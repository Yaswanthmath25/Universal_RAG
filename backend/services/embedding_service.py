import os

from openai import OpenAI


MODEL = "text-embedding-3-small"
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _embed_texts(texts):
    if not texts:
        return []

    response = _client.embeddings.create(
        model=MODEL,
        input=texts,
    )
    # The API returns an index for each item; sort to preserve input order.
    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


def generate_embeddings(chunks):
    if not chunks:
        return []

    texts = [chunk["text"] for chunk in chunks]
    batch_size = 100
    embeddings = []

    for start in range(0, len(texts), batch_size):
        embeddings.extend(_embed_texts(texts[start:start + batch_size]))

    return embeddings


def generate_query_embedding(question):
    return _embed_texts([question])[0]
