
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import SessionLocal
from backend.models import (
    Customer,
    Product,
    Order,
    Payment,
    SupportTicket
)
from backend.services.auth_dependencies import require_admin


router = APIRouter(
    prefix="/admin/dashboard",
    tags=["Admin - Dashboard"]
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
# DASHBOARD STATISTICS
# ============================================================

@router.get("/stats")
def get_dashboard_statistics(
    db: Session = Depends(get_db),
    admin=Depends(require_admin)
):
    # --------------------------------------------------------
    # CUSTOMER STATISTICS
    # --------------------------------------------------------

    total_customers = db.query(Customer).count()

    active_customers = (
        db.query(Customer)
        .filter(Customer.is_active.is_(True))
        .count()
    )

    inactive_customers = (
        db.query(Customer)
        .filter(Customer.is_active.is_(False))
        .count()
    )

    # --------------------------------------------------------
    # PRODUCT STATISTICS
    # --------------------------------------------------------

    total_products = db.query(Product).count()

    active_products = (
        db.query(Product)
        .filter(Product.is_active.is_(True))
        .count()
    )

    low_stock_products = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            Product.stock_quantity <= 5
        )
        .count()
    )

    # --------------------------------------------------------
    # ORDER STATISTICS
    # --------------------------------------------------------

    total_orders = db.query(Order).count()

    order_status_rows = (
        db.query(
            Order.status,
            func.count(Order.id)
        )
        .group_by(Order.status)
        .all()
    )

    orders_by_status = {
        str(status or "Unknown"): count
        for status, count in order_status_rows
    }

    # --------------------------------------------------------
    # PAYMENT AND REVENUE STATISTICS
    # --------------------------------------------------------

    total_payments = db.query(Payment).count()

    paid_payments = (
        db.query(Payment)
        .filter(Payment.paid_at.isnot(None))
        .count()
    )

    total_revenue = (
        db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        )
        .filter(Payment.paid_at.isnot(None))
        .scalar()
    )

    # --------------------------------------------------------
    # SUPPORT TICKET STATISTICS
    # --------------------------------------------------------

    total_tickets = db.query(SupportTicket).count()

    ticket_status_rows = (
        db.query(
            SupportTicket.status,
            func.count(SupportTicket.id)
        )
        .group_by(SupportTicket.status)
        .all()
    )

    tickets_by_status = {
        str(status or "Unknown"): count
        for status, count in ticket_status_rows
    }

    closed_statuses = ["closed", "resolved"]

    open_tickets = (
        db.query(SupportTicket)
        .filter(
            func.lower(SupportTicket.status).notin_(
                closed_statuses
            )
        )
        .count()
    )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "customers": {
            "total": total_customers,
            "active": active_customers,
            "inactive": inactive_customers
        },

        "products": {
            "total": total_products,
            "active": active_products,
            "low_stock": low_stock_products,
            "low_stock_threshold": 5
        },

        "orders": {
            "total": total_orders,
            "by_status": orders_by_status
        },

        "payments": {
            "total": total_payments,
            "paid": paid_payments,
            "total_revenue": float(total_revenue or 0)
        },

        "support_tickets": {
            "total": total_tickets,
            "open": open_tickets,
            "by_status": tickets_by_status
        }
    }
