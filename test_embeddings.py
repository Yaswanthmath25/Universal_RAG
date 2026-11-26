
from backend.services.embedding_service import generate_embeddings

sample_chunks = [
    {
        "chunk_id": "chunk_1",
        "text": "Python is a programming language."
    },
    {
        "chunk_id": "chunk_2",
        "text": "Machine learning uses data to train models."
    }
]

embeddings = generate_embeddings(sample_chunks)

print("Number of embeddings:", len(embeddings))
print("Dimensions of each embedding:", len(embeddings[0]))
print("First embedding preview:", embeddings[0][:5])
print("Embedding shape:", embeddings.shape)
