from backend.services.cloudflare_ai import run_model


MODEL_NAME = "@cf/meta/llama-3.1-8b-instruct"


def call_ollama(prompt):
    """Compatibility wrapper for the existing RAG workflow."""
    result = run_model(
        MODEL_NAME,
        {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 1000,
        },
    )
    response = result.get("response") if isinstance(result, dict) else None
    if not response:
        raise RuntimeError("Cloudflare AI returned an empty chat response")
    return response.strip()


def generate_answer(question, retrieved_chunks):
    context = "\n\n".join(chunk["text"] for chunk in retrieved_chunks)

    prompt = f"""
You are a precise document question-answering assistant.

Answer the user's question using only the provided document context. Read all
context, combine relevant details, and do not invent facts. If the requested
information does not appear in the context, respond exactly:
I couldn't find information about this question in the uploaded document.

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{question}

ANSWER:
"""

    return call_ollama(prompt)
