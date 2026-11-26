from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    Boolean,
    ForeignKey,
    Numeric
)
from sqlalchemy.sql import func

from backend.database import Base


# --------------------------------------------------
# DOCUMENT MODEL
# --------------------------------------------------

class Document(Base):

    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)

    filename = Column(String, nullable=False)

    file_type = Column(String, nullable=False)

    file_path = Column(String, nullable=False)

    upload_date = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    total_chunks = Column(Integer, default=0)

    version_number = Column(Integer, default=1, nullable=False)

    # Access control — new columns
    access_scope = Column(
        String(32),
        nullable=False,
        default="company_policy",
        index=True
    )

    target_user_id = Column(
        String,
        nullable=True,
        index=True
    )


# --------------------------------------------------
# DOCUMENT VERSION HISTORY MODEL
# --------------------------------------------------

class DocumentVersion(Base):

    __tablename__ = "document_versions"

    id = Column(String, primary_key=True, index=True)

    document_id = Column(
        String,
        ForeignKey("documents.id"),
        nullable=False,
        index=True
    )

    version_number = Column(Integer, nullable=False)

    filename = Column(String, nullable=False)

    file_type = Column(String, nullable=False)

    file_path = Column(String, nullable=False)

    replaced_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# CHAT HISTORY MODEL
# --------------------------------------------------

class ChatHistory(Base):

    __tablename__ = "chat_history"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    conversation_id = Column(String, index=True, nullable=False)

    user_id = Column(String, nullable=True, index=True)

    document_id = Column(String, nullable=True)

    order_state = Column(Text, nullable=True)

    question = Column(Text, nullable=False)

    answer = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# USER MODEL - AUTHENTICATION
# --------------------------------------------------

class User(Base):

    __tablename__ = "users"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    username = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    hashed_password = Column(
        String,
        nullable=False
    )

    role = Column(
        String,
        nullable=False,
        default="customer"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# CUSTOMER MODEL
# --------------------------------------------------

class Customer(Base):

    __tablename__ = "customers"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    user_id = Column(
        String,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True
    )

    full_name = Column(String, nullable=False)

    phone = Column(String, nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )


# --------------------------------------------------
# CUSTOMER ADDRESS MODEL
# --------------------------------------------------

class CustomerAddress(Base):

    __tablename__ = "customer_addresses"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    customer_id = Column(
        String,
        ForeignKey("customers.id"),
        nullable=False,
        index=True
    )

    address_type = Column(
        String,
        default="shipping",
        nullable=False
    )

    address_line1 = Column(String, nullable=False)

    address_line2 = Column(String, nullable=True)

    city = Column(String, nullable=False)

    state = Column(String, nullable=False)

    postal_code = Column(String, nullable=False)

    country = Column(
        String,
        default="India",
        nullable=False
    )

    is_default = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# PRODUCT MODEL
# --------------------------------------------------

class Product(Base):

    __tablename__ = "products"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    sku = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    name = Column(String, nullable=False, index=True)

    description = Column(Text, nullable=True)

    price = Column(
        Numeric(10, 2),
        nullable=False
    )

    stock_quantity = Column(
        Integer,
        default=0,
        nullable=False
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# ORDER MODEL
# --------------------------------------------------

class Order(Base):

    __tablename__ = "orders"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    order_number = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    customer_id = Column(
        String,
        ForeignKey("customers.id"),
        nullable=False,
        index=True
    )

    shipping_address_id = Column(
        String,
        ForeignKey("customer_addresses.id"),
        nullable=True
    )

    status = Column(
        String,
        default="pending",
        nullable=False,
        index=True
    )

    total_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# --------------------------------------------------
# ORDER ITEM MODEL
# --------------------------------------------------

class OrderItem(Base):

    __tablename__ = "order_items"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    order_id = Column(
        String,
        ForeignKey("orders.id"),
        nullable=False,
        index=True
    )

    product_id = Column(
        String,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    product_name = Column(
        String,
        nullable=False
    )

    quantity = Column(
        Integer,
        nullable=False
    )

    unit_price = Column(
        Numeric(10, 2),
        nullable=False
    )

    subtotal = Column(
        Numeric(10, 2),
        nullable=False
    )


# --------------------------------------------------
# PAYMENT MODEL
# --------------------------------------------------

class Payment(Base):

    __tablename__ = "payments"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    order_id = Column(
        String,
        ForeignKey("orders.id"),
        nullable=False,
        index=True
    )

    amount = Column(
        Numeric(10, 2),
        nullable=False
    )

    payment_method = Column(
        String,
        nullable=False
    )

    transaction_reference = Column(
        String,
        unique=True,
        nullable=True
    )

    status = Column(
        String,
        default="pending",
        nullable=False,
        index=True
    )

    paid_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# DELIVERY MODEL
# --------------------------------------------------

class Delivery(Base):

    __tablename__ = "deliveries"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    order_id = Column(
        String,
        ForeignKey("orders.id"),
        unique=True,
        nullable=False,
        index=True
    )

    tracking_number = Column(
        String,
        unique=True,
        nullable=True,
        index=True
    )

    courier_name = Column(String, nullable=True)

    status = Column(
        String,
        default="pending",
        nullable=False,
        index=True
    )

    shipped_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    estimated_delivery_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    delivered_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# --------------------------------------------------
# SUPPORT TICKET MODEL
# --------------------------------------------------

class SupportTicket(Base):

    __tablename__ = "support_tickets"

    id = Column(
        String,
        primary_key=True,
        index=True,
        default=lambda: str(uuid4())
    )

    ticket_number = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    customer_id = Column(
        String,
        ForeignKey("customers.id"),
        nullable=False,
        index=True
    )

    order_id = Column(
        String,
        ForeignKey("orders.id"),
        nullable=True,
        index=True
    )

    subject = Column(String, nullable=False)

    description = Column(Text, nullable=False)

    status = Column(
        String,
        default="open",
        nullable=False,
        index=True
    )

    priority = Column(
        String,
        default="normal",
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )