
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

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
    User
)
from backend.services.auth_dependencies import require_admin


router = APIRouter(
    prefix="/admin/data",
    tags=["Admin - Business Data"]
)


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# SERIALIZATION HELPERS
# ============================================================

def serialize_product(product):
    return {
        "id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "price": float(product.price or 0),
        "stock_quantity": product.stock_quantity,
        "is_active": product.is_active,
        "created_at": (
            product.created_at.isoformat()
            if product.created_at else None
        )
    }


def serialize_order(order):
    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "customer_id": str(order.customer_id),
        "shipping_address_id": (
            str(order.shipping_address_id)
            if order.shipping_address_id else None
        ),
        "status": order.status,
        "total_amount": float(order.total_amount or 0),
        "created_at": (
            order.created_at.isoformat()
            if order.created_at else None
        ),
        "updated_at": (
            order.updated_at.isoformat()
            if order.updated_at else None
        )
    }


def serialize_order_item(item):
    return {
        "id": str(item.id),
        "product_id": (
            str(item.product_id)
            if item.product_id else None
        ),
        "product_name": item.product_name,
        "quantity": item.quantity,
        "unit_price": float(item.unit_price or 0),
        "subtotal": float(item.subtotal or 0)
    }


def serialize_payment(payment):
    return {
        "id": str(payment.id),
        "order_id": str(payment.order_id),
        "amount": float(payment.amount or 0),
        "payment_method": payment.payment_method,
        "transaction_reference": payment.transaction_reference,
        "status": payment.status,
        "paid_at": (
            payment.paid_at.isoformat()
            if payment.paid_at else None
        ),
        "created_at": (
            payment.created_at.isoformat()
            if payment.created_at else None
        )
    }


def serialize_delivery(delivery):
    return {
        "id": str(delivery.id),
        "order_id": str(delivery.order_id),
        "tracking_number": delivery.tracking_number,
        "courier_name": delivery.courier_name,
        "status": delivery.status,
        "shipped_at": (
            delivery.shipped_at.isoformat()
            if delivery.shipped_at else None
        ),
        "estimated_delivery_at": (
            delivery.estimated_delivery_at.isoformat()
            if delivery.estimated_delivery_at else None
        ),
        "delivered_at": (
            delivery.delivered_at.isoformat()
            if delivery.delivered_at else None
        )
    }


def serialize_ticket(ticket):
    return {
        "id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "customer_id": str(ticket.customer_id),
        "order_id": (
            str(ticket.order_id)
            if ticket.order_id else None
        ),
        "subject": ticket.subject,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": (
            ticket.created_at.isoformat()
            if ticket.created_at else None
        ),
        "updated_at": (
            ticket.updated_at.isoformat()
            if ticket.updated_at else None
        )
    }


def paginated_response(query, limit, offset, serializer):
    total = query.count()

    records = (
        query
        .order_by(query.column_descriptions[0]["entity"].id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serializer(record) for record in records]
    }


# ============================================================
# PRODUCT RETRIEVAL
# ============================================================

@router.get("/products")
def get_products(
    search: str = Query(default="", max_length=100),
    active_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = db.query(Product)

    if active_only:
        query = query.filter(Product.is_active.is_(True))

    if search.strip():
        term = f"%{search.strip()}%"

        query = query.filter(
            or_(
                Product.name.ilike(term),
                Product.sku.ilike(term),
                Product.description.ilike(term)
            )
        )

    return paginated_response(
        query, limit, offset, serialize_product
    )


# ============================================================
# ORDER RETRIEVAL
# ============================================================

@router.get("/orders")
def get_orders(
    search: str = Query(default="", max_length=100),
    status: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = db.query(Order)

    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(Order.order_number.ilike(term))

    if status.strip():
        query = query.filter(Order.status.ilike(status.strip()))

    return paginated_response(
        query, limit, offset, serialize_order
    )


@router.get("/orders/{order_id}")
def get_order_details(
    order_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )

    payments = (
        db.query(Payment)
        .filter(Payment.order_id == order.id)
        .all()
    )

    delivery = (
        db.query(Delivery)
        .filter(Delivery.order_id == order.id)
        .first()
    )

    customer = (
        db.query(Customer)
        .filter(Customer.id == order.customer_id)
        .first()
    )

    customer_user = None

    if customer:
        customer_user = (
            db.query(User)
            .filter(User.id == customer.user_id)
            .first()
        )

    address = None

    if order.shipping_address_id:
        address = (
            db.query(CustomerAddress)
            .filter(
                CustomerAddress.id == order.shipping_address_id
            )
            .first()
        )

    address_data = None

    if address:
        address_data = {
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country
        }

    customer_data = None

    if customer:
        customer_data = {
            "customer_id": str(customer.id),
            "full_name": customer.full_name,
            "phone": customer.phone,
            "email": (
                customer_user.email
                if customer_user else None
            )
        }

    return {
        "order": serialize_order(order),
        "customer": customer_data,
        "shipping_address": address_data,
        "items": [
            serialize_order_item(item)
            for item in items
        ],
        "payments": [
            serialize_payment(payment)
            for payment in payments
        ],
        "delivery": (
            serialize_delivery(delivery)
            if delivery else None
        )
    }


# ============================================================
# PAYMENT RETRIEVAL
# ============================================================

@router.get("/payments")
def get_payments(
    status: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = db.query(Payment)

    if status.strip():
        query = query.filter(
            Payment.status.ilike(status.strip())
        )

    return paginated_response(
        query, limit, offset, serialize_payment
    )


# ============================================================
# DELIVERY RETRIEVAL
# ============================================================

@router.get("/deliveries")
def get_deliveries(
    status: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = db.query(Delivery)

    if status.strip():
        query = query.filter(
            Delivery.status.ilike(status.strip())
        )

    return paginated_response(
        query, limit, offset, serialize_delivery
    )


# ============================================================
# SUPPORT TICKET RETRIEVAL
# ============================================================

@router.get("/tickets")
def get_support_tickets(
    search: str = Query(default="", max_length=100),
    status: str = "",
    priority: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = db.query(SupportTicket)

    if search.strip():
        term = f"%{search.strip()}%"

        query = query.filter(
            or_(
                SupportTicket.ticket_number.ilike(term),
                SupportTicket.subject.ilike(term),
                SupportTicket.description.ilike(term)
            )
        )

    if status.strip():
        query = query.filter(
            SupportTicket.status.ilike(status.strip())
        )

    if priority.strip():
        query = query.filter(
            SupportTicket.priority.ilike(priority.strip())
        )

    return paginated_response(
        query, limit, offset, serialize_ticket
    )


@router.get("/tickets/{ticket_id}")
def get_ticket_details(
    ticket_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    ticket = (
        db.query(SupportTicket)
        .filter(SupportTicket.id == ticket_id)
        .first()
    )

    if not ticket:
        raise HTTPException(
            status_code=404,
            detail="Support ticket not found"
        )

    customer = (
        db.query(Customer)
        .filter(Customer.id == ticket.customer_id)
        .first()
    )

    user = None

    if customer:
        user = (
            db.query(User)
            .filter(User.id == customer.user_id)
            .first()
        )

    return {
        "ticket": serialize_ticket(ticket),
        "customer": (
            {
                "customer_id": str(customer.id),
                "full_name": customer.full_name,
                "phone": customer.phone,
                "email": user.email if user else None
            }
            if customer else None
        )
    }
