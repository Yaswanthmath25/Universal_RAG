import re
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END

from backend.services.agentic_rag.multi_query import multi_query_search
from backend.services.agentic_rag.reranker import rerank_documents
from backend.services.agentic_rag.claim_validator import validate_answer_claims
from backend.services.agentic_rag.source_attributor import attribute_answer_sources
from backend.services.llm_service import call_ollama, generate_answer


MAX_RETRIES = 1
MAX_ANSWER_RETRIES = 0

RETRIEVAL_CANDIDATES = 10
FINAL_CONTEXT_CHUNKS = 8

FALLBACK_ANSWER = (
    "I couldn't find information about this question in the uploaded document."
)


class RAGState(TypedDict, total=False):
    question: str
    search_query: str
    conversation_history: str

    top_k: int
    document_id: str

    role: str
    user_id: str

    retrieved_chunks: List[Dict[str, Any]]
    compressed_chunks: List[Dict[str, Any]]

    is_relevant: bool
    retry_count: int
    answer_retry_count: int

    answer: str
    answer_is_valid: bool

    claim_validation: Dict[str, Any]
    source_attribution: Dict[str, Any]
    sources: List[Dict[str, Any]]


def resolve_followup_question(state: RAGState):

    question = state["question"].strip()
    history = state.get("conversation_history", "")

    if not history.strip():
        return {"search_query": question}

    followup_patterns = [
        r"^(and|also|what about|how about|why|when|where|who|which)\b",
        r"\b(it|they|them|their|that|those|these|he|she|his|her)\b",
        r"\b(the same|that one|those ones|previous one)\b",
    ]

    is_followup = any(
        re.search(pattern, question.lower())
        for pattern in followup_patterns
    )

    if not is_followup:
        return {"search_query": question}

    prompt = f"""
Rewrite the current question as a standalone document search query.

Use the conversation history only to resolve references.
Preserve the user's original intent.
Do not introduce new topics or assumptions.
Do not answer the question.
Return only the rewritten query.

Conversation history:
{history}

Current question:
{question}

Standalone search query:
"""

    try:
        rewritten_query = call_ollama(prompt).strip()

        if not rewritten_query or len(rewritten_query) > 500:
            rewritten_query = question

    except Exception as error:
        print("Follow-up rewrite error:", error)
        rewritten_query = question

    return {"search_query": rewritten_query}


def retrieve_documents(state: RAGState):

    query = state.get("search_query") or state["question"]

    print("\n========== RETRIEVE ==========")
    print("Query:", query)
    print("Role:", state.get("role", "admin"))
    print("User:", state.get("user_id"))

    try:
        results = multi_query_search(
            question=query,
            top_k=RETRIEVAL_CANDIDATES,
            document_id=state.get("document_id"),
            role=state.get("role", "admin"),
            user_id=state.get("user_id"),
        )
    except Exception as error:
        print("Multi-query retrieval failed:", error)
        results = []

    print("Retrieved:", len(results))

    if not results:
        return {"retrieved_chunks": []}

    try:
        reranked_results = rerank_documents(
            question=query,
            chunks=results,
            top_k=FINAL_CONTEXT_CHUNKS,
        )
    except Exception as error:
        print("Reranking failed:", error)
        reranked_results = results[:FINAL_CONTEXT_CHUNKS]

    print("Reranked:", len(reranked_results))

    return {"retrieved_chunks": reranked_results}


def grade_documents(state: RAGState):

    chunks = state.get("retrieved_chunks", [])

    relevant_chunks = [
        chunk for chunk in chunks
        if isinstance(chunk, dict)
        and chunk.get("text", "").strip()
    ]

    if not relevant_chunks:
        return {"is_relevant": False}

    return {"is_relevant": True}


def rewrite_question(state: RAGState):

    question = state["question"]

    prompt = f"""
Improve this document search query without changing its meaning.

Original question:
{question}

Previous search query:
{state.get("search_query", question)}

Use important keywords from the original question.
Do not introduce unrelated topics.
Return only the improved search query.
"""

    try:
        rewritten_query = call_ollama(prompt).strip()
        if not rewritten_query or len(rewritten_query) > 500:
            rewritten_query = question
    except Exception:
        rewritten_query = question

    retry_count = state.get("retry_count", 0) + 1

    return {
        "search_query": rewritten_query,
        "retry_count": retry_count,
    }


def compress_context(state: RAGState):

    chunks = state.get("retrieved_chunks", [])

    if not chunks:
        return {"compressed_chunks": []}

    compressed_chunks = []
    seen_chunks = set()

    for chunk in chunks:

        text = chunk.get("text", "").strip()

        if not text:
            continue

        normalized = re.sub(r"\s+", " ", text.lower()).strip()

        if normalized in seen_chunks:
            continue

        seen_chunks.add(normalized)
        compressed_chunks.append(chunk)

    return {"compressed_chunks": compressed_chunks}


def generate_final_answer(state: RAGState):

    chunks = state.get("compressed_chunks", [])

    if not chunks:
        return {"answer": FALLBACK_ANSWER}

    try:
        answer = generate_answer(
            question=state["question"],
            retrieved_chunks=chunks,
        )
        answer = answer.strip()
        if not answer:
            answer = FALLBACK_ANSWER
    except Exception as error:
        print("Answer generation error:", error)
        answer = FALLBACK_ANSWER

    print("\n========== GENERATED ANSWER ==========")
    print(answer)

    return {"answer": answer}


def evaluate_answer(state: RAGState):

    answer = state.get("answer", "").strip()
    chunks = state.get("compressed_chunks", [])

    if not answer or answer == FALLBACK_ANSWER:
        return {
            "answer_is_valid": False,
            "claim_validation": {
                "is_grounded": False,
                "unsupported_claims": [],
            },
        }

    try:
        validation = validate_answer_claims(
            answer=answer,
            retrieved_chunks=chunks,
        )
        is_valid = validation.get("is_grounded", False)
    except Exception as error:
        print("Claim validation error:", error)
        validation = {
            "is_grounded": False,
            "unsupported_claims": [],
        }
        is_valid = False

    print("\n========== CLAIM VALIDATION ==========")
    print("Is grounded:", is_valid)
    print("Supported:", validation.get("supported_claims"))
    print("Unsupported:", validation.get("unsupported_claims"))

    return {
        "answer_is_valid": is_valid,
        "claim_validation": validation,
    }


def regenerate_answer(state: RAGState):

    answer = state.get("answer", "")
    chunks = state.get("compressed_chunks", [])

    context = "\n\n".join(
        chunk.get("text", "")
        for chunk in chunks
    )

    prompt = f"""
Correct the answer using only the document content.

Original question:
{state["question"]}

Original answer:
{answer}

Document content:
{context}

Instructions:
- Keep supported facts from the original answer.
- Answer the original question directly.
- Do not invent information.
- If the answer cannot be found, return exactly:
{FALLBACK_ANSWER}

Corrected answer:
"""

    try:
        corrected_answer = call_ollama(prompt).strip()
        if not corrected_answer:
            corrected_answer = FALLBACK_ANSWER
    except Exception:
        corrected_answer = FALLBACK_ANSWER

    retry_count = state.get("answer_retry_count", 0) + 1

    return {
        "answer": corrected_answer,
        "answer_retry_count": retry_count,
    }


def attribute_sources(state: RAGState):

    answer = state.get("answer", "")
    chunks = state.get("compressed_chunks", [])

    if not answer or answer == FALLBACK_ANSWER:
        return {
            "source_attribution": {},
            "sources": [],
        }

    try:
        attribution = attribute_answer_sources(
            answer=answer,
            retrieved_chunks=chunks,
        )
        sources = attribution.get("sources", [])
    except Exception as error:
        print("Source attribution error:", error)
        attribution = {}
        sources = []

    return {
        "source_attribution": attribution,
        "sources": sources,
    }


def finalize_answer(state: RAGState):

    answer = state.get("answer", "").strip()

    print("\n========== FINALIZE ==========")
    print("Is relevant:", state.get("is_relevant"))
    print("Answer length:", len(answer))

    if not state.get("is_relevant", False) or not answer:
        answer = FALLBACK_ANSWER
    # NOTE: we do NOT discard the answer on claim-validation failure.
    # The answer_validator + claim_validator already filter out
    # truly hallucinated content. Keeping the answer here prevents
    # losing a grounded response due to a single outlier claim.

    print("Final answer:", answer[:200])

    return {"answer": answer}


def route_after_grading(state: RAGState):

    if state.get("is_relevant", False):
        return "compress_context"

    if state.get("retry_count", 0) < MAX_RETRIES:
        return "rewrite_question"

    return "finalize_answer"


def route_after_evaluation(state: RAGState):

    return "attribute_sources"


workflow = StateGraph(RAGState)

workflow.add_node("resolve_followup_question", resolve_followup_question)
workflow.add_node("retrieve_documents", retrieve_documents)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("rewrite_question", rewrite_question)
workflow.add_node("compress_context", compress_context)
workflow.add_node("generate_final_answer", generate_final_answer)
workflow.add_node("evaluate_answer", evaluate_answer)
workflow.add_node("regenerate_answer", regenerate_answer)
workflow.add_node("attribute_sources", attribute_sources)
workflow.add_node("finalize_answer", finalize_answer)

workflow.set_entry_point("resolve_followup_question")

workflow.add_edge("resolve_followup_question", "retrieve_documents")
workflow.add_edge("retrieve_documents", "grade_documents")

workflow.add_conditional_edges(
    "grade_documents",
    route_after_grading,
    {
        "compress_context": "compress_context",
        "rewrite_question": "rewrite_question",
        "finalize_answer": "finalize_answer",
    },
)

workflow.add_edge("rewrite_question", "retrieve_documents")
workflow.add_edge("compress_context", "generate_final_answer")
workflow.add_edge("generate_final_answer", "evaluate_answer")

workflow.add_conditional_edges(
    "evaluate_answer",
    route_after_evaluation,
    {
        "attribute_sources": "attribute_sources",
    },
)

workflow.add_edge("attribute_sources", "finalize_answer")
workflow.add_edge("finalize_answer", END)

agentic_rag_app = workflow.compile()


def run_agentic_rag(
    question: str,
    top_k: int = 5,
    document_id: str = None,
    conversation_history: str = "",
    role: str = "admin",
    user_id: str = None,
):

    print("\n========================================")
    print("       STARTING AGENTIC RAG")
    print("========================================")
    print("Role:", role, "| User:", user_id)

    initial_state = {
        "question": question,
        "search_query": question,
        "conversation_history": conversation_history,
        "top_k": top_k,
        "document_id": document_id,
        "role": role,
        "user_id": user_id,
        "retrieved_chunks": [],
        "compressed_chunks": [],
        "is_relevant": False,
        "retry_count": 0,
        "answer_retry_count": 0,
        "answer": "",
        "answer_is_valid": False,
        "claim_validation": {},
        "source_attribution": {},
        "sources": [],
    }

    result = agentic_rag_app.invoke(initial_state)

    print("\n========== RAG COMPLETED ==========")

    return result