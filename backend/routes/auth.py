
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field

from backend.database import SessionLocal
from backend.models import User, Customer

from backend.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token
)

from backend.services.auth_dependencies import (
    get_current_user,
    require_admin,
    require_customer
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# --------------------------------------------------
# CUSTOMER SIGNUP REQUEST
# --------------------------------------------------

class CustomerSignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------
# LOGIN REQUEST
# --------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# --------------------------------------------------
# CREATE USER REQUEST (ADMIN ONLY)
# --------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


# --------------------------------------------------
# CUSTOMER SIGNUP API
# --------------------------------------------------

@router.post("/signup", status_code=status.HTTP_201_CREATED)
def customer_signup(request: CustomerSignupRequest):

    db = SessionLocal()

    try:
        username = request.username.strip()
        full_name = request.full_name.strip()

        if not username or not full_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username and full name cannot be empty"
            )

        # Check existing username or email
        existing_user = (
            db.query(User)
            .filter(
                (User.username == username) |
                (User.email == request.email)
            )
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email already exists"
            )

        # Create customer login account
        new_user = User(
            id=str(uuid4()),
            username=username,
            email=request.email,
            hashed_password=hash_password(request.password),
            role="customer",
            is_active=True
        )

        db.add(new_user)
        db.flush()

        # Create linked customer business profile
        new_customer = Customer(
            id=str(uuid4()),
            user_id=new_user.id,
            full_name=full_name,
            phone=request.phone.strip() if request.phone else None,
            is_active=True
        )

        db.add(new_customer)

        # Save both records together
        db.commit()

        db.refresh(new_user)
        db.refresh(new_customer)

        return {
            "message": "Customer registered successfully",
            "user": {
                "id": str(new_user.id),
                "username": new_user.username,
                "email": new_user.email,
                "role": new_user.role
            },
            "customer": {
                "id": str(new_customer.id),
                "full_name": new_customer.full_name,
                "phone": new_customer.phone
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Customer registration failed"
        )

    finally:
        db.close()


# --------------------------------------------------
# LOGIN API
# --------------------------------------------------

@router.post("/login")
def login(request: LoginRequest):

    db = SessionLocal()

    try:
        # Find user by email
        user = (
            db.query(User)
            .filter(User.email == request.email)
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Check active status
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is inactive"
            )

        # Verify password
        if not verify_password(
            request.password,
            user.hashed_password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Generate JWT
        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role
        )

        return {
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }

    finally:
        db.close()


# --------------------------------------------------
# CURRENT USER PROFILE
# --------------------------------------------------

@router.get("/me")
def get_my_profile(
    current_user: dict = Depends(get_current_user)
):

    return current_user


# --------------------------------------------------
# ADMIN TEST API
# --------------------------------------------------

@router.get("/admin-test")
def admin_test(
    current_user: dict = Depends(require_admin)
):

    return {
        "message": "Admin access granted",
        "user": current_user
    }


# --------------------------------------------------
# CUSTOMER TEST API
# --------------------------------------------------

@router.get("/customer-test")
def customer_test(
    current_user: dict = Depends(require_customer)
):

    return {
        "message": "Customer access granted",
        "user": current_user
    }


# --------------------------------------------------
# CREATE NORMAL USER (ADMIN ONLY)
# --------------------------------------------------

@router.post("/create-user")
def create_user(
    request: CreateUserRequest,
    current_user: dict = Depends(require_admin)
):

    db = SessionLocal()

    try:
        username = request.username.strip()

        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username cannot be empty"
            )

        existing_user = (
            db.query(User)
            .filter(
                (User.username == username) |
                (User.email == request.email)
            )
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email already exists"
            )

        new_user = User(
            id=str(uuid4()),
            username=username,
            email=request.email,
            hashed_password=hash_password(request.password),
            role="user",
            is_active=True
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "message": "User created successfully",
            "user": {
                "id": str(new_user.id),
                "username": new_user.username,
                "email": new_user.email,
                "role": new_user.role
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User creation failed"
        )

    finally:
        db.close()
