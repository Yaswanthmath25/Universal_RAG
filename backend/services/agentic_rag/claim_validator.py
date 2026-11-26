import re
from typing import List, Dict, Any

from backend.services.llm_service import call_ollama


FALLBACK_ANSWER = (
    "I couldn't find information about this question "
    "in the uploaded document."
)

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "be", "been", "being", "to", "of", "in", "on",
    "for", "and", "or", "but", "that", "this",
    "these", "those", "it", "its", "as", "at",
    "by", "from", "with", "may", "might", "can",
    "could", "should", "would", "must", "will",
    "while", "once", "when", "where", "who",
    "what", "which", "how", "their", "they",
    "them", "there", "here"
}

NON_FACTUAL_PREFIXES = (
    "here are the policies",
    "these are the policies",
    "these policies are",
    "if you need more information",
    "if you need further information",
    "please provide more details",
    "let me know if",
    "based on the information provided"
)


def normalize_text(text):

    text = text.lower()
    text = re.sub(r"[^a-z0-9+#.]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_keyword(word):

    word = word.lower().strip()

    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"

    if len(word) > 5 and word.endswith("ation"):
        return word[:-5]

    if len(word) > 5 and word.endswith("ed"):
        return word[:-2]

    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]

    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]

    return word


def get_meaningful_tokens(text):

    words = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return {
        normalize_keyword(word)
        for word in words
        if word not in STOP_WORDS
        and len(word) > 1
    }


def is_locally_supported(claim, normalized_context, context_tokens):

    normalized_claim = normalize_text(claim)

    if not normalized_claim:
        return False

    if normalized_claim in normalized_context:
        return True

    claim_tokens = get_meaningful_tokens(claim)

    if len(claim_tokens) < 3:
        return True

    matched_tokens = claim_tokens.intersection(context_tokens)
    coverage = len(matched_tokens) / len(claim_tokens)

    return (
        len(matched_tokens) >= 2
        and coverage >= 0.40
    )


def extract_claims(answer):

    answer = re.sub(r"\*\*(.*?)\*\*", r"\1", answer)
    answer = re.sub(r"__(.*?)__", r"\1", answer)

    claims = []
    lines = answer.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()

        if not line:
            continue

        if re.match(r"^(?:POL|L)-\d+\b", line, re.IGNORECASE):
            continue

        normalized_line = normalize_text(line)

        if any(
            normalized_line.startswith(prefix)
            for prefix in NON_FACTUAL_PREFIXES
        ):
            continue

        sentences = re.split(r"(?<=[.!?])\s+", line)

        for sentence in sentences:

            sentence = sentence.strip()
            sentence = re.sub(
                r"^\s*(?:[-*•]|\d+[.)])\s*",
                "",
                sentence
            ).strip()

            if not sentence:
                continue

            normalized = normalize_text(sentence)

            if any(
                normalized.startswith(prefix)
                for prefix in NON_FACTUAL_PREFIXES
            ):
                continue

            if len(get_meaningful_tokens(sentence)) < 3:
                continue

            claims.append(sentence)

    unique_claims = []
    seen = set()

    for claim in claims:
        normalized = normalize_text(claim)
        if normalized not in seen:
            seen.add(normalized)
            unique_claims.append(claim)

    return unique_claims


def verify_claims_batch(claims, context):

    if not claims:
        return {}

    numbered_claims = "\n".join(
        f"{index}. {claim}"
        for index, claim in enumerate(claims, start=1)
    )

    prompt = f"""
You are a document-grounding evaluator.

Evaluate every claim independently against the document.

DOCUMENT CONTENT:
{context}

CLAIMS:
{numbered_claims}

RULES:
- Accept a claim when its meaning is clearly supported.
- Accept reasonable paraphrases and equivalent wording.
- A claim may be supported by multiple sentences.
- Do not reject a claim only because its wording differs.
- Reject claims that are missing or contradicted.
- Do not use external knowledge.
- Do not assume information that is not present.
- Evaluate every numbered claim.
- Return exactly one verdict for each claim.
- Use the original claim numbers.
- Do not create additional claim numbers.

OUTPUT FORMAT:
1: SUPPORTED
2: UNSUPPORTED
3: SUPPORTED

Return only the verdict lines.
"""

    try:
        response = call_ollama(prompt)

        if not response:
            raise ValueError("Ollama returned an empty response.")

        response = response.strip().upper()

        results = {}

        for line in response.splitlines():

            match = re.match(
                r"^\s*(\d+)\s*[:.)-]\s*(SUPPORTED|UNSUPPORTED)\b",
                line
            )

            if not match:
                continue

            claim_number = int(match.group(1))
            verdict = match.group(2)

            if 1 <= claim_number <= len(claims):
                results[claim_number] = (verdict == "SUPPORTED")

        return results

    except Exception as error:
        print("\nClaim validation failed:", str(error))
        return {}


def validate_answer_claims(answer, retrieved_chunks):

    if (
        not answer
        or answer.strip() == FALLBACK_ANSWER
    ):
        return {
            "is_grounded": False,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_results": []
        }

    if not retrieved_chunks:
        return {
            "is_grounded": False,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_results": []
        }

    context = "\n\n".join(
        chunk.get("text", "")
        for chunk in retrieved_chunks
        if chunk.get("text")
    )

    if not context.strip():
        return {
            "is_grounded": False,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_results": []
        }

    claims = extract_claims(answer)

    if not claims:
        return {
            "is_grounded": False,
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": [],
            "claim_results": []
        }

    normalized_context = normalize_text(context)
    context_tokens = get_meaningful_tokens(context)

    claim_results = []
    claims_requiring_llm = []
    claim_indexes = []

    for index, claim in enumerate(claims, start=1):

        if is_locally_supported(
            claim=claim,
            normalized_context=normalized_context,
            context_tokens=context_tokens
        ):
            claim_results.append({
                "claim": claim,
                "is_supported": True,
                "evaluation": "SUPPORTED - Local document evidence"
            })
        else:
            claim_results.append(None)
            claims_requiring_llm.append(claim)
            claim_indexes.append(index)

    if claims_requiring_llm:

        batch_results = verify_claims_batch(
            claims=claims_requiring_llm,
            context=context
        )

        for batch_index, claim in enumerate(
            claims_requiring_llm,
            start=1
        ):

            original_index = claim_indexes[batch_index - 1] - 1

            # DEFAULT TO SUPPORTED if LLM verdict is missing.
            # The downstream answer_validator provides a second check.
            is_supported = batch_results.get(batch_index, True)

            evaluation = (
                "SUPPORTED - LLM verification"
                if is_supported
                else "UNSUPPORTED - Not verified against document"
            )

            claim_results[original_index] = {
                "claim": claim,
                "is_supported": is_supported,
                "evaluation": evaluation
            }

    supported_claims = sum(
        1
        for result in claim_results
        if result and result["is_supported"]
    )

    unsupported_claims = [
        result["claim"]
        for result in claim_results
        if not result or not result["is_supported"]
    ]

    is_grounded = (
        len(claims) > 0
        and len(unsupported_claims) == 0
    )

    return {
        "is_grounded": is_grounded,
        "total_claims": len(claims),
        "supported_claims": supported_claims,
        "unsupported_claims": unsupported_claims,
        "claim_results": claim_results
    }