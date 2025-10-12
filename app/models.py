from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserType(str, Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    ADMIN = "admin"

class ProductCondition(str, Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class SubscriptionTier(str, Enum):
    BASIC = "basic"
    PRO = "pro"
    PREMIUM = "premium"

# User Schemas
class UserBase(BaseModel):
    name: str
    email: EmailStr
    type: UserType

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: str
    created_at: datetime

# Shop Schemas
class ShopBase(BaseModel):
    name: str
    description: Optional[str] = None
    address: str
    phone: Optional[str] = None

class ShopCreate(ShopBase):
    pass

class ShopResponse(ShopBase):
    id: str
    user_id: str
    verified: bool
    subscription_tier: Optional[SubscriptionTier]
    rating: Optional[float]
    created_at: datetime

# Product Schemas
class ProductBase(BaseModel):
    title: str
    description: str
    brand: str
    price: float = Field(..., gt=0)
    condition: ProductCondition
    stock: int = Field(..., ge=0)
    specs: Optional[Dict[str, Any]] = None

class ProductCreate(ProductBase):
    images: List[str] = []

class ProductResponse(ProductBase):
    id: str
    shop_id: str
    images: List[str]
    created_at: datetime

# Order Schemas
class OrderItemBase(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1)

class OrderCreate(BaseModel):
    items: List[OrderItemBase]
    shipping_address: str

class OrderResponse(BaseModel):
    id: str
    user_id: str
    shop_id: str
    total_amount: float
    status: OrderStatus
    items: List[Dict]
    shipping_address: str
    created_at: datetime

# Promotion Schemas
class PromotionBase(BaseModel):
    type: str
    budget: float
    start_date: datetime
    end_date: datetime

class PromotionCreate(PromotionBase):
    product_id: Optional[str] = None

class PromotionResponse(PromotionBase):
    id: str
    shop_id: str
    product_id: Optional[str]
    status: str