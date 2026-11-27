import re
import math
from collections import Counter

from backend.services.embedding_service import generate_query_embedding
from backend.services.vector_store import collection


SEMANTIC_WEIGHT = 0.60
TFIDF_WEIGHT = 0.40

DEFAULT_TOP_K = 5
MAX_CANDIDATES = 30
NEIGHBOR_SCORE_FACTOR = 0.75


def build_access_filter(role, user_id, document_id=None):

    clauses = []

    if role == "customer":
        if not user_id:
            raise ValueError("user_id is required for customer access")

        clauses.append({
            "$and": [
                {"access_scope": "user_data"},
                {"target_user_id": user_id},
            ]
        })

    elif role != "admin":
        raise ValueError(f"Unknown role: {role}")

    if document_id:
        clauses.append({"document_id": document_id})

    if not clauses:
        return None

    if len(clauses) == 1:
        return clauses[0]

    return {"$and": clauses}


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9+#.\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def calculate_tfidf_scores(question, documents):
    if not documents:
        return []

    def terms(text):
        words = re.findall(r"\b[a-z0-9+#.]+\b", normalize_text(text))
        unigrams = words
        bigrams = [f"{left} {right}" for left, right in zip(words, words[1:])]
        return unigrams + bigrams

    document_terms = [terms(document) for document in documents]
    question_counts = Counter(terms(question))
    if not question_counts:
        return [0.0] * len(documents)

    document_frequencies = Counter()
    for tokens in document_terms:
        document_frequencies.update(set(tokens))

    document_count = len(documents)
    idf = {
        term: math.log((1 + document_count) / (1 + frequency)) + 1.0
        for term, frequency in document_frequencies.items()
    }
    question_weights = {
        term: (1.0 + math.log(count)) * idf.get(term, 0.0)
        for term, count in question_counts.items()
    }
    question_norm = math.sqrt(sum(weight * weight for weight in question_weights.values()))
    if not question_norm:
        return [0.0] * len(documents)

    scores = []
    for tokens in document_terms:
        term_counts = Counter(tokens)
        document_weights = {
            term: (1.0 + math.log(term_counts[term])) * idf[term]
            for term in set(tokens)
            if term in idf
        }
        document_norm = math.sqrt(
            sum(weight * weight for weight in document_weights.values())
        )
        dot_product = sum(
            question_weights.get(term, 0.0) * weight
            for term, weight in document_weights.items()
        )
        scores.append(
            dot_product / (question_norm * document_norm)
            if document_norm
            else 0.0
        )
    return scores


def calculate_semantic_scores(distances):
    if len(distances) == 0:
        return []
    return [1.0 / (1.0 + max(float(distance), 0.0)) for distance in distances]


def search_documents(
    question,
    top_k=DEFAULT_TOP_K,
    document_id=None,
    role="admin",
    user_id=None,
):

    if top_k <= 0:
        return []

    where_filter = build_access_filter(role, user_id, document_id)

    get_params = {"include": ["documents", "metadatas"]}
    if where_filter:
        get_params["where"] = where_filter

    all_docs = collection.get(**get_params)

    if not all_docs["ids"]:
        print(f"[RETRIEVAL] No docs for role={role} user_id={user_id}")
        return []

    total_vectors = len(all_docs["ids"])
    document_texts = all_docs["documents"]

    query_embedding = generate_query_embedding(question)
    candidate_count = min(total_vectors, max(top_k * 4, MAX_CANDIDATES))

    search_params = {
        "query_embeddings": [query_embedding],
        "n_results": candidate_count,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        search_params["where"] = where_filter

    semantic_results = collection.query(**search_params)

    semantic_chunks = {}
    if semantic_results["ids"] and semantic_results["ids"][0]:
        for i, chunk_id in enumerate(semantic_results["ids"][0]):
            semantic_chunks[chunk_id] = {
                "distance": semantic_results["distances"][0][i]
            }

    tfidf_scores = calculate_tfidf_scores(question, document_texts)

    semantic_ids = list(semantic_chunks.keys())
    semantic_distances = [
        semantic_chunks[cid]["distance"] for cid in semantic_ids
    ]
    semantic_scores = calculate_semantic_scores(semantic_distances)
    semantic_score_map = dict(zip(semantic_ids, semantic_scores))

    candidates = {}

    for i, chunk_id in enumerate(all_docs["ids"]):
        tfidf_score = float(tfidf_scores[i])
        semantic_score = semantic_score_map.get(chunk_id, 0.0)
        distance = (
            semantic_chunks[chunk_id]["distance"]
            if chunk_id in semantic_chunks
            else None
        )

        candidates[chunk_id] = {
            "text": all_docs["documents"][i],
            "metadata": all_docs["metadatas"][i],
            "distance": distance,
            "semantic_score": semantic_score,
            "tfidf_score": tfidf_score,
            "relevance_score": (
                SEMANTIC_WEIGHT * semantic_score
                + TFIDF_WEIGHT * tfidf_score
            ),
        }

    ranked = sorted(
        candidates.values(),
        key=lambda x: x["relevance_score"],
        reverse=True,
    )

    selected = ranked[: min(total_vectors, max(top_k * 2, 10))]

    neighbor_scores = {}
    for item in selected:
        metadata = item["metadata"]
        doc_id = metadata.get("document_id")
        chunk_number = metadata.get("chunk_number")
        if doc_id is None or chunk_number is None:
            continue
        for nearby in (chunk_number - 1, chunk_number + 1):
            if nearby <= 0:
                continue
            neighbor_id = f"{doc_id}_chunk_{nearby}"
            propagated = item["relevance_score"] * NEIGHBOR_SCORE_FACTOR
            neighbor_scores[neighbor_id] = max(
                neighbor_scores.get(neighbor_id, 0.0),
                propagated,
            )

    missing = [cid for cid in neighbor_scores if cid not in candidates]
    if missing:
        neighbor_get = {
            "ids": missing,
            "include": ["documents", "metadatas"],
        }
        if where_filter:
            neighbor_get["where"] = where_filter
        neighbors = collection.get(**neighbor_get)
        for i, chunk_id in enumerate(neighbors["ids"]):
            candidates[chunk_id] = {
                "text": neighbors["documents"][i],
                "metadata": neighbors["metadatas"][i],
                "distance": None,
                "semantic_score": 0.0,
                "tfidf_score": 0.0,
                "relevance_score": neighbor_scores[chunk_id],
            }

    final = sorted(
        candidates.values(),
        key=lambda x: x["relevance_score"],
        reverse=True,
    )

    print(
        f"[RETRIEVAL] role={role} user_id={user_id} "
        f"filter={where_filter} total={total_vectors} "
        f"final={len(final[:top_k])}"
    )

    return [
        {
            "text": item["text"],
            "metadata": item["metadata"],
            "distance": item["distance"],
            "relevance_score": item["relevance_score"],
        }
        for item in final[:top_k]
    ]
