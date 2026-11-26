import requests


OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL_NAME = "qwen2.5:3b"


def call_ollama(prompt):

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 1000,
            "temperature": 0
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=600
        )

        response.raise_for_status()

        return response.json()["response"].strip()

    except requests.RequestException as error:
        raise RuntimeError(
            f"Unable to communicate with Ollama: {error}"
        )


def generate_answer(question, retrieved_chunks):

    context = "\n\n".join(
        chunk["text"]
        for chunk in retrieved_chunks
    )

    prompt = f"""
You are a precise document question-answering assistant.

Your task is to answer the user's question using the provided document context.

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{question}

IMPORTANT INSTRUCTIONS:

1. Read the complete document context before answering.
2. Search for information related to the question throughout ALL retrieved chunks.
3. Pay attention to section headings, policy IDs, names, dates, and descriptions.
4. If the question asks about company policies, identify all policy sections and policy IDs present in the context.
5. If the question asks for all policies, include every relevant policy found in the context.
6. Explain each policy briefly using the actual document information.
7. Do not conclude that information is missing when relevant information is present in any retrieved chunk.
8. Retrieved chunks may contain different portions of the same document. Combine relevant information from all chunks.
9. Do not invent information or use external knowledge.
10. If the requested information genuinely does not exist anywhere in the context, respond exactly:
I couldn't find information about this question in the uploaded document.

Write a clear and complete answer.

ANSWER:
"""

    answer = call_ollama(prompt)

    return answer