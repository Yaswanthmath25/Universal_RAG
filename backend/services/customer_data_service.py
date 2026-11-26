
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from backend.database import SessionLocal
from backend.models import (
    Customer,
    CustomerAddress,
    Product,
    Order,
    OrderItem,
    Payment,
    Delivery,
    SupportTicket,
)


# ============================================================
# CUSTOMER PROFILE
# ============================================================

def get_customer_profile(db: Session, user_id: str):
    return (
        db.query(Customer)
        .filter(
            Customer.user_id == user_id,
            Customer.is_active.is_(True)
        )
        .first()
    )


# ============================================================
# FORMATTING HELPERS
# ============================================================

def format_date(value):
    if not value:
        return "Not available"

    return value.strftime("%Y-%m-%d")


def format_amount(value):
    if value is None:
        return "0.00"

    return f"{value:.2f}"


def no_records(message):
    return message


# ============================================================
# CUSTOMER PROFILE INFORMATION
# ============================================================

def get_profile_answer(db: Session, customer: Customer):
    user = customer.user_id

    from backend.models import User

    account = (
        db.query(User)
        .filter(User.id == user)
        .first()
    )

    if not account:
        return "Your account profile could not be found."

    return (
        f"**Your Profile**\n\n"
        f"- Name: {customer.full_name}\n"
        f"- Username: {account.username}\n"
        f"- Email: {account.email}\n"
        f"- Phone: {customer.phone or 'Not provided'}\n"
        f"- Account status: {'Active' if customer.is_active else 'Inactive'}\n"
        f"- Registered on: {format_date(customer.created_at)}"
    )


# ============================================================
# CUSTOMER ADDRESSES
# ============================================================

def get_address_answer(db: Session, customer: Customer):
    addresses = (
        db.query(CustomerAddress)
        .filter(CustomerAddress.customer_id == customer.id)
        .order_by(desc(CustomerAddress.is_default),
                  desc(CustomerAddress.created_at))
        .all()
    )

    if not addresses:
        return no_records("No addresses are saved in your account.")

    results = ["**Your Saved Addresses**"]

    for index, address in enumerate(addresses, start=1):
        lines = [
            address.address_line1,
            address.address_line2,
            address.city,
            address.state,
            address.postal_code,
            address.country,
        ]

        full_address = ", ".join(
            str(item).strip()
            for item in lines
            if item and str(item).strip()
        )

        results.append(
            f"\n**Address {index}**"
            f"\n- Type: {address.address_type or 'Not specified'}"
            f"\n- Address: {full_address}"
            f"\n- Default address: {'Yes' if address.is_default else 'No'}"
        )

    return "\n".join(results)


# ============================================================
# PUBLIC PRODUCT CATALOG
# ============================================================

def get_product_answer(db: Session, question: str):
    products = (
        db.query(Product)
        .filter(Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .limit(20)
        .all()
    )

    if not products:
        return "There are currently no active products in the catalog."

    question_words = {
        word.lower().strip(".,?!")
        for word in question.split()
        if len(word) > 2
    }

    matched = []

    for product in products:
        searchable_text = (
            f"{product.name or ''} "
            f"{product.description or ''} "
            f"{product.sku or ''}"
        ).lower()

        if any(word in searchable_text for word in question_words):
            matched.append(product)

    # If the question asks for the catalog generally, show active products.
    if not matched:
        catalog_terms = [
            "product", "catalog", "available", "selling",
            "show", "list", "all", "what"
        ]

        if any(term in question.lower() for term in catalog_terms):
            matched = products

    if not matched:
        return "I couldn't find a matching active product in the catalog."

    results = ["**Available Products**"]

    for product in matched[:10]:
        results.append(
            f"\n- **{product.name}**"
            f"\n  - SKU: {product.sku}"
            f"\n  - Price: ₹{format_amount(product.price)}"
            f"\n  - Description: {product.description or 'Not available'}"
        )

    return "\n".join(results)


# ============================================================
# CUSTOMER ORDERS
# ============================================================

def get_orders_answer(db: Session, customer: Customer):
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer.id)
        .order_by(desc(Order.created_at))
        .limit(10)
        .all()
    )

    if not orders:
        return "You do not have any orders in your account yet."

    results = ["**Your Recent Orders**"]

    for order in orders:
        results.append(
            f"\n**Order: {order.order_number}**"
            f"\n- Status: {order.status}"
            f"\n- Total amount: ₹{format_amount(order.total_amount)}"
            f"\n- Order date: {format_date(order.created_at)}"
        )

        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .all()
        )

        if items:
            results.append("- Items:")

            for item in items:
                results.append(
                    f"  - {item.product_name}: "
                    f"{item.quantity} × ₹{format_amount(item.unit_price)} "
                    f"= ₹{format_amount(item.subtotal)}"
                )

        delivery = (
            db.query(Delivery)
            .filter(Delivery.order_id == order.id)
            .first()
        )

        if delivery:
            results.append(
                f"- Delivery status: {delivery.status}"
            )

            if delivery.tracking_number:
                results.append(
                    f"- Tracking number: {delivery.tracking_number}"
                )

            if delivery.estimated_delivery_at:
                results.append(
                    "- Estimated delivery: "
                    f"{format_date(delivery.estimated_delivery_at)}"
                )

    return "\n".join(results)


# ============================================================
# CUSTOMER PAYMENTS
# ============================================================

def get_payments_answer(db: Session, customer: Customer):
    payments = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Order.customer_id == customer.id)
        .order_by(desc(Payment.created_at))
        .limit(10)
        .all()
    )

    if not payments:
        return "No payment records were found for your orders."

    results = ["**Your Payment History**"]

    for payment in payments:
        order = (
            db.query(Order)
            .filter(
                Order.id == payment.order_id,
                Order.customer_id == customer.id
            )
            .first()
        )

        if not order:
            continue

        results.append(
            f"\n**Order: {order.order_number}**"
            f"\n- Amount: ₹{format_amount(payment.amount)}"
            f"\n- Payment method: {payment.payment_method or 'Not specified'}"
            f"\n- Payment status: {payment.status}"
            f"\n- Paid on: {format_date(payment.paid_at)}"
        )

    return "\n".join(results)


# ============================================================
# CUSTOMER DELIVERY INFORMATION
# ============================================================

def get_delivery_answer(db: Session, customer: Customer):
    deliveries = (
        db.query(Delivery, Order)
        .join(Order, Delivery.order_id == Order.id)
        .filter(Order.customer_id == customer.id)
        .order_by(desc(Delivery.created_at))
        .limit(10)
        .all()
    )

    if not deliveries:
        return "No delivery records were found for your orders."

    results = ["**Your Delivery Information**"]

    for delivery, order in deliveries:
        results.append(
            f"\n**Order: {order.order_number}**"
            f"\n- Delivery status: {delivery.status}"
            f"\n- Tracking number: {delivery.tracking_number or 'Not available'}"
            f"\n- Courier: {delivery.courier_name or 'Not available'}"
            f"\n- Shipped on: {format_date(delivery.shipped_at)}"
            f"\n- Estimated delivery: {format_date(delivery.estimated_delivery_at)}"
            f"\n- Delivered on: {format_date(delivery.delivered_at)}"
        )

    return "\n".join(results)


# ============================================================
# CUSTOMER SUPPORT TICKETS
# ============================================================

def get_support_answer(db: Session, customer: Customer):
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.customer_id == customer.id)
        .order_by(desc(SupportTicket.created_at))
        .limit(10)
        .all()
    )

    if not tickets:
        return "You do not have any support tickets."

    results = ["**Your Support Tickets**"]

    for ticket in tickets:
        results.append(
            f"\n**Ticket: {ticket.ticket_number}**"
            f"\n- Subject: {ticket.subject}"
            f"\n- Description: {ticket.description}"
            f"\n- Status: {ticket.status}"
            f"\n- Priority: {ticket.priority}"
            f"\n- Created on: {format_date(ticket.created_at)}"
        )

    return "\n".join(results)


# ============================================================
# CUSTOMER QUESTION ROUTER
# ============================================================

def detect_customer_intents(question: str):
    q = question.lower()

    intents = []

    product_terms = [
        "product", "catalog", "price", "cost",
        "available product", "buy", "selling"
    ]

    order_terms = [
        "order", "purchase", "ordered",
        "my recent", "order history"
    ]

    payment_terms = [
        "payment", "paid", "refund",
        "transaction", "amount paid"
    ]

    delivery_terms = [
        "delivery", "deliver", "tracking",
        "track", "shipment", "shipped",
        "where is my"
    ]

    support_terms = [
        "ticket", "support", "complaint",
        "issue", "problem", "help request"
    ]

    address_terms = [
        "address", "shipping address",
        "delivery address", "saved address"
    ]

    profile_terms = [
        "profile", "my details", "my account",
        "my information", "my name", "my email",
        "my phone", "account details"
    ]

    if any(term in q for term in product_terms):
        intents.append("products")

    if any(term in q for term in order_terms):
        intents.append("orders")

    if any(term in q for term in payment_terms):
        intents.append("payments")

    if any(term in q for term in delivery_terms):
        intents.append("deliveries")

    if any(term in q for term in support_terms):
        intents.append("support")

    if any(term in q for term in address_terms):
        intents.append("addresses")

    if any(term in q for term in profile_terms):
        intents.append("profile")

    # A general account overview returns the customer's own records.
    overview_terms = [
        "my account", "account overview",
        "my details", "show my information",
        "summarize my account"
    ]

    if any(term in q for term in overview_terms):
        intents = [
            "profile",
            "addresses",
            "orders",
            "payments",
            "deliveries",
            "support"
        ]

    # "Where is my order?" should include order and delivery information.
    if "where is my order" in q:
        intents = ["orders", "deliveries"]

    return list(dict.fromkeys(intents))


# ============================================================
# MAIN CUSTOMER ANSWER SERVICE
# ============================================================

def answer_customer_question(user_id: str, question: str):
    if not question or not question.strip():
        return {
            "answer": "Please enter a question.",
            "intent": "unknown",
            "sources": []
        }

    db = SessionLocal()

    try:
        customer = get_customer_profile(db, user_id)

        if not customer:
            return {
                "answer": "Your customer profile could not be found or is inactive.",
                "intent": "profile",
                "sources": []
            }

        intents = detect_customer_intents(question)

        if not intents:
            return {
                "answer": (
                    "I can help with your profile, saved addresses, "
                    "products, orders, payments, deliveries, and support tickets. "
                    "Please ask a question about one of these topics."
                ),
                "intent": "unknown",
                "sources": []
            }

        answer_sections = []

        for intent in intents:
            if intent == "profile":
                result = get_profile_answer(db, customer)

            elif intent == "addresses":
                result = get_address_answer(db, customer)

            elif intent == "products":
                result = get_product_answer(db, question)

            elif intent == "orders":
                result = get_orders_answer(db, customer)

            elif intent == "payments":
                result = get_payments_answer(db, customer)

            elif intent == "deliveries":
                result = get_delivery_answer(db, customer)

            elif intent == "support":
                result = get_support_answer(db, customer)

            else:
                continue

            answer_sections.append(result)

        return {
            "answer": "\n\n".join(answer_sections),
            "intent": ", ".join(intents),
            "sources": []
        }

    finally:
        db.close()
