import re
from typing import List, Dict, Any

from backend.services.llm_service import call_ollama
from backend.services.retrieval_service import search_documents


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

NUMBER_OF_QUERIES = 2
RRF_K = 60
RETRIEVAL_TOP_K = 20

STOP_WORDS = {
    "what", "are", "is", "the", "a", "an", "of", "in",
    "on", "for", "to", "and", "or", "how", "when",
    "where", "who", "which", "why", "can", "could",
    "would", "should", "do", "does", "did", "tell",
    "me", "about", "please", "my", "your", "their",
    "this", "that", "these", "those"
}

SCOPE_WORDS = {
    "internal",
    "confidential",
    "admin-only",
    "customer-facing",
    "employee",
    "technical",
    "private",
    "restricted"
}


def normalize_keyword(word: str) -> str:

    word = word.lower().strip()

    if word.endswith("'s"):
        word = word[:-2]

    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"

    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]

    return word


def get_important_keywords(text: str) -> set:

    words = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return {
        normalize_keyword(word)
        for word in words
        if normalize_keyword(word) not in STOP_WORDS
        and len(word) > 1
    }


def is_valid_query_variant(original_question, generated_query):

    original_keywords = get_important_keywords(original_question)
    generated_keywords = get_important_keywords(generated_query)

    if not original_keywords:
        return True

    if not original_keywords.issubset(generated_keywords):
        return False

    original_scope = get_important_keywords(original_question) & SCOPE_WORDS
    generated_scope = get_important_keywords(generated_query) & SCOPE_WORDS

    if generated_scope - original_scope:
        return False

    return True


def generate_search_queries(question: str) -> List[str]:

    print("\n========== MULTI QUERY GENERATION ==========")

    prompt = f"""
You are a document search query generation assistant.

Original question:
{question}

Generate exactly {NUMBER_OF_QUERIES} alternative search queries.

STRICT RULES:
- Preserve every important keyword from the original question.
- Preserve the exact subject and scope of the question.
- Use different wording without changing the meaning.
- Do not introduce internal, confidential, technical,
  customer-facing, or other new topics unless they appear
  in the original question.
- Do not invent company names, departments, or entities.
- Do not answer the question.
- Return one query per line.
- Do not include numbering or explanations.
"""

    queries = [question.strip()]

    try:
        response = call_ollama(prompt)

        for line in response.splitlines():

            cleaned = re.sub(
                r"^\s*(?:[-*]|\d+[.)])\s*",
                "",
                line
            ).strip()

            if not cleaned:
                continue

            if not is_valid_query_variant(question, cleaned):
                print("Rejected unrelated query:", cleaned)
                continue

            if cleaned.lower() not in {item.lower() for item in queries}:
                queries.append(cleaned)

            if len(queries) >= NUMBER_OF_QUERIES + 1:
                break

    except Exception as error:
        print("Multi-query generation failed:", error)
        print("Using original question for retrieval.")

    print("\nGenerated queries:")
    for query in queries:
        print("-", query)

    return queries


def reciprocal_rank_fusion(
    search_results: List[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:

    print("\n========== RRF RANK FUSION ==========")

    fused_results = {}

    for results in search_results:
        for rank, chunk in enumerate(results, start=1):

            metadata = chunk.get("metadata", {})
            document_id = metadata.get("document_id", "")
            chunk_number = metadata.get("chunk_number", "")

            if document_id or chunk_number:
                chunk_id = f"{document_id}_{chunk_number}"
            else:
                chunk_id = chunk.get("text", str(chunk))

            if chunk_id not in fused_results:
                fused_results[chunk_id] = {
                    **chunk,
                    "rrf_score": 0.0
                }

            fused_results[chunk_id]["rrf_score"] += (1.0 / (RRF_K + rank))

    ranked_results = sorted(
        fused_results.values(),
        key=lambda item: item["rrf_score"],
        reverse=True
    )

    print("Unique chunks after fusion:", len(ranked_results))

    return ranked_results


def multi_query_search(
    question: str,
    top_k: int = 5,
    document_id: str = None,
    role: str = "admin",
    user_id: str = None,
):

    print("\n========== MULTI QUERY RETRIEVAL ==========")

    queries = generate_search_queries(question)

    all_search_results = []

    for query in queries:

        print("\nSearching:", query)

        try:
            results = search_documents(
                question=query,
                top_k=RETRIEVAL_TOP_K,
                document_id=document_id,
                role=role,
                user_id=user_id,
            )
        except Exception as error:
            print("Search failed for query:", query)
            print("Search error:", error)
            results = []

        print("Retrieved:", len(results))

        all_search_results.append(results)

    fused_results = reciprocal_rank_fusion(all_search_results)

    candidate_limit = max(top_k, RETRIEVAL_TOP_K)

    final_results = fused_results[:candidate_limit]

    print("\nFinal RRF results:", len(final_results))

    return final_results