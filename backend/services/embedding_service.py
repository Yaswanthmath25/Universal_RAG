import os
import requests


HF_TOKEN = os.getenv("HF_TOKEN")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{MODEL}"


def _call_hf_api(inputs, timeout=120):
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    response = requests.post(
        API_URL,
        headers=headers,
        json={"inputs": inputs, "options": {"wait_for_model": True}},
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def generate_embeddings(chunks):
    if not chunks:
        return []

    texts = [chunk["text"] for chunk in chunks]

    # HF API accepts up to ~100 inputs per call; batch to be safe.
    BATCH_SIZE = 50
    all_vectors = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        vectors = _call_hf_api(batch)
        all_vectors.extend(vectors)

    return all_vectors


def generate_query_embedding(question):
    result = _call_hf_api(question, timeout=60)

    if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
        return result[0]
    return result