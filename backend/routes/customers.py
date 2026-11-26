
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.database import SessionLocal
from backend.models import User, Customer, CustomerAddress

from backend.services.auth_dependencies import require_admin

from backend.schemas.customer_schema import (
    CustomerUpdateRequest,
    CustomerStatusRequest,
    CustomerAddressCreateRequest,
    CustomerAddressUpdateRequest
)


router = APIRouter(
    prefix="/customers",
    tags=["Customer Management"]
)


# ============================================================
# DATABASE SESSION
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CUSTOMER SERIALIZATION
# ============================================================

def serialize_customer(customer, user):
    return {
        "id": customer.id,
        "user_id": customer.user_id,
        "full_name": customer.full_name,
        "phone": customer.phone,
        "email": user.email if user else None,
        "username": user.username if user else None,
        "is_active": customer.is_active,
        "created_at": customer.created_at
    }


# ============================================================
# ADDRESS SERIALIZATION
# ============================================================

def serialize_address(address):
    return {
        "id": address.id,
        "customer_id": address.customer_id,
        "address_type": address.address_type,
        "address_line1": address.address_line1,
        "address_line2": address.address_line2,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country,
        "is_default": address.is_default,
        "created_at": address.created_at
    }


# ============================================================
# GET ALL CUSTOMERS
# ============================================================

@router.get("/")
def get_all_customers(
    q: str = Query(default="", description="Search by name, phone, email or username"),
    is_active: bool = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    query = (
        db.query(Customer, User)
        .join(User, Customer.user_id == User.id)
    )

    if q.strip():
        search = f"%{q.strip()}%"

        query = query.filter(
            or_(
                Customer.full_name.ilike(search),
                Customer.phone.ilike(search),
                User.email.ilike(search),
                User.username.ilike(search)
            )
        )

    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)

    total = query.count()

    results = (
        query
        .order_by(Customer.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    customers = [
        serialize_customer(customer, user)
        for customer, user in results
    ]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "customers": customers
    }


# ============================================================
# GET CUSTOMER DETAILS
# ============================================================

@router.get("/{customer_id}")
def get_customer_details(
    customer_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
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
        .order_by(CustomerAddress.is_default.desc())
        .all()
    )

    customer_data = serialize_customer(customer, user)

    customer_data["addresses"] = [
        serialize_address(address)
        for address in addresses
    ]

    return customer_data


# ============================================================
# UPDATE CUSTOMER INFORMATION
# ============================================================

@router.patch("/{customer_id}")
def update_customer(
    customer_id: str,
    request: CustomerUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
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

    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)

    user = (
        db.query(User)
        .filter(User.id == customer.user_id)
        .first()
    )

    return {
        "message": "Customer information updated successfully",
        "customer": serialize_customer(customer, user)
    }


# ============================================================
# ACTIVATE / DEACTIVATE CUSTOMER
# ============================================================

@router.patch("/{customer_id}/status")
def update_customer_status(
    customer_id: str,
    request: CustomerStatusRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
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
            detail="Linked user account not found"
        )

    # Keep both account statuses synchronized.
    customer.is_active = request.is_active
    user.is_active = request.is_active

    db.commit()

    return {
        "message": (
            "Customer activated successfully"
            if request.is_active
            else "Customer deactivated successfully"
        ),
        "customer_id": customer.id,
        "is_active": customer.is_active
    }


# ============================================================
# GET CUSTOMER ADDRESSES
# ============================================================

@router.get("/{customer_id}/addresses")
def get_customer_addresses(
    customer_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
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

    addresses = (
        db.query(CustomerAddress)
        .filter(CustomerAddress.customer_id == customer_id)
        .order_by(CustomerAddress.is_default.desc())
        .all()
    )

    return {
        "customer_id": customer_id,
        "total": len(addresses),
        "addresses": [
            serialize_address(address)
            for address in addresses
        ]
    }


# ============================================================
# ADD CUSTOMER ADDRESS
# ============================================================

@router.post("/{customer_id}/addresses", status_code=201)
def add_customer_address(
    customer_id: str,
    request: CustomerAddressCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
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

    address_data = request.model_dump()

    if address_data["is_default"]:
        db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == customer_id
        ).update(
            {"is_default": False},
            synchronize_session=False
        )

    address = CustomerAddress(
        customer_id=customer_id,
        **address_data
    )

    db.add(address)
    db.commit()
    db.refresh(address)

    return {
        "message": "Customer address added successfully",
        "address": serialize_address(address)
    }


# ============================================================
# UPDATE CUSTOMER ADDRESS
# ============================================================

@router.patch("/{customer_id}/addresses/{address_id}")
def update_customer_address(
    customer_id: str,
    address_id: str,
    request: CustomerAddressUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    address = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id
        )
        .first()
    )

    if not address:
        raise HTTPException(
            status_code=404,
            detail="Customer address not found"
        )

    update_data = request.model_dump(exclude_unset=True)

    if update_data.get("is_default") is True:
        db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == customer_id
        ).update(
            {"is_default": False},
            synchronize_session=False
        )

    for field, value in update_data.items():
        setattr(address, field, value)

    db.commit()
    db.refresh(address)

    return {
        "message": "Customer address updated successfully",
        "address": serialize_address(address)
    }


# ============================================================
# DELETE CUSTOMER ADDRESS
# ============================================================

@router.delete("/{customer_id}/addresses/{address_id}")
def delete_customer_address(
    customer_id: str,
    address_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):

    address = (
        db.query(CustomerAddress)
        .filter(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id
        )
        .first()
    )

    if not address:
        raise HTTPException(
            status_code=404,
            detail="Customer address not found"
        )

    db.delete(address)
    db.commit()

    return {
        "message": "Customer address deleted successfully",
        "address_id": address_id
    }
