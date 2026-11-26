
from typing import List, Dict, Any

from sentence_transformers import CrossEncoder


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

RERANKER_DEVICE = "cpu"

RERANKER_BATCH_SIZE = 8

_reranker = None


# --------------------------------------------------
# LOAD CROSS-ENCODER MODEL
# --------------------------------------------------

def get_reranker():

    global _reranker

    if _reranker is None:

        print("\nLoading Cross-Encoder Reranker...")

        _reranker = CrossEncoder(
            RERANKER_MODEL_NAME,
            device=RERANKER_DEVICE
        )

        print("Cross-Encoder loaded successfully.")

    return _reranker


# --------------------------------------------------
# RERANK DOCUMENTS
# --------------------------------------------------

def rerank_documents(
    question: str,
    chunks: List[Dict[str, Any]],
    top_k: int = 5
) -> List[Dict[str, Any]]:

    print("\n========== CROSS-ENCODER RERANKING ==========")

    if not chunks or top_k <= 0:
        print("No chunks available for reranking.")
        return []

    model = get_reranker()

    pairs = []

    for chunk in chunks:

        chunk_text = chunk.get("text", "")

        pairs.append(
            (question, chunk_text)
        )

    scores = model.predict(
        pairs,
        batch_size=RERANKER_BATCH_SIZE,
        show_progress_bar=False
    )

    reranked_chunks = []

    for chunk, score in zip(chunks, scores):

        updated_chunk = dict(chunk)

        updated_chunk["rerank_score"] = float(score)

        reranked_chunks.append(updated_chunk)

    reranked_chunks.sort(
        key=lambda item: item["rerank_score"],
        reverse=True
    )

    final_chunks = reranked_chunks[:top_k]

    print("Input chunks:", len(chunks))
    print("Final reranked chunks:", len(final_chunks))

    for index, chunk in enumerate(final_chunks, start=1):

        print(f"\n--- RERANKED CHUNK {index} ---")

        print("Rerank score:", chunk.get("rerank_score"))

        print(
            "Original relevance score:",
            chunk.get("relevance_score")
        )

        print("Metadata:", chunk.get("metadata"))

    return final_chunks
