import json
import re
import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import (
    User,
    Customer,
    CustomerAddress,
    Product,
    Order,
    OrderItem,
    ChatHistory,
)
from backend.services.llm_service import call_ollama


# ============================================================
# ORDER INTENT
# ============================================================

def is_order_request(question: str) -> bool:

    text = question.lower().strip()

    history_phrases = [
        "my orders",
        "order history",
        "previous order",
        "previous orders",
        "recent orders",
        "order status",
        "track my order",
        "where is my order",
        "what is my order",
        "order id",
        "order number",
    ]

    if any(phrase in text for phrase in history_phrases):
        return False

    order_phrases = [
        "i want to order",
        "i want to buy",
        "i would like to order",
        "i would like to buy",
        "place an order",
        "purchase",
        "buy",
        "order a",
        "order the",
        "i need to order",
        "add to cart",
    ]

    return any(phrase in text for phrase in order_phrases)


def get_quantity(question: str):

    text = question.lower().strip()

    match = re.search(
        r"\b(\d+)\s*(?:pieces?|items?|units?|qty|quantity)?\b",
        text
    )

    if match:
        quantity = int(match.group(1))
        if quantity > 0:
            return quantity

    if re.fullmatch(r"\d+", text):
        quantity = int(text)
        if quantity > 0:
            return quantity

    return None


# ============================================================
# PRODUCT SELECTION
# ============================================================

def find_product(products, question: str):

    text = question.lower()

    for product in products:
        product_name = product.name.lower()
        if product_name in text:
            return product

    question_words = [
        w for w in re.findall(r"[a-zA-Z0-9]+", text)
        if len(w) > 2
    ]

    best_match = None
    best_score = 0

    for product in products:
        product_words = set(
            re.findall(r"[a-zA-Z0-9]+", product.name.lower())
        )

        matches = sum(
            1 for w in question_words
            if any(w in pw or pw in w for pw in product_words)
        )

        if matches > best_score:
            best_score = matches
            best_match = product

    if best_score >= 1:
        return best_match

    return None


def get_active_products(db: Session):

    return (
        db.query(Product)
        .filter(Product.is_active == True)
        .order_by(Product.name)
        .all()
    )


def get_product_options(products):

    if not products:
        return "There are currently no active products available."

    lines = ["Here are the available products:"]

    for index, product in enumerate(products, start=1):
        lines.append(
            f"{index}. {product.name} - ₹{product.price} "
            f"(Available stock: {product.stock_quantity})"
        )

    lines.append("\nPlease enter the product name you want to order.")

    return "\n".join(lines)


def select_product(products, question: str):

    product = find_product(products, question)

    if product:
        return product

    text = question.strip()

    if text.isdigit():
        index = int(text) - 1

        if 0 <= index < len(products):
            return products[index]

    return None


# ============================================================
# CUSTOMER AND ADDRESS
# ============================================================

def get_customer(db: Session, user_id: str):

    return (
        db.query(Customer)
        .filter(
            Customer.user_id == user_id,
            Customer.is_active == True
        )
        .first()
    )


def get_customer_addresses(db: Session, customer_id: str):

    return (
        db.query(CustomerAddress)
        .filter(CustomerAddress.customer_id == customer_id)
        .order_by(
            CustomerAddress.is_default.desc(),
            CustomerAddress.created_at.desc()
        )
        .all()
    )


def format_address(address):

    parts = [
        address.address_line1,
        address.address_line2,
        address.city,
        address.state,
        address.postal_code,
        address.country,
    ]

    return ", ".join(
        str(part).strip()
        for part in parts
        if part and str(part).strip()
    )


def address_options(addresses):

    if not addresses:
        return (
            "I couldn't find a saved shipping address. "
            "Please enter your complete shipping address."
        )

    lines = ["Please select your shipping address:"]

    for index, address in enumerate(addresses, start=1):
        address_type = address.address_type or "Address"
        lines.append(
            f"{index}. {address_type}: {format_address(address)}"
        )

    lines.append("\nEnter the address number you want to use.")

    return "\n".join(lines)


def choose_address(addresses, question: str):

    text = question.strip()

    if not text.isdigit():
        return None

    index = int(text) - 1

    if 0 <= index < len(addresses):
        return addresses[index]

    return None


# ============================================================
# ADDRESS PARSING
# ============================================================

def _heuristic_parse_address(address_text: str):
    """
    Try to parse a comma-separated address without calling the LLM.
    Handles inputs like:
        "ramalayam street, kakinada, andhra pradesh, 533001, india"
    Returns a dict or None.
    """
    parts = [p.strip() for p in address_text.split(",") if p.strip()]

    if len(parts) < 3:
        return None

    address_line1 = parts[0]
    city = parts[1]

    postal_code = ""
    state = ""
    country = "India"

    for part in parts[2:]:
        if re.fullmatch(r"\d{6}", part):
            postal_code = part
        elif part.lower() in ("india", "in"):
            country = "India"
        elif not state:
            state = part

    if len(parts) >= 4 and not state:
        state = parts[2]

    if not address_line1 or not city:
        return None

    return {
        "address_line1": address_line1,
        "address_line2": "",
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
    }


def parse_address_with_ollama(address_text: str):

    # Fast path: try heuristic parser first (no LLM call needed)
    heuristic = _heuristic_parse_address(address_text)

    if heuristic:
        print("[ADDRESS PARSER] Fast-path heuristic succeeded:", heuristic)
        return heuristic

    # Slow path: ask the LLM
    prompt = f"""
Extract the shipping address from the user's message.

Return ONLY valid JSON with these keys:
{{
    "address_line1": "",
    "address_line2": "",
    "city": "",
    "state": "",
    "postal_code": "",
    "country": ""
}}

Do not invent missing information.
Use empty strings for missing fields.
Do not add any other text, explanation, or markdown.

User address:
{address_text}
"""

    raw = ""

    try:
        from openai import OpenAI
        import os

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured address data. "
                        "Reply with JSON only, no prose."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()

    except Exception as error:
        print("[ADDRESS PARSER] OpenAI call failed:", error)

        try:
            raw = call_ollama(prompt).strip()
        except Exception:
            return None

    if not raw:
        return None

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        print("[ADDRESS PARSER] No JSON object found in response:", raw[:200])
        return None

    try:
        data = json.loads(match.group(0))
    except Exception as error:
        print("[ADDRESS PARSER] JSON parse failed:", error, "| raw:", raw[:200])
        return None

    if not isinstance(data, dict):
        return None

    cleaned = {
        "address_line1": str(data.get("address_line1", "")).strip(),
        "address_line2": str(data.get("address_line2", "")).strip(),
        "city": str(data.get("city", "")).strip(),
        "state": str(data.get("state", "")).strip(),
        "postal_code": str(data.get("postal_code", "")).strip(),
        "country": str(data.get("country", "")).strip() or "India",
    }

    if not cleaned["address_line1"] or not cleaned["city"]:
        print("[ADDRESS PARSER] Missing required fields:", cleaned)
        return None

    return cleaned


def save_new_address(db: Session, customer_id: str, address_data: dict):

    address = CustomerAddress(
        id=str(uuid.uuid4()),
        customer_id=customer_id,
        address_type="Shipping",
        address_line1=address_data["address_line1"],
        address_line2=address_data.get("address_line2", ""),
        city=address_data["city"],
        state=address_data["state"],
        postal_code=address_data["postal_code"],
        country=address_data["country"],
        is_default=False,
    )

    db.add(address)
    db.flush()

    return address


# ============================================================
# PENDING ORDER STATE
# ============================================================

ORDER_DRAFT_PREFIX = "order_draft:"


def get_pending_order_state(db: Session, conversation_id: str, user_id: str):

    if not conversation_id:
        return None

    history = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == user_id,
            ChatHistory.order_state.like(f"{ORDER_DRAFT_PREFIX}%")
        )
        .order_by(ChatHistory.created_at.desc())
        .first()
    )

    if not history:
        return None

    try:
        state_json = history.order_state[len(ORDER_DRAFT_PREFIX):]
        return json.loads(state_json)
    except Exception:
        return None


def encode_order_state(state):

    if not state:
        return None

    return ORDER_DRAFT_PREFIX + json.dumps(state)


# ============================================================
# ORDER CONFIRMATION
# ============================================================

def is_confirmation(question: str):

    text = question.lower().strip()

    confirmations = [
        "yes", "yes confirm", "confirm", "confirm order",
        "place order", "proceed", "ok", "okay", "sure",
        "go ahead",
    ]

    return text in confirmations


def is_cancellation(question: str):

    text = question.lower().strip()

    cancellations = [
        "no", "cancel", "cancel order", "don't order",
        "do not order", "stop", "no thanks",
    ]

    return text in cancellations


def create_order_number():

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:5].upper()

    return f"ORD{timestamp}{suffix}"


# ============================================================
# ORDER SUMMARY
# ============================================================

def build_order_summary(product, quantity, address):

    total = Decimal(str(product.price)) * quantity

    return (
        "Please review your order:\n\n"
        f"Product: {product.name}\n"
        f"Quantity: {quantity}\n"
        f"Unit price: ₹{product.price}\n"
        f"Total amount: ₹{total:.2f}\n\n"
        f"Shipping address:\n{format_address(address)}\n\n"
        "Would you like me to confirm and place this order? "
        "Please reply Yes or No."
    )


# ============================================================
# MAIN CUSTOMER ORDER AGENT
# ============================================================

def handle_customer_order(
    db: Session,
    user_id: str,
    conversation_id: str,
    question: str
):

    state = get_pending_order_state(
        db,
        conversation_id,
        user_id
    )

    question = question.strip()

    if not state and not is_order_request(question):
        return None

    if not state:
        state = {"stage": "product"}

    # --------------------------------------------------------
    # CANCEL ORDER DRAFT
    # --------------------------------------------------------

    if is_cancellation(question):
        return {
            "answer": "Your pending order has been cancelled. No order was placed.",
            "intent": "order",
            "order_state": None,
        }

    # --------------------------------------------------------
    # CUSTOMER VALIDATION
    # --------------------------------------------------------

    customer = get_customer(db, user_id)

    if not customer:
        return {
            "answer": (
                "I couldn't find an active customer profile "
                "for your account. Please contact support."
            ),
            "intent": "order",
            "order_state": None,
        }

    # --------------------------------------------------------
    # GET AVAILABLE PRODUCTS
    # --------------------------------------------------------

    products = get_active_products(db)

    if not products:
        return {
            "answer": "There are currently no products available for ordering.",
            "intent": "order",
            "order_state": None,
        }

    # --------------------------------------------------------
    # PRODUCT SELECTION
    # --------------------------------------------------------

    if state.get("stage") == "product":

        selected_product = select_product(products, question)

        if not selected_product:
            return {
                "answer": get_product_options(products),
                "intent": "order",
                "order_state": state,
            }

        if selected_product.stock_quantity <= 0:
            return {
                "answer": (
                    f"Sorry, {selected_product.name} is currently out of stock. "
                    "Please select another product."
                ),
                "intent": "order",
                "order_state": state,
            }

        state["product_id"] = selected_product.id
        state["stage"] = "quantity"

        return {
            "answer": (
                f"You selected {selected_product.name}.\n"
                f"Price: ₹{selected_product.price}\n"
                f"Available stock: {selected_product.stock_quantity}\n\n"
                "How many units would you like to order?"
            ),
            "intent": "order",
            "order_state": state,
        }

    # --------------------------------------------------------
    # QUANTITY
    # --------------------------------------------------------

    if state.get("stage") == "quantity":

        quantity = get_quantity(question)

        if not quantity:
            return {
                "answer": "Please enter a valid quantity, such as 1, 2, or 3.",
                "intent": "order",
                "order_state": state,
            }

        product = (
            db.query(Product)
            .filter(
                Product.id == state["product_id"],
                Product.is_active == True
            )
            .first()
        )

        if not product:
            return {
                "answer": "This product is no longer available. Please start your order again.",
                "intent": "order",
                "order_state": None,
            }

        if quantity > product.stock_quantity:
            return {
                "answer": (
                    f"Only {product.stock_quantity} units of "
                    f"{product.name} are currently available. "
                    "Please enter a smaller quantity."
                ),
                "intent": "order",
                "order_state": state,
            }

        state["quantity"] = quantity
        state["stage"] = "address"

    # --------------------------------------------------------
    # SHIPPING ADDRESS
    # --------------------------------------------------------

    if state.get("stage") == "address":

        addresses = get_customer_addresses(db, customer.id)

        if addresses:
            selected_address = choose_address(addresses, question)

            if not selected_address and len(addresses) == 1:
                selected_address = addresses[0]

            if not selected_address:
                return {
                    "answer": address_options(addresses),
                    "intent": "order",
                    "order_state": state,
                }

            state["address_id"] = selected_address.id

        else:
            address_data = parse_address_with_ollama(question)

            if not address_data:
                return {
                    "answer": (
                        "Please enter your complete shipping address, "
                        "including street, city, state, postal code, and country."
                    ),
                    "intent": "order",
                    "order_state": state,
                }

            try:
                selected_address = save_new_address(
                    db, customer.id, address_data
                )
                state["address_id"] = selected_address.id

            except Exception:
                db.rollback()
                return {
                    "answer": (
                        "I couldn't save that shipping address. "
                        "Please try entering it again."
                    ),
                    "intent": "order",
                    "order_state": state,
                }

        state["stage"] = "confirmation"

        product = (
            db.query(Product)
            .filter(Product.id == state["product_id"])
            .first()
        )

        if not product:
            return {
                "answer": "The selected product is no longer available. Please start again.",
                "intent": "order",
                "order_state": None,
            }

        selected_address = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.id == state["address_id"],
                CustomerAddress.customer_id == customer.id
            )
            .first()
        )

        if not selected_address:
            return {
                "answer": "The selected shipping address could not be found. Please start again.",
                "intent": "order",
                "order_state": None,
            }

        return {
            "answer": build_order_summary(
                product,
                state["quantity"],
                selected_address
            ),
            "intent": "order",
            "order_state": state,
        }

    # --------------------------------------------------------
    # FINAL ORDER CONFIRMATION
    # --------------------------------------------------------

    if state.get("stage") == "confirmation":

        if not is_confirmation(question):
            return {
                "answer": (
                    "Your order has not been placed yet. "
                    "Please reply Yes to confirm or No to cancel."
                ),
                "intent": "order",
                "order_state": state,
            }

        product = (
            db.query(Product)
            .filter(
                Product.id == state["product_id"],
                Product.is_active == True
            )
            .with_for_update()
            .first()
        )

        if not product:
            return {
                "answer": "The selected product is no longer available. Your order was not placed.",
                "intent": "order",
                "order_state": None,
            }

        quantity = int(state["quantity"])

        if quantity <= 0 or product.stock_quantity < quantity:
            return {
                "answer": (
                    f"Sorry, only {product.stock_quantity} units of "
                    f"{product.name} are currently available. "
                    "Your order was not placed."
                ),
                "intent": "order",
                "order_state": None,
            }

        address = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.id == state["address_id"],
                CustomerAddress.customer_id == customer.id
            )
            .first()
        )

        if not address:
            return {
                "answer": "Your shipping address could not be found. Your order was not placed.",
                "intent": "order",
                "order_state": None,
            }

        unit_price = Decimal(str(product.price))
        subtotal = unit_price * quantity

        order = Order(
            id=str(uuid.uuid4()),
            order_number=create_order_number(),
            customer_id=customer.id,
            shipping_address_id=address.id,
            status="pending",
            total_amount=subtotal,
        )

        db.add(order)
        db.flush()

        order_item = OrderItem(
            id=str(uuid.uuid4()),
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal,
        )

        db.add(order_item)
        product.stock_quantity -= quantity

        try:
            db.commit()
        except Exception:
            db.rollback()
            return {
                "answer": (
                    "Something went wrong while placing your order. "
                    "No order was confirmed. Please try again."
                ),
                "intent": "order",
                "order_state": state,
            }

        return {
            "answer": (
                "Your order has been placed successfully!\n\n"
                f"Order ID: {order.order_number}\n"
                f"Product: {product.name}\n"
                f"Quantity: {quantity}\n"
                f"Total amount: ₹{subtotal:.2f}\n"
                "Order status: Pending\n\n"
                "You can ask me for your order details anytime."
            ),
            "intent": "order",
            "order_state": None,
        }

    return {
        "answer": "Let's start your order again. Which product would you like to order?",
        "intent": "order",
        "order_state": {"stage": "product"},
    }