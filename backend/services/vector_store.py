from pathlib import Path

import chromadb
from chromadb.config import Settings


CHROMA_DIR = Path(__file__).resolve().parents[2] / "chroma_db"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)


client = chromadb.PersistentClient(
    path=str(CHROMA_DIR),
    settings=Settings(anonymized_telemetry=False),
)


collection = client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "l2"},
)


# --------------------------------------------------
# METADATA BUILDER
# --------------------------------------------------

def _build_metadatas(chunks, document_id, access_scope, target_user_id):

    metadatas = []

    for chunk in chunks:
        metadatas.append({
            "document_id": document_id,
            "chunk_number": int(chunk["chunk_number"]),
            "chunk_id": chunk["chunk_id"],
            "filename": chunk["filename"],
            "page_number": (
                int(chunk["page_number"])
                if chunk.get("page_number") is not None
                else -1
            ),
            "access_scope": access_scope,
            # Chroma rejects None in metadata — use "" for company_policy
            "target_user_id": target_user_id if target_user_id else "",
        })

    return metadatas


# --------------------------------------------------
# STORE
# --------------------------------------------------

def store_chunks(
    chunks,
    embeddings,
    document_id,
    access_scope="company_policy",
    target_user_id=None
):

    if not chunks:
        return 0

    ids = [
        f"{document_id}_chunk_{chunk['chunk_number']}"
        for chunk in chunks
    ]

    documents = [chunk["text"] for chunk in chunks]

    metadatas = _build_metadatas(
        chunks,
        document_id,
        access_scope,
        target_user_id,
    )

    embedding_list = [
        embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        for embedding in embeddings
    ]

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embedding_list,
        metadatas=metadatas,
    )

    return len(chunks)


def replace_document_vectors(
    chunks,
    embeddings,
    document_id,
    access_scope="company_policy",
    target_user_id=None
):

    delete_document_vectors(document_id)

    return store_chunks(
        chunks,
        embeddings,
        document_id,
        access_scope=access_scope,
        target_user_id=target_user_id,
    )


def delete_document_vectors(document_id):

    existing = collection.get(
        where={"document_id": document_id}
    )

    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        return len(existing["ids"])

    return 0


def get_collection_count():
    return collection.count()