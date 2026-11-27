from typing import Any, Dict, List

from backend.services.cloudflare_ai import run_model


RERANKER_MODEL = "@cf/baai/bge-reranker-base"


def rerank_documents(
    question: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    if not chunks or top_k <= 0:
        return []

    try:
        result = run_model(
            RERANKER_MODEL,
            {
                "query": question,
                "contexts": [{"text": chunk.get("text", "")} for chunk in chunks],
                "top_k": min(top_k, len(chunks)),
            },
        )

        ranked_items = result.get("response", [])
        if not ranked_items:
            raise RuntimeError("Cloudflare AI returned no reranking results")

        reranked = []
        for rank, item in enumerate(ranked_items):
            index = item.get("id", item.get("index", rank)) if isinstance(item, dict) else rank
            score = item.get("score", 0.0) if isinstance(item, dict) else float(item)
            index = int(index)
            if 0 <= index < len(chunks):
                updated = dict(chunks[index])
                updated["rerank_score"] = float(score)
                reranked.append(updated)

        if not reranked:
            raise RuntimeError("Cloudflare AI returned invalid reranking indices")
        return reranked[:top_k]

    except Exception as error:
        print(f"[RERANKER] Falling back to original order: {error}")
        return chunks[:top_k]
