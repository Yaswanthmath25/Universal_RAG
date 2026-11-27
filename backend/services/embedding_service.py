from backend.services.cloudflare_ai import run_model


MODEL = "@cf/baai/bge-base-en-v1.5"
BATCH_SIZE = 50


def _embed_texts(texts):
    if not texts:
        return []

    result = run_model(MODEL, {"text": texts})
    vectors = result.get("data") if isinstance(result, dict) else result
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise RuntimeError("Cloudflare AI returned an unexpected embedding response")
    return vectors


def generate_embeddings(chunks):
    if not chunks:
        return []

    texts = [chunk["text"] for chunk in chunks]
    embeddings = []
    for start in range(0, len(texts), BATCH_SIZE):
        embeddings.extend(_embed_texts(texts[start:start + BATCH_SIZE]))
    return embeddings


def generate_query_embedding(question):
    return _embed_texts([question])[0]
