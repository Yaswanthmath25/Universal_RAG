from typing import List, Dict, Any

import os
import requests


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_API = f"https://api-inference.huggingface.co/models/{RERANKER_MODEL}"
HF_TOKEN = os.getenv("HF_TOKEN")


def _call_reranker(question, chunk_texts):
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    pairs = [[question, text] for text in chunk_texts]

    response = requests.post(
        RERANKER_API,
        headers=headers,
        json={"inputs": pairs, "options": {"wait_for_model": True}},
        timeout=120
    )
    response.raise_for_status()
    return response.json()


def rerank_documents(
    question: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 5
) -> List[Dict[str, Any]]:

    if not chunks or top_k <= 0:
        return []

    try:
        chunk_texts = [chunk.get("text", "") for chunk in chunks]
        scores_raw = _call_reranker(question, chunk_texts)

        # HF returns either [{"score": x}, ...] or [[score], ...]
        scores = []
        for item in scores_raw:
            if isinstance(item, dict):
                scores.append(float(item.get("score", 0.0)))
            elif isinstance(item, list):
                scores.append(float(item[0]) if item else 0.0)
            else:
                scores.append(float(item))

        reranked = []
        for chunk, score in zip(chunks, scores):
            updated = dict(chunk)
            updated["rerank_score"] = score
            reranked.append(updated)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]

    except Exception as error:
        print(f"[RERANKER] Falling back to original order: {error}")
        # Graceful fallback — keep hybrid-retrieval order
        return chunks[:top_k]