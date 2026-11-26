import re

from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.models import (
    User,
    Customer,
    CustomerAddress,
    Order,
    OrderItem,
    Product,
    Payment,
    Delivery,
    SupportTicket,
)

from backend.services.agentic_rag.graph import run_agentic_rag

from backend.services.customer_data_service import (
    answer_customer_question as answer_customer_from_database,
)


# ============================================================
# ADMIN DATABASE QUESTION DETECTION
# ============================================================

def detect_admin_database_intent(question: str):
    q = question.lower().strip()

    # --------------------------------------------------------
    # CUSTOMERS WHO ORDERED A SPECIFIC PRODUCT
    # --------------------------------------------------------

    customer_order_patterns = [
        r"\bhow many customers\b.*\b(order|ordered|bought|purchased)\b",
        r"\bnumber of customers\b.*\b(order|ordered|bought|purchased)\b",
        r"\bcustomers who\b.*\b(order|ordered|bought|purchased)\b",
        r"\bcustomers that\b.*\b(order|ordered|bought|purchased)\b",
    ]

    if any(
        re.search(pattern, q)
        for pattern in customer_order_patterns
    ):
        return "customers_ordered_product"

    # --------------------------------------------------------
    # CUSTOMER DETAILS QUESTIONS
    # --------------------------------------------------------

    customer_detail_patterns = [
        r"\bcustomer details\b",
        r"\bcustomer information\b",
        r"\bcustomer records\b",
        r"\ball customers\b",
        r"\bevery customer\b",
        r"\blist customers\b",
        r"\bshow customers\b",
        r"\bdisplay customers\b",
        r"\bget customers\b",
        r"\bgive me .*customers?\b",
        r"\bfetch .*customers?\b",
        r"\bdetails of .*customers?\b",
        r"\binformation about .*customers?\b",
    ]

    if any(
        re.search(pattern, q)
        for pattern in customer_detail_patterns
    ):
        return "customer_details"

    # --------------------------------------------------------
    # COUNT QUESTIONS
    # --------------------------------------------------------

    count_patterns = [
        r"\bhow many\b",
        r"\bcount\b",
        r"\bnumber of\b",
        r"\btotal count\b",
        r"\btotal number\b",
        r"\btotal\s+(customers?|clients?|orders?|purchases?|products?|items?|payments?|transactions?|deliveries?|shipments?|tickets?)\b",
        r"\b(count|number)\s+of\b",
        r"\b(how many|count|number)\b",
    ]

    is_count_question = any(
        re.search(pattern, q)
        for pattern in count_patterns
    )

    if not is_count_question:
        if re.search(
            r"\b(active|inactive)\s+(customers?|products?)\b",
            q
        ):
            is_count_question = True

    if not is_count_question:
        return None

    entities = {
        "customers": [
            r"\bcustomers?\b",
            r"\bclients?\b",
        ],
        "orders": [
            r"\borders?\b",
            r"\bpurchases?\b",
        ],
        "products": [
            r"\bproducts?\b",
            r"\bitems?\b",
        ],
        "payments": [
            r"\bpayments?\b",
            r"\btransactions?\b",
        ],
        "deliveries": [
            r"\bdeliveries\b",
            r"\bdelivery\b",
            r"\bshipments?\b",
        ],
        "support_tickets": [
            r"\bsupport tickets?\b",
            r"\btickets?\b",
        ],
    }

    for intent, patterns in entities.items():
        if any(re.search(pattern, q) for pattern in patterns):
            return intent

    return None


# ============================================================
# ADMIN CUSTOMER DETAILS
# ============================================================

def answer_admin_customer_details(db: Session):

    customers = (
        db.query(Customer, User)
        .join(User, Customer.user_id == User.id)
        .order_by(Customer.created_at.desc())
        .all()
    )

    if not customers:
        return "There are no customer records in the database."

    lines = [
        f"**Complete Customer Details ({len(customers)} customers)**\n"
    ]

    for index, (customer, user) in enumerate(customers, start=1):

        addresses = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.customer_id == customer.id
            )
            .order_by(CustomerAddress.is_default.desc())
            .all()
        )

        lines.append(
            f"### Customer {index}\n"
            f"- Customer ID: {customer.id}\n"
            f"- Name: {customer.full_name or 'Not available'}\n"
            f"- Username: {user.username or 'Not available'}\n"
            f"- Email: {user.email or 'Not available'}\n"
            f"- Phone: {customer.phone or 'Not available'}\n"
            f"- Account status: {'Active' if customer.is_active else 'Inactive'}\n"
            f"- Registered: {customer.created_at or 'Not available'}"
        )

        if addresses:
            lines.append("**Saved Addresses:**")

            for address_index, address in enumerate(addresses, start=1):

                address_parts = [
                    address.address_line1,
                    address.address_line2,
                    address.city,
                    address.state,
                    address.postal_code,
                    address.country,
                ]

                formatted_address = ", ".join(
                    str(part).strip()
                    for part in address_parts
                    if part and str(part).strip()
                )

                lines.append(
                    f"- Address {address_index}: {formatted_address}"
                    f" ({address.address_type or 'Address'})"
                    f"{' [Default]' if address.is_default else ''}"
                )

        else:
            lines.append("- Saved Addresses: No addresses available")

        lines.append("\n---\n")

    return "\n".join(lines)


# ============================================================
# CUSTOMERS WHO ORDERED A SPECIFIC PRODUCT
# ============================================================

def answer_customers_ordered_product(
    db: Session,
    question: str,
):
    q = question.lower()

    products = db.query(Product).all()

    matched_product = None

    for product in products:
        if product.name.lower() in q:
            matched_product = product
            break

    if not matched_product:
        return (
            "I couldn't identify the product in your question. "
            "Please provide the exact product name."
        )

    customer_count = (
        db.query(Order.customer_id)
        .join(
            OrderItem,
            OrderItem.order_id == Order.id
        )
        .filter(
            or_(
                OrderItem.product_id == matched_product.id,
                OrderItem.product_name.ilike(matched_product.name)
            )
        )
        .distinct()
        .count()
    )

    return (
        f"**Customer Purchase Report**\n\n"
        f"- Product: {matched_product.name}\n"
        f"- Unique customers who ordered this product: {customer_count}"
    )


# ============================================================
# ADMIN DATABASE ANSWER SERVICE
# ============================================================

def answer_admin_database_question(
    db: Session,
    question: str,
):

    intent = detect_admin_database_intent(question)

    if not intent:
        return None

    q = question.lower()

    # --------------------------------------------------------
    # CUSTOMERS WHO ORDERED A PRODUCT
    # --------------------------------------------------------

    if intent == "customers_ordered_product":

        answer = answer_customers_ordered_product(
            db,
            question
        )

    # --------------------------------------------------------
    # COMPLETE CUSTOMER DETAILS
    # --------------------------------------------------------

    elif intent == "customer_details":

        answer = answer_admin_customer_details(db)

    # --------------------------------------------------------
    # CUSTOMER COUNTS
    # --------------------------------------------------------

    elif intent == "customers":

        total = db.query(Customer).count()

        active = (
            db.query(Customer)
            .filter(Customer.is_active.is_(True))
            .count()
        )

        inactive = (
            db.query(Customer)
            .filter(Customer.is_active.is_(False))
            .count()
        )

        if re.search(r"\binactive\b", q):
            answer = f"There are **{inactive} inactive customers**."

        elif re.search(r"\bactive\b", q):
            answer = f"There are **{active} active customers**."

        else:
            answer = (
                f"**Customer Summary**\n\n"
                f"- Total customers: {total}\n"
                f"- Active customers: {active}\n"
                f"- Inactive customers: {inactive}"
            )

    # --------------------------------------------------------
    # ORDERS
    # --------------------------------------------------------

    elif intent == "orders":

        total = db.query(Order).count()

        answer = (
            f"There are **{total} orders** in the database."
        )

    # --------------------------------------------------------
    # PRODUCTS
    # --------------------------------------------------------

    elif intent == "products":

        total = db.query(Product).count()

        active = (
            db.query(Product)
            .filter(Product.is_active.is_(True))
            .count()
        )

        inactive = (
            db.query(Product)
            .filter(Product.is_active.is_(False))
            .count()
        )

        if re.search(r"\binactive\b", q):
            answer = f"There are **{inactive} inactive products**."

        elif re.search(r"\bactive\b", q):
            answer = f"There are **{active} active products**."

        else:
            answer = (
                f"**Product Summary**\n\n"
                f"- Total products: {total}\n"
                f"- Active products: {active}\n"
                f"- Inactive products: {inactive}"
            )

    # --------------------------------------------------------
    # PAYMENTS
    # --------------------------------------------------------

    elif intent == "payments":

        total = db.query(Payment).count()

        answer = (
            f"There are **{total} payment records** in the database."
        )

    # --------------------------------------------------------
    # DELIVERIES
    # --------------------------------------------------------

    elif intent == "deliveries":

        total = db.query(Delivery).count()

        answer = (
            f"There are **{total} delivery records** in the database."
        )

    # --------------------------------------------------------
    # SUPPORT TICKETS
    # --------------------------------------------------------

    elif intent == "support_tickets":

        total = db.query(SupportTicket).count()

        answer = (
            f"There are **{total} support tickets** in the database."
        )

    else:
        return None

    return {
        "answer": answer,
        "sources": [],
        "intent": intent,
        "source_type": "postgresql",
    }


# ============================================================
# ADMIN QUESTION SERVICE
# ============================================================

def answer_admin_question(
    question: str,
    db: Session,
    top_k: int = 5,
    document_id: str | None = None,
    conversation_history: str = "",
    admin_user_id: str | None = None,
):
    """
    Admin-only AI service.

    PostgreSQL:
    - Complete customer details
    - Customers who ordered a particular product
    - Customer counts
    - Order counts
    - Product counts
    - Payment counts
    - Delivery counts
    - Support ticket counts

    Agentic RAG / ChromaDB:
    - Company policies
    - Uploaded documents
    - Knowledge base questions

    Access must be protected by require_admin in the API route.
    """

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    question = question.strip()

    database_result = answer_admin_database_question(
        db=db,
        question=question,
    )

    if database_result is not None:
        return database_result

    return run_agentic_rag(
        question=question,
        top_k=top_k,
        document_id=document_id,
        conversation_history=conversation_history,
        role="admin",
        user_id=admin_user_id,
    )


# ============================================================
# CUSTOMER QUESTION SERVICE
# ============================================================

def answer_customer_question(
    user_id: str,
    question: str,
):
    """
    Customer-only AI service.

    Uses PostgreSQL customer records only.
    Does not access ChromaDB or admin documents.
    The user_id must come from the authenticated JWT user.
    """

    if not user_id:
        raise ValueError("Authenticated user ID is required.")

    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    return answer_customer_from_database(
        user_id=user_id,
        question=question.strip(),
    )