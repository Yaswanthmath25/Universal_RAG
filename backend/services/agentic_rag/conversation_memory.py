
from typing import List, Dict, Any, Optional

from backend.database import SessionLocal
from backend.models import ChatHistory


MAX_HISTORY_MESSAGES = 6


def get_conversation_history(
    conversation_id: str,
    user_id: str,
    document_id: Optional[str] = None,
    limit: int = MAX_HISTORY_MESSAGES
) -> List[Dict[str, Any]]:

    if not conversation_id or not user_id:
        return []

    db = SessionLocal()

    try:
        query = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.conversation_id == conversation_id,
                ChatHistory.user_id == user_id
            )
        )

        if document_id:
            query = query.filter(
                ChatHistory.document_id == document_id
            )

        chats = (
            query
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
            .all()
        )

        chats.reverse()

        return [
            {
                "question": chat.question,
                "answer": chat.answer,
                "document_id": chat.document_id,
                "created_at": (
                    chat.created_at.isoformat()
                    if chat.created_at else None
                )
            }
            for chat in chats
        ]

    finally:
        db.close()


def format_conversation_history(
    history: List[Dict[str, Any]]
) -> str:

    if not history:
        return "No previous conversation."

    formatted_messages = []

    for index, message in enumerate(history, start=1):
        formatted_messages.append(
            f"""
Conversation Turn {index}
User:
{message.get("question", "")}

Assistant:
{message.get("answer", "")}
"""
        )

    return "\n\n".join(formatted_messages)


def build_conversation_context(
    conversation_id: str,
    user_id: str,
    document_id: Optional[str] = None,
    limit: int = MAX_HISTORY_MESSAGES
) -> Dict[str, Any]:

    history = get_conversation_history(
        conversation_id=conversation_id,
        user_id=user_id,
        document_id=document_id,
        limit=limit
    )

    formatted_history = format_conversation_history(history)

    return {
        "conversation_id": conversation_id,
        "history": history,
        "formatted_history": formatted_history,
        "total_messages": len(history)
    }
