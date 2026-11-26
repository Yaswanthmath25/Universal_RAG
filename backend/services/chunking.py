
def split_text(text, chunk_size=500, overlap=100):

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Overlap must be smaller than chunk size")

    chunks = []
    start = 0

    while start < len(text):

        end = min(start + chunk_size, len(text))

        # Try to avoid cutting a word in half
        if end < len(text):
            last_space = text.rfind(" ", start, end)

            if last_space > start:
                end = last_space

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # Move forward while keeping some overlapping text
        start = max(end - overlap, start + 1)

    return chunks


def chunk_document(extracted_data, filename):

    all_chunks = []
    chunk_number = 1

    for section in extracted_data:

        text = section["text"]
        page_number = section["page_number"]

        text_chunks = split_text(
            text,
            chunk_size=500,
            overlap=100
        )

        for chunk in text_chunks:

            all_chunks.append({
                "chunk_id": f"chunk_{chunk_number}",
                "chunk_number": chunk_number,
                "filename": filename,
                "page_number": page_number,
                "text": chunk
            })

            chunk_number += 1

    return all_chunks
