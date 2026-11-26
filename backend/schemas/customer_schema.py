
from pydantic import BaseModel, Field
from typing import Optional


# ============================================================
# CUSTOMER UPDATE
# ============================================================

class CustomerUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2)
    phone: Optional[str] = None


# ============================================================
# CUSTOMER ACCOUNT STATUS
# ============================================================

class CustomerStatusRequest(BaseModel):
    is_active: bool


# ============================================================
# CUSTOMER ADDRESS CREATE
# ============================================================

class CustomerAddressCreateRequest(BaseModel):
    address_type: str = Field(min_length=1)
    address_line1: str = Field(min_length=1)
    address_line2: Optional[str] = None
    city: str = Field(min_length=1)
    state: str = Field(min_length=1)
    postal_code: str = Field(min_length=1)
    country: str = "India"
    is_default: bool = False


# ============================================================
# CUSTOMER ADDRESS UPDATE
# ============================================================

class CustomerAddressUpdateRequest(BaseModel):
    address_type: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    is_default: Optional[bool] = None
