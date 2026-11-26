import re
from typing import List, Dict, Any

from backend.services.llm_service import call_ollama


def extract_answer_claims(answer: str) -> List[str]:

    if not answer or not answer.strip():
        return []

    claims = re.split(r'(?<=[.!?])\s+', answer.strip())

    return [
        claim.strip()
        for claim in claims
        if claim.strip()
    ]


def build_numbered_context(chunks: List[Dict[str, Any]]) -> str:

    context_parts = []

    for index, chunk in enumerate(chunks, start=1):

        metadata = chunk.get("metadata", {})

        page_number = metadata.get("page_number", "Unknown")
        chunk_number = metadata.get("chunk_number", "Unknown")

        text = chunk.get("text", "").strip()

        if not text:
            continue

        context_parts.append(
            f"""
[CHUNK_ID: {index}]
[PAGE_NUMBER: {page_number}]
[CHUNK_NUMBER: {chunk_number}]

CONTENT:
{text}
"""
        )

    return "\n\n".join(context_parts)


def format_source(chunk: Dict[str, Any]) -> Dict[str, Any]:

    metadata = chunk.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    page = metadata.get("page_number")
    if page == -1:
        page = None

    return {
        "filename": (
            metadata.get("filename")
            or metadata.get("source")
        ),
        "page_number": page,
        "chunk_number": metadata.get("chunk_number"),
        "document_id": metadata.get("document_id"),
        "source": metadata.get("source"),
        "text": chunk.get("text", "")
    }


def attribute_answer_sources(
    answer: str,
    retrieved_chunks: List[Dict[str, Any]] = None,
    chunks: List[Dict[str, Any]] = None
) -> Dict[str, Any]:

    if retrieved_chunks is None:
        retrieved_chunks = chunks or []

    claims = extract_answer_claims(answer)

    # Even if attribution fails, return all retrieved chunks as
    # "sources" so the frontend can show where the answer came from.
    fallback_sources = [
        format_source(chunk) for chunk in retrieved_chunks
    ]

    if not claims or not retrieved_chunks:
        return {
            "total_claims": len(claims),
            "attributed_claims": 0,
            "unattributed_claims": claims,
            "claim_sources": [],
            "sources": fallback_sources
        }

    numbered_context = build_numbered_context(retrieved_chunks)

    if not numbered_context.strip():
        return {
            "total_claims": len(claims),
            "attributed_claims": 0,
            "unattributed_claims": claims,
            "claim_sources": [],
            "sources": fallback_sources
        }

    numbered_claims = "\n".join(
        f"{index}. {claim}"
        for index, claim in enumerate(claims, start=1)
    )

    prompt = f"""
You are a document source attribution assistant.

Identify which document chunks directly support each claim.

DOCUMENT CHUNKS:
{numbered_context}

ANSWER CLAIMS:
{numbered_claims}

RULES:
- Evaluate every claim independently.
- Select only chunks that directly support each claim.
- A claim can have multiple supporting chunks.
- Use only the supplied document content.
- Do not guess.
- If no chunk supports a claim, return NONE.
- Use the exact output format below.
- Do not include explanations.

OUTPUT FORMAT:
1: 1,2
2: NONE
3: 2,3
"""

    claim_sources = []
    unattributed_claims = []
    all_sources = []
    seen_sources = set()

    try:
        response = call_ollama(prompt)

        if not response:
            raise ValueError("Empty attribution response.")

        results = {}

        for line in response.splitlines():

            match = re.match(r"^\s*(\d+)\s*[:.)-]\s*(.*)$", line.strip())

            if not match:
                continue

            claim_number = int(match.group(1))

            if not 1 <= claim_number <= len(claims):
                continue

            value = match.group(2).strip().upper()

            if value == "NONE":
                results[claim_number] = []
                continue

            indexes = re.findall(r"\b\d+\b", value)
            selected_indexes = []

            for item in indexes:
                index = int(item)
                if (
                    1 <= index <= len(retrieved_chunks)
                    and index not in selected_indexes
                ):
                    selected_indexes.append(index)

            results[claim_number] = selected_indexes

        for claim_number, claim in enumerate(claims, start=1):

            selected_indexes = results.get(claim_number, [])
            sources = []

            for index in selected_indexes:

                source = format_source(retrieved_chunks[index - 1])
                sources.append(source)

                source_key = (
                    source.get("document_id"),
                    source.get("page_number"),
                    source.get("chunk_number")
                )

                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    all_sources.append(source)

            is_attributed = bool(sources)

            if not is_attributed:
                unattributed_claims.append(claim)

            claim_sources.append({
                "claim": claim,
                "sources": sources,
                "is_attributed": is_attributed
            })

    except Exception as error:

        print("Source attribution failed:", error)

        for claim in claims:
            unattributed_claims.append(claim)
            claim_sources.append({
                "claim": claim,
                "sources": [],
                "is_attributed": False
            })

    # If attribution produced no sources at all, fall back to
    # returning every retrieved chunk. Better to show the user
    # where the answer came from than nothing.
    if not all_sources:
        all_sources = fallback_sources

    attributed_count = sum(
        1 for item in claim_sources if item["is_attributed"]
    )

    return {
        "total_claims": len(claims),
        "attributed_claims": attributed_count,
        "unattributed_claims": unattributed_claims,
        "claim_sources": claim_sources,
        "sources": all_sources
    }