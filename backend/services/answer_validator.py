import re


STOPWORDS = {
    "the", "is", "are", "was", "were", "a", "an", "and",
    "or", "of", "in", "on", "at", "to", "for", "from",
    "by", "with", "this", "that", "it", "its", "as",
    "what", "which", "who", "when", "where", "how",
    "paper", "publication", "published", "name", "called"
}


def normalize_text(text):

    text = text.lower()
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_programming_languages(context):

    pattern = r"Programming\s*:\s*([^\n]+)"

    match = re.search(pattern, context, re.IGNORECASE)

    if not match:
        return []

    items = [
        item.strip()
        for item in match.group(1).split(",")
        if item.strip()
    ]

    excluded_items = ["data structures"]

    return [
        item for item in items
        if item.lower() not in excluded_items
    ]


def extract_keywords(text):

    words = re.findall(r"\b[a-zA-Z0-9+#.]+\b", text.lower())

    return {
        word for word in words
        if len(word) > 2 and word not in STOPWORDS
    }


def validate_answer(answer, retrieved_chunks, question=""):

    context = "\n".join(
        chunk.get("text", "")
        for chunk in retrieved_chunks
    )

    normalized_context = normalize_text(context)
    normalized_answer = normalize_text(answer)

    expected_items = []

    if "programming" in question.lower():
        expected_items = extract_programming_languages(context)

    if expected_items:

        missing_items = [
            item
            for item in expected_items
            if normalize_text(item) not in normalized_answer
        ]

        supported_items = [
            item
            for item in expected_items
            if normalize_text(item) in normalized_answer
        ]

        is_supported = len(supported_items) > 0
        is_complete = len(missing_items) == 0

    else:

        if (
            normalized_answer
            and normalized_answer in normalized_context
        ):
            return {
                "is_supported": True,
                "is_complete": True,
                "missing_items": [],
                "expected_items": []
            }

        answer_keywords = extract_keywords(answer)
        context_keywords = extract_keywords(context)

        matching_keywords = answer_keywords.intersection(
            context_keywords
        )

        if answer_keywords:
            match_ratio = len(matching_keywords) / len(answer_keywords)
        else:
            match_ratio = 0

        # Lowered from 0.35 to 0.15 — qwen2.5:3b paraphrases
        # heavily, and stricter thresholds cause false rejections
        # of grounded answers.
        is_supported = (
            bool(context.strip())
            and bool(answer.strip())
            and match_ratio >= 0.15
        )

        is_complete = True
        missing_items = []

    return {
        "is_supported": is_supported,
        "is_complete": is_complete,
        "missing_items": missing_items,
        "expected_items": expected_items
    }