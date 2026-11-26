
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.database import SessionLocal
from backend.models import (
    Customer,
    CustomerAddress,
    Order,
    SupportTicket,
    User
)
from backend.services.auth_dependencies import require_admin


router = APIRouter(
    prefix="/admin/customers",
    tags=["Admin - Customer Management"]
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
# REQUEST SCHEMAS
# ============================================================

class CustomerStatusRequest(BaseModel):
    is_active: bool


# ============================================================
# SERIALIZATION HELPERS
# ============================================================

def serialize_customer(customer, user):
    return {
        "customer_id": str(customer.id),
        "user_id": str(customer.user_id),
        "full_name": customer.full_name,
        "username": user.username,
        "email": user.email,
        "phone": customer.phone,
        "is_active": customer.is_active,
        "created_at": (
            customer.created_at.isoformat()
            if customer.created_at else None
        )
    }


# ============================================================
# GET ALL CUSTOMERS
# ============================================================

@router.get("/")
def get_all_customers(
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    query = (
        db.query(Customer, User)
        .join(User, Customer.user_id == User.id)
    )

    if search.strip():
        search_term = f"%{search.strip()}%"

        query = query.filter(
            or_(
                Customer.full_name.ilike(search_term),
                Customer.phone.ilike(search_term),
                User.username.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    total = query.count()

    results = (
        query
        .order_by(Customer.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    customers = [
        serialize_customer(customer, user)
        for customer, user in results
    ]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "customers": customers
    }


# ============================================================
# GET CUSTOMER DETAILS
# ============================================================

@router.get("/{customer_id}")
def get_customer_details(
    customer_id: str,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    result = (
        db.query(Customer, User)
        .join(User, Customer.user_id == User.id)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    customer, user = result

    addresses = (
        db.query(CustomerAddress)
        .filter(CustomerAddress.customer_id == customer.id)
        .all()
    )

    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.customer_id == customer.id)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )

    address_data = [
        {
            "id": str(address.id),
            "address_type": address.address_type,
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
            "is_default": address.is_default
        }
        for address in addresses
    ]

    order_data = [
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": float(order.total_amount or 0),
            "created_at": (
                order.created_at.isoformat()
                if order.created_at else None
            )
        }
        for order in orders
    ]

    ticket_data = [
        {
            "id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
            "subject": ticket.subject,
            "status": ticket.status,
            "priority": ticket.priority,
            "created_at": (
                ticket.created_at.isoformat()
                if ticket.created_at else None
            )
        }
        for ticket in tickets
    ]

    return {
        "customer": serialize_customer(customer, user),
        "addresses": address_data,
        "orders": order_data,
        "support_tickets": ticket_data,
        "summary": {
            "total_addresses": len(address_data),
            "total_orders": len(order_data),
            "total_support_tickets": len(ticket_data)
        }
    }


# ============================================================
# ACTIVATE / DEACTIVATE CUSTOMER
# ============================================================

@router.patch("/{customer_id}/status")
def update_customer_status(
    customer_id: str,
    payload: CustomerStatusRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    user = (
        db.query(User)
        .filter(User.id == customer.user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Customer login account not found"
        )

    customer.is_active = payload.is_active
    user.is_active = payload.is_active

    db.commit()
    db.refresh(customer)

    return {
        "message": (
            "Customer activated successfully"
            if payload.is_active
            else "Customer deactivated successfully"
        ),
        "customer_id": str(customer.id),
        "is_active": customer.is_active
    }
