from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import ChatHistory

from backend.services.auth_dependencies import (
    get_current_user,
    require_admin,
    require_customer,
)

from backend.services.role_based_qa_service import (
    answer_admin_question,
)

from backend.services.customer_data_service import (
    answer_customer_question as answer_customer_from_database,
    detect_customer_intents,
)

from backend.services.order_agent_service import (
    handle_customer_order,
    encode_order_state,
)

from backend.services.agentic_rag.graph import run_agentic_rag


router = APIRouter()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    conversation_id: str | None = None
    document_id: str | None = None


def get_user_id(current_user):
    if isinstance(current_user, dict):
        user_id = current_user.get("id")
    else:
        user_id = getattr(current_user, "id", None)

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user ID not found.",
        )

    return str(user_id)


def check_conversation_access(db, conversation_id, user_id):
    existing = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id,
        )
        .first()
    )

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )


def save_chat_history(
    db,
    conversation_id,
    user_id,
    question,
    answer,
    document_id=None,
    order_state=None,
):
    chat = ChatHistory(
        id=str(uuid4()),
        conversation_id=conversation_id,
        user_id=user_id,
        document_id=document_id,
        order_state=order_state,
        question=question,
        answer=answer,
    )

    db.add(chat)
    db.commit()
    db.refresh(chat)

    return chat


def get_user_conversation_context(
    db,
    conversation_id,
    user_id,
    document_id=None,
):
    query = db.query(ChatHistory).filter(
        ChatHistory.conversation_id == conversation_id,
        ChatHistory.user_id == user_id,
    )

    if document_id:
        query = query.filter(ChatHistory.document_id == document_id)

    history = (
        query
        .order_by(ChatHistory.created_at.desc())
        .limit(6)
        .all()
    )

    history.reverse()

    formatted = ""

    for item in history:
        formatted += (
            f"User: {item.question}\n"
            f"Assistant: {item.answer}\n"
        )

    return formatted


def format_sources(sources):
    formatted = []

    for source in sources or []:
        if isinstance(source, dict):
            metadata = source.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            page = source.get("page_number") or metadata.get("page_number")
            if page == -1:
                page = None

            formatted.append({
                "filename": (
                    source.get("filename")
                    or metadata.get("filename")
                ),
                "page_number": page,
                "chunk_number": (
                    source.get("chunk_number")
                    or metadata.get("chunk_number")
                ),
                "document_id": (
                    source.get("document_id")
                    or metadata.get("document_id")
                ),
                "content": (
                    source.get("content")
                    or source.get("text")
                    or source.get("page_content")
                    or ""
                ),
            })

        else:
            metadata = getattr(source, "metadata", {}) or {}
            page = metadata.get("page_number")
            if page == -1:
                page = None

            formatted.append({
                "filename": metadata.get("filename"),
                "page_number": page,
                "chunk_number": metadata.get("chunk_number"),
                "document_id": metadata.get("document_id"),
                "content": getattr(source, "page_content", ""),
            })

    return formatted


# ============================================================
# ADMIN AI ASSISTANT
# ============================================================

@router.post("/qa/search")
def admin_search(
    request: QuestionRequest,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user_id = get_user_id(current_user)
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    conversation_id = request.conversation_id or str(uuid4())

    if request.conversation_id:
        check_conversation_access(db, conversation_id, user_id)

    conversation_history = get_user_conversation_context(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        document_id=request.document_id,
    )

    result = answer_admin_question(
        question=question,
        db=db,
        top_k=request.top_k,
        document_id=request.document_id,
        conversation_history=conversation_history,
        admin_user_id=user_id,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Invalid response from admin AI service.",
        )

    answer = result.get("answer", "")

    chat = save_chat_history(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        question=question,
        answer=answer,
        document_id=request.document_id,
    )

    sources = format_sources(result.get("sources", []))

    return {
        "chat_id": str(chat.id),
        "conversation_id": conversation_id,
        "role": "admin",
        "question": question,
        "answer": answer,
        "total_results": len(sources),
        "sources": sources,
        "source_type": result.get("source_type", "chromadb"),
        "validation": {
            "is_relevant": result.get("is_relevant"),
            "answer_is_valid": result.get("answer_is_valid"),
            "retry_count": result.get("retry_count"),
            "answer_retry_count": result.get("answer_retry_count"),
        },
        "claim_validation": result.get("claim_validation"),
        "source_attribution": result.get("source_attribution"),
    }


# ============================================================
# CUSTOMER AI ASSISTANT + ORDERING AGENT
# ============================================================

@router.post("/qa/customer-search")
def customer_search(
    request: QuestionRequest,
    current_user=Depends(require_customer),
    db: Session = Depends(get_db),
):
    user_id = get_user_id(current_user)
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    conversation_id = request.conversation_id or str(uuid4())

    if request.conversation_id:
        check_conversation_access(db, conversation_id, user_id)

    # ---------------- Order agent first ----------------

    try:
        order_result = handle_customer_order(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
        )
    except Exception as error:
        db.rollback()
        print(
            "Customer order agent error:",
            type(error).__name__,
            str(error),
        )
        raise HTTPException(
            status_code=500,
            detail="The ordering assistant could not process your request.",
        )

    if order_result is not None:
        answer = order_result.get("answer", "")
        order_state = order_result.get("order_state")
        saved_state = encode_order_state(order_state)

        chat = save_chat_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            question=question,
            answer=answer,
            document_id=None,
            order_state=saved_state,
        )

        return {
            "chat_id": str(chat.id),
            "conversation_id": conversation_id,
            "role": "customer",
            "question": question,
            "answer": answer,
            "total_results": 0,
            "sources": [],
            "intent": order_result.get("intent", "order"),
            "order_status": (
                "pending"
                if order_state
                else "completed_or_cancelled"
            ),
        }

    # ---------------- Structured customer data ----------------

    detected_intents = detect_customer_intents(question)
    known_intents = [i for i in detected_intents if i != "unknown"]

    if known_intents:
        result = answer_customer_from_database(
            user_id=user_id,
            question=question,
        )

        if isinstance(result, dict):
            answer = result.get("answer", "")
            sources = result.get("sources", [])
        else:
            answer = str(result)
            sources = []

        chat = save_chat_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            question=question,
            answer=answer,
            document_id=None,
        )

        return {
            "chat_id": str(chat.id),
            "conversation_id": conversation_id,
            "role": "customer",
            "question": question,
            "answer": answer,
            "total_results": len(sources),
            "sources": sources,
            "intent": ", ".join(known_intents),
        }

    # ---------------- RAG fallback for uploaded documents ----------------

    conversation_history = get_user_conversation_context(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        document_id=request.document_id,
    )

    rag_result = run_agentic_rag(
        question=question,
        top_k=request.top_k,
        document_id=request.document_id,
        conversation_history=conversation_history,
        role="customer",
        user_id=user_id,
    )

    answer = rag_result.get("answer", "")
    sources = format_sources(rag_result.get("sources", []))

    chat = save_chat_history(
        db=db,
        conversation_id=conversation_id,
        user_id=user_id,
        question=question,
        answer=answer,
        document_id=request.document_id,
    )

    return {
        "chat_id": str(chat.id),
        "conversation_id": conversation_id,
        "role": "customer",
        "question": question,
        "answer": answer,
        "total_results": len(sources),
        "sources": sources,
        "source_type": "chromadb",
        "intent": "documents",
    }


# ============================================================
# HISTORY ENDPOINTS
# ============================================================

@router.get("/qa/history/{conversation_id}")
def get_conversation_history(
    conversation_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_user_id(current_user)
    check_conversation_access(db, conversation_id, user_id)

    messages = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id,
        )
        .order_by(ChatHistory.created_at.asc())
        .all()
    )

    return {
        "conversation_id": conversation_id,
        "total_messages": len(messages),
        "messages": [
            {
                "chat_id": str(m.id),
                "question": m.question,
                "answer": m.answer,
                "document_id": m.document_id,
                "order_state": m.order_state,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.get("/qa/conversations")
def get_conversations(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_user_id(current_user)

    messages = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.created_at.desc())
        .all()
    )

    conversations = {}

    for m in messages:
        cid = m.conversation_id

        if cid not in conversations:
            conversations[cid] = {
                "conversation_id": cid,
                "last_question": m.question,
                "last_answer": m.answer,
                "updated_at": m.created_at,
                "total_messages": 0,
            }

        conversations[cid]["total_messages"] += 1

    return {
        "total_conversations": len(conversations),
        "conversations": list(conversations.values()),
    }


@router.delete("/qa/history/{conversation_id}")
def delete_conversation_history(
    conversation_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_user_id(current_user)
    check_conversation_access(db, conversation_id, user_id)

    deleted = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id,
        )
        .delete(synchronize_session=False)
    )

    db.commit()

    return {
        "message": "Conversation deleted successfully.",
        "conversation_id": conversation_id,
        "deleted_messages": deleted,
    }