from pydantic import BaseModel, EmailStr, Field, HttpUrl, ConfigDict, field_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from enum import Enum
import re
from uuid import UUID

# ========== ENUMS ==========

class UserType(str, Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    ADMIN = "admin"
    MODERATOR = "moderator"

class ProductCondition(str, Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"
    FOR_PARTS = "for_parts"

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    RETURNED = "returned"

class SubscriptionTier(str, Enum):
    BASIC = "basic"
    PRO = "pro"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

class TransactionType(str, Enum):
    # User transactions
    USER_REGISTER = "user_register"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    
    # Shop transactions
    SHOP_CREATE = "shop_create"
    SHOP_UPDATE = "shop_update"
    SHOP_DELETE = "shop_delete"
    SHOP_VERIFY = "shop_verify"
    SHOP_SUSPEND = "shop_suspend"
    
    # Product transactions
    PRODUCT_CREATE = "product_create"
    PRODUCT_UPDATE = "product_update"
    PRODUCT_DELETE = "product_delete"
    PRODUCT_PUBLISH = "product_publish"
    PRODUCT_UNPUBLISH = "product_unpublish"
    
    # Category transactions
    CATEGORY_CREATE = "category_create"
    CATEGORY_UPDATE = "category_update"
    CATEGORY_DELETE = "category_delete"
    CATEGORY_REORDER = "category_reorder"
    PRODUCT_CATEGORY_UPDATE = "product_category_update"
    
    # Order transactions
    ORDER_CREATE = "order_create"
    ORDER_UPDATE = "order_update"
    ORDER_CANCEL = "order_cancel"
    ORDER_COMPLETE = "order_complete"
    ORDER_REFUND = "order_refund"
    
    # Promotion transactions
    PROMOTION_CREATE = "promotion_create"
    PROMOTION_UPDATE = "promotion_update"
    PROMOTION_DELETE = "promotion_delete"
    PROMOTION_ACTIVATE = "promotion_activate"
    PROMOTION_DEACTIVATE = "promotion_deactivate"
    
    # Review transactions
    REVIEW_CREATE = "review_create"
    REVIEW_UPDATE = "review_update"
    REVIEW_DELETE = "review_delete"
    
    # Inventory transactions
    PRICE_UPDATE = "price_update"
    STOCK_UPDATE = "stock_update"
    STOCK_ALERT = "stock_alert"
    
    # Payment transactions
    PAYMENT_CREATE = "payment_create"
    PAYMENT_COMPLETE = "payment_complete"
    PAYMENT_REFUND = "payment_refund"
    PAYMENT_FAILED = "payment_failed"
    
    # System transactions
    SETTINGS_UPDATE = "settings_update"
    BULK_OPERATION = "bulk_operation"
    IMPORT_DATA = "import_data"
    EXPORT_DATA = "export_data"

class NotificationType(str, Enum):
    SYSTEM = "system"
    ORDER = "order"
    PRODUCT = "product"
    PROMOTION = "promotion"
    SECURITY = "security"
    PAYMENT = "payment"
    SHIPMENT = "shipment"
    REVIEW = "review"
    SUPPORT = "support"

class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class AuditAction(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    VIEW = "VIEW"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"

class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"
    CASH_ON_DELIVERY = "cash_on_delivery"
    WALLET = "wallet"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"

class ShippingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"

class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"

class ImportExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"
    XML = "xml"

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"

class PromotionType(str, Enum):
    DISCOUNT_PERCENTAGE = "discount_percentage"
    DISCOUNT_FIXED = "discount_fixed"
    BUY_ONE_GET_ONE = "buy_one_get_one"
    FREE_SHIPPING = "free_shipping"
    GIFT_WITH_PURCHASE = "gift_with_purchase"

# ========== USER SCHEMAS ==========

class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    type: UserType
    phone_number: Optional[str] = Field(
        default=None, 
        pattern=r'^\+?[1-9]\d{1,14}$',
        description="Phone number in E.164 format"
    )
    profile_picture: Optional[HttpUrl] = Field(
        default=None,
        description="URL to the user's profile picture"
    )
    locale: str = Field(default="en-US", pattern=r'^[a-z]{2}-[A-Z]{2}$')
    timezone: str = Field(default="UTC")
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: Optional[str] = None
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('passwords do not match')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = Field(default=False)

class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    login_count: int = Field(default=0)
    blockchain_tx_id: Optional[str] = None
    two_factor_enabled: bool = Field(default=False)
    
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone_number: Optional[str] = Field(
        default=None,
        pattern=r'^\+?[1-9]\d{1,14}$'
    )
    profile_picture: Optional[HttpUrl] = None
    locale: Optional[str] = Field(default=None, pattern=r'^[a-z]{2}-[A-Z]{2}$')
    timezone: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('passwords do not match')
        return v

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v, info):
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('passwords do not match')
        return v

# ========== SHOP SCHEMAS ==========

class ShopBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    address: str
    phone: Optional[str] = Field(default=None, pattern=r'^\+?[1-9]\d{1,14}$')
    email: Optional[EmailStr] = None
    website: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    banner_url: Optional[HttpUrl] = None
    tax_id: Optional[str] = Field(default=None, max_length=50)
    business_registration_number: Optional[str] = Field(default=None, max_length=50)
    country: str = Field(default="MW", pattern=r'^[A-Z]{2}$')
    currency: str = Field(default="MWK", pattern=r'^[A-Z]{3}$')

class ShopCreate(ShopBase):
    terms_accepted: bool = Field(default=False)
    privacy_policy_accepted: bool = Field(default=False)
    
    @field_validator('terms_accepted', 'privacy_policy_accepted')
    @classmethod
    def must_accept_terms(cls, v):
        if not v:
            raise ValueError('must accept terms and privacy policy')
        return v

class ShopResponse(ShopBase):
    id: str
    user_id: str
    verified: bool = Field(default=False)
    verification_status: str = Field(default="pending")
    subscription_tier: Optional[SubscriptionTier] = None
    subscription_expires_at: Optional[datetime] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    total_rating_count: int = Field(default=0)
    total_sales: int = Field(default=0)
    total_revenue: float = Field(default=0.0)
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    is_suspended: bool = Field(default=False)
    suspension_reason: Optional[str] = None
    blockchain_tx_id: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class ShopUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, pattern=r'^\+?[1-9]\d{1,14}$')
    email: Optional[EmailStr] = None
    website: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    banner_url: Optional[HttpUrl] = None
    tax_id: Optional[str] = Field(default=None, max_length=50)
    country: Optional[str] = Field(default=None, pattern=r'^[A-Z]{2}$')
    currency: Optional[str] = Field(default=None, pattern=r'^[A-Z]{3}$')

class ShopVerificationRequest(BaseModel):
    shop_id: str
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None

class ShopVerificationResponse(BaseModel):
    verified: bool
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    notes: Optional[str] = None
    documents_verified: List[str] = Field(default_factory=list)

# ========== CATEGORY SCHEMAS ==========

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=50)
    slug: str = Field(..., pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    parent_id: Optional[str] = None
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    meta_title: Optional[str] = Field(default=None, max_length=70)
    meta_description: Optional[str] = Field(default=None, max_length=160)
    image_url: Optional[HttpUrl] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=50)
    slug: Optional[str] = Field(default=None, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    meta_title: Optional[str] = Field(default=None, max_length=70)
    meta_description: Optional[str] = Field(default=None, max_length=160)
    image_url: Optional[HttpUrl] = None

class CategoryResponse(CategoryBase):
    id: str
    product_count: int = Field(default=0)
    children: List['CategoryResponse'] = Field(default_factory=list)
    path: List[str] = Field(default_factory=list)
    depth: int = Field(default=0)
    blockchain_tx_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class CategoryReorder(BaseModel):
    categories: List[Dict[str, Any]] = Field(
        ...,
        description="List of category IDs with their new sort orders"
    )

# ========== PRODUCT SCHEMAS ==========

class ProductBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10, max_length=10000)
    brand: str = Field(..., max_length=100)
    price: float = Field(..., gt=0)
    compare_at_price: Optional[float] = Field(default=None, gt=0)
    cost_price: Optional[float] = Field(default=None, gt=0)
    condition: ProductCondition
    stock: int = Field(..., ge=0)
    sku: Optional[str] = Field(default=None, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)
    weight: Optional[float] = Field(default=None, ge=0)
    weight_unit: str = Field(default="kg")
    dimensions: Optional[Dict[str, float]] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    specs: Optional[Dict[str, Any]] = Field(default_factory=dict)
    category_ids: Optional[List[str]] = Field(default=None)
    variants: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    is_digital: bool = Field(default=False)
    digital_download_url: Optional[HttpUrl] = None
    requires_shipping: bool = Field(default=True)
    is_taxable: bool = Field(default=True)
    tax_rate: Optional[float] = Field(default=None, ge=0, le=100)
    seo_title: Optional[str] = Field(default=None, max_length=70)
    seo_description: Optional[str] = Field(default=None, max_length=160)
    is_featured: bool = Field(default=False)
    is_published: bool = Field(default=True)
    published_at: Optional[datetime] = None

class ProductCreate(ProductBase):
    images: List[str] = []
    primary_image_index: int = Field(default=0, ge=0)

class ProductResponse(ProductBase):
    id: str
    shop_id: str
    images: List[str]
    primary_image: Optional[str] = None
    category_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    blockchain_tx_id: Optional[str] = None
    average_rating: Optional[float] = Field(default=None, ge=0, le=5)
    rating_count: int = Field(default=0)
    review_count: int = Field(default=0)
    total_sold: int = Field(default=0)
    view_count: int = Field(default=0)
    wishlist_count: int = Field(default=0)
    
    # Extended fields
    categories: Optional[List[CategoryResponse]] = Field(default_factory=list)
    shop: Optional[Dict[str, Any]] = Field(default=None)
    blockchain_activity: Optional[Dict[str, Any]] = Field(default=None)
    variant_groups: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)

class ProductUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, min_length=10, max_length=10000)
    brand: Optional[str] = Field(default=None, max_length=100)
    price: Optional[float] = Field(default=None, gt=0)
    compare_at_price: Optional[float] = Field(default=None, gt=0)
    cost_price: Optional[float] = Field(default=None, gt=0)
    condition: Optional[ProductCondition] = None
    stock: Optional[int] = Field(default=None, ge=0)
    sku: Optional[str] = Field(default=None, max_length=100)
    barcode: Optional[str] = Field(default=None, max_length=100)
    weight: Optional[float] = Field(default=None, ge=0)
    weight_unit: Optional[str] = None
    dimensions: Optional[Dict[str, float]] = None
    tags: Optional[List[str]] = None
    specs: Optional[Dict[str, Any]] = None
    category_ids: Optional[List[str]] = None
    variants: Optional[List[Dict[str, Any]]] = None
    is_digital: Optional[bool] = None
    digital_download_url: Optional[HttpUrl] = None
    requires_shipping: Optional[bool] = None
    is_taxable: Optional[bool] = None
    tax_rate: Optional[float] = Field(default=None, ge=0, le=100)
    seo_title: Optional[str] = Field(default=None, max_length=70)
    seo_description: Optional[str] = Field(default=None, max_length=160)
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    images: Optional[List[str]] = None
    primary_image_index: Optional[int] = Field(default=None, ge=0)

class StockUpdate(BaseModel):
    stock_change: int
    reason: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=500)

class PriceUpdate(BaseModel):
    new_price: float = Field(..., gt=0)
    old_price: float = Field(..., gt=0)
    reason: Optional[str] = Field(default=None, max_length=200)
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

class ProductVariant(BaseModel):
    id: str
    product_id: str
    sku: str
    price: float
    compare_at_price: Optional[float]
    cost_price: Optional[float]
    stock: int
    weight: Optional[float]
    dimensions: Optional[Dict[str, float]]
    options: Dict[str, str]
    is_active: bool = Field(default=True)
    created_at: datetime
    updated_at: Optional[datetime] = None

# ========== PRODUCT-CATEGORY RELATIONSHIP ==========

class ProductCategoryAssignment(BaseModel):
    category_ids: List[str] = Field(..., min_length=1, max_length=10)
    replace_existing: bool = Field(default=False)

class ProductCategoryResponse(BaseModel):
    product_id: str
    category_id: str
    category: CategoryResponse
    is_primary: bool = Field(default=False)
    created_at: datetime
    created_by: Optional[str] = None

class CategoryWithProductsResponse(CategoryResponse):
    products: List[ProductResponse] = Field(default_factory=list)
    total_products: int = Field(default=0)
    featured_products: List[ProductResponse] = Field(default_factory=list)

# ========== ORDER SCHEMAS ==========

class OrderItemBase(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., gt=0)
    tax_rate: Optional[float] = Field(default=0, ge=0, le=100)

class OrderCreate(BaseModel):
    items: List[OrderItemBase]
    shipping_address: Dict[str, Any]
    billing_address: Optional[Dict[str, Any]] = None
    shipping_method: str
    payment_method: PaymentMethod
    notes: Optional[str] = Field(default=None, max_length=500)
    coupon_code: Optional[str] = None
    use_wallet: bool = Field(default=False)
    
    @field_validator('billing_address')
    @classmethod
    def set_billing_address(cls, v, info):
        if v is None and 'shipping_address' in info.data:
            return info.data['shipping_address']
        return v

class OrderResponse(BaseModel):
    id: str
    order_number: str
    user_id: str
    shop_id: str
    total_amount: float
    subtotal: float
    tax_amount: float
    shipping_amount: float
    discount_amount: float
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    shipping_status: ShippingStatus
    items: List[Dict[str, Any]]
    shipping_address: Dict[str, Any]
    billing_address: Dict[str, Any]
    shipping_method: str
    payment_method: PaymentMethod
    notes: Optional[str] = None
    coupon_code: Optional[str] = None
    coupon_discount: Optional[float] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[HttpUrl] = None
    estimated_delivery_date: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    blockchain_tx_id: Optional[str] = None
    
    # Extended fields
    user: Optional[Dict[str, Any]] = None
    shop: Optional[Dict[str, Any]] = None
    payment_details: Optional[Dict[str, Any]] = None
    shipping_details: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    shipping_status: Optional[ShippingStatus] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[HttpUrl] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    estimated_delivery_date: Optional[datetime] = None

class OrderCancelRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)
    refund_amount: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=500)

# ========== ADDRESS SCHEMAS ==========

class AddressBase(BaseModel):
    label: str = Field(..., min_length=2, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    street: str = Field(..., max_length=200)
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    postal_code: str = Field(..., max_length=20)
    country: str = Field(..., pattern=r'^[A-Z]{2}$')
    is_default: bool = Field(default=False)

class AddressCreate(AddressBase):
    pass

class AddressResponse(AddressBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class AddressUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=2, max_length=50)
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = Field(default=None, pattern=r'^\+?[1-9]\d{1,14}$')
    street: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, pattern=r'^[A-Z]{2}$')
    is_default: Optional[bool] = None

# ========== PAYMENT SCHEMAS ==========

class PaymentIntent(BaseModel):
    order_id: str
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    payment_method: PaymentMethod
    customer_email: EmailStr
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    return_url: Optional[HttpUrl] = None
    cancel_url: Optional[HttpUrl] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: float
    currency: str
    payment_method: PaymentMethod
    status: PaymentStatus
    transaction_id: Optional[str] = None
    processor_response: Optional[Dict[str, Any]] = None
    blockchain_tx_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None

class RefundRequest(BaseModel):
    payment_id: str
    amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=5, max_length=500)
    note: Optional[str] = Field(default=None, max_length=500)

# ========== PROMOTION SCHEMAS ==========

class PromotionBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    type: PromotionType
    value: float = Field(..., ge=0)
    budget: Optional[float] = Field(default=None, ge=0)
    min_purchase_amount: Optional[float] = Field(default=None, ge=0)
    max_discount_amount: Optional[float] = Field(default=None, ge=0)
    usage_limit: Optional[int] = Field(default=None, ge=1)
    usage_limit_per_user: Optional[int] = Field(default=None, ge=1)
    start_date: datetime
    end_date: datetime
    is_active: bool = Field(default=True)

class PromotionCreate(PromotionBase):
    product_ids: Optional[List[str]] = None
    category_ids: Optional[List[str]] = None
    shop_ids: Optional[List[str]] = None
    code: Optional[str] = Field(default=None, pattern=r'^[A-Z0-9_-]+$')
    is_public: bool = Field(default=True)

class PromotionResponse(PromotionBase):
    id: str
    shop_id: Optional[str] = None
    product_ids: List[str] = Field(default_factory=list)
    category_ids: List[str] = Field(default_factory=list)
    code: Optional[str] = None
    is_public: bool
    total_used: int = Field(default=0)
    total_discount: float = Field(default=0.0)
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: str
    blockchain_tx_id: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PromotionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=200)
    type: Optional[PromotionType] = None
    value: Optional[float] = Field(default=None, ge=0)
    budget: Optional[float] = Field(default=None, ge=0)
    min_purchase_amount: Optional[float] = Field(default=None, ge=0)
    max_discount_amount: Optional[float] = Field(default=None, ge=0)
    usage_limit: Optional[int] = Field(default=None, ge=1)
    usage_limit_per_user: Optional[int] = Field(default=None, ge=1)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    product_ids: Optional[List[str]] = None
    category_ids: Optional[List[str]] = None
    code: Optional[str] = Field(default=None, pattern=r'^[A-Z0-9_-]+$')

# ========== REVIEW & RATING SCHEMAS ==========

class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=200)
    comment: str = Field(..., min_length=10, max_length=2000)
    images: List[str] = Field(default_factory=list)
    is_anonymous: bool = Field(default=False)

class ReviewCreate(ReviewBase):
    product_id: str
    order_id: Optional[str] = None

class ReviewResponse(ReviewBase):
    id: str
    product_id: str
    user_id: str
    order_id: Optional[str]
    status: ReviewStatus
    helpful_count: int = Field(default=0)
    not_helpful_count: int = Field(default=0)
    is_verified_purchase: bool = Field(default=False)
    created_at: datetime
    updated_at: Optional[datetime] = None
    blockchain_tx_id: Optional[str] = None
    
    # Extended fields
    user: Optional[Dict[str, Any]] = None
    product: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)

class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = Field(default=None, min_length=10, max_length=2000)
    images: Optional[List[str]] = None
    status: Optional[ReviewStatus] = None

class ReviewHelpful(BaseModel):
    is_helpful: bool

# ========== WISHLIST SCHEMAS ==========

class WishlistItem(BaseModel):
    product_id: str
    added_at: datetime = Field(default_factory=datetime.now)

class WishlistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_public: bool = Field(default=False)

class WishlistResponse(BaseModel):
    id: str
    user_id: str
    name: str
    is_public: bool
    items: List[WishlistItem] = Field(default_factory=list)
    item_count: int = Field(default=0)
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

# ========== CART SCHEMAS ==========

class CartItem(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(..., ge=1)
    added_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

class CartResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    items: List[CartItem] = Field(default_factory=list)
    item_count: int = Field(default=0)
    total_price: float = Field(default=0.0)
    currency: str = Field(default="USD")
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Extended fields
    items_details: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)

class CartUpdate(BaseModel):
    items: List[CartItem] = Field(..., min_length=1)

# ========== NOTIFICATION SCHEMAS ==========

class NotificationBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)
    notification_type: NotificationType
    priority: NotificationPriority = Field(default=NotificationPriority.MEDIUM)
    data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    action_url: Optional[HttpUrl] = None
    action_text: Optional[str] = Field(default=None, max_length=50)
    image_url: Optional[HttpUrl] = None
    icon: Optional[str] = Field(default=None, max_length=50)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class NotificationCreate(NotificationBase):
    user_id: str

class NotificationResponse(NotificationBase):
    id: str
    user_id: str
    read: bool = Field(default=False)
    read_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# ========== RECENTLY VIEWED SCHEMAS ==========

class RecentlyViewedBase(BaseModel):
    product_id: str
    viewed_at: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RecentlyViewedCreate(RecentlyViewedBase):
    user_id: Optional[str] = None

class RecentlyViewedResponse(RecentlyViewedBase):
    id: str
    user_id: Optional[str]
    
    # Extended fields
    product: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)

# ========== BLOCKCHAIN SCHEMAS ==========

class BlockchainTransaction(BaseModel):
    transaction_id: str
    transaction_type: TransactionType
    user_id: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    signature: Optional[str] = None
    previous_hash: Optional[str] = None
    
    # Entity references
    shop_id: Optional[str] = None
    product_id: Optional[str] = None
    order_id: Optional[str] = None
    promotion_id: Optional[str] = None
    category_id: Optional[str] = None
    review_id: Optional[str] = None
    payment_id: Optional[str] = None

class Block(BaseModel):
    index: int
    timestamp: datetime
    transactions: List[BlockchainTransaction]
    proof: int
    previous_hash: str
    nonce: int = Field(default=0)
    hash: Optional[str] = None
    mined_by: Optional[str] = None
    difficulty: int = Field(default=4)

class Blockchain(BaseModel):
    chain: List[Block] = Field(default_factory=list)
    pending_transactions: List[BlockchainTransaction] = Field(default_factory=list)
    difficulty: int = Field(default=4)
    mining_reward: float = Field(default=1.0)
    nodes: List[str] = Field(default_factory=list)

# Blockchain-specific responses
class BlockchainTransactionResponse(BaseModel):
    transaction_id: str
    transaction_type: str
    user_id: str
    timestamp: datetime
    data: Dict[str, Any]
    block_index: Optional[int] = None
    block_hash: Optional[str] = None
    confirmed: bool = Field(default=False)
    confirmations: int = Field(default=0)

class BlockResponse(BaseModel):
    index: int
    timestamp: datetime
    transactions_count: int
    proof: int
    previous_hash: str
    hash: str
    nonce: int
    mined_by: Optional[str]
    difficulty: int

class ChainValidationResponse(BaseModel):
    is_valid: bool
    total_blocks: int
    total_transactions: int
    pending_transactions: int
    issues: List[str] = Field(default_factory=list)
    chain_hash: Optional[str] = None

class BlockchainStatsResponse(BaseModel):
    total_blocks: int
    total_transactions: int
    pending_transactions: int
    chain_valid: bool
    last_block_timestamp: Optional[datetime]
    last_block_hash: Optional[str] = None
    difficulty: int
    mining_reward: float
    node_count: int
    total_mining_rewards: float

class NodeRegistration(BaseModel):
    node_address: str

class MiningRequest(BaseModel):
    miner_address: str

class MiningResponse(BaseModel):
    message: str
    block_index: Optional[int] = None
    reward: Optional[float] = None
    hash: Optional[str] = None

# ========== AUTH & TOKEN SCHEMAS ==========

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=3600)
    refresh_token: Optional[str] = None
    user_id: str
    user_type: UserType
    blockchain_tx_id: Optional[str] = None

class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    user_type: Optional[UserType] = None
    exp: Optional[datetime] = None
    scopes: List[str] = Field(default_factory=list)

class RefreshToken(BaseModel):
    refresh_token: str

class TwoFactorSetup(BaseModel):
    secret: str
    qr_code_url: str

class TwoFactorVerify(BaseModel):
    token: str

# ========== RESPONSE MODELS ==========

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
    field: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    request_id: Optional[str] = None

class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str

class ValidationErrorResponse(BaseModel):
    detail: List[ValidationError]
    timestamp: datetime = Field(default_factory=datetime.now)

class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class PaginatedResponse(BaseModel):
    data: List[Any]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_previous: bool
    meta: Optional[Dict[str, Any]] = None

# ========== FILTER & QUERY MODELS ==========

class ProductFilter(BaseModel):
    search: Optional[str] = None
    brand: Optional[str] = None
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    condition: Optional[ProductCondition] = None
    shop_id: Optional[str] = None
    category_id: Optional[str] = None
    tag: Optional[str] = None
    in_stock_only: bool = Field(default=False)
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    min_rating: Optional[float] = Field(default=None, ge=0, le=5)
    sort_by: str = Field(default="created_at", pattern=r'^(created_at|price|name|rating|popularity)$')
    sort_order: SortDirection = Field(default=SortDirection.DESC)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class CategoryFilter(BaseModel):
    parent_id: Optional[str] = None
    is_active: Optional[bool] = None
    include_products: bool = Field(default=False)
    include_children: bool = Field(default=True)
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class OrderFilter(BaseModel):
    user_id: Optional[str] = None
    shop_id: Optional[str] = None
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    shipping_status: Optional[ShippingStatus] = None
    min_amount: Optional[float] = Field(default=None, ge=0)
    max_amount: Optional[float] = Field(default=None, ge=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sort_by: str = Field(default="created_at", pattern=r'^(created_at|updated_at|total_amount)$')
    sort_order: SortDirection = Field(default=SortDirection.DESC)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class UserFilter(BaseModel):
    type: Optional[UserType] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    search: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    sort_by: str = Field(default="created_at", pattern=r'^(created_at|name|email)$')
    sort_order: SortDirection = Field(default=SortDirection.DESC)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

# ========== SEARCH MODELS ==========

class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    category_id: Optional[str] = None
    shop_id: Optional[str] = None
    brand: Optional[str] = None
    min_price: Optional[float] = Field(default=None, ge=0)
    max_price: Optional[float] = Field(default=None, ge=0)
    condition: Optional[ProductCondition] = None
    in_stock_only: bool = Field(default=False)
    sort_by: str = Field(default="relevance", pattern=r'^(relevance|price|rating|newest|popularity)$')
    sort_order: SortDirection = Field(default=SortDirection.DESC)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    facets: List[str] = Field(default_factory=lambda: ["category", "brand", "price_range"])

class SearchResponse(BaseModel):
    results: List[ProductResponse]
    total: int
    query: str
    facets: Dict[str, Any] = Field(default_factory=dict)
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[str] = Field(default_factory=list)
    search_time_ms: float

class AutocompleteQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=50)
    limit: int = Field(default=10, ge=1, le=20)

class AutocompleteResponse(BaseModel):
    products: List[Dict[str, Any]] = Field(default_factory=list)
    categories: List[Dict[str, Any]] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

# ========== ANALYTICS & STATISTICS MODELS ==========

class TimeRange(BaseModel):
    start_date: datetime
    end_date: datetime
    interval: str = Field(default="day", pattern=r'^(hour|day|week|month|year)$')
    timezone: str = Field(default="UTC")

class DateRange(BaseModel):
    start_date: date
    end_date: date

class UserStats(BaseModel):
    total_users: int
    merchants_count: int
    customers_count: int
    admins_count: int
    active_users_30d: int
    new_users_30d: int
    user_growth_rate: float
    avg_session_duration: Optional[float]

class ShopStats(BaseModel):
    total_shops: int
    verified_shops: int
    active_shops: int
    suspended_shops: int
    average_rating: Optional[float]
    by_subscription_tier: Dict[str, int]
    total_revenue: float
    avg_shop_revenue: float

class ProductStats(BaseModel):
    total_products: int
    published_products: int
    out_of_stock: int
    low_stock: int
    average_price: float
    by_condition: Dict[str, int]
    by_category: Dict[str, int]
    top_selling_products: List[Dict[str, Any]]

class OrderStats(BaseModel):
    total_orders: int
    total_revenue: float
    avg_order_value: float
    conversion_rate: float
    by_status: Dict[str, int]
    by_payment_method: Dict[str, int]
    by_shipping_method: Dict[str, int]
    revenue_trend: Dict[str, float]

class SalesReport(BaseModel):
    time_range: TimeRange
    total_revenue: float
    total_orders: int
    total_products_sold: int
    avg_order_value: float
    top_products: List[Dict[str, Any]]
    top_categories: List[Dict[str, Any]]
    top_shops: List[Dict[str, Any]]
    revenue_by_interval: Dict[str, float]
    orders_by_interval: Dict[str, int]

class PlatformStats(BaseModel):
    users: UserStats
    shops: ShopStats
    products: ProductStats
    orders: OrderStats
    blockchain: BlockchainStatsResponse
    revenue_summary: Dict[str, float]
    timestamp: datetime = Field(default_factory=datetime.now)
    cache_hit_rate: Optional[float] = None
    avg_response_time: Optional[float] = None

# ========== IMPORT/EXPORT MODELS ==========

class ImportRequest(BaseModel):
    file_url: Optional[HttpUrl] = None
    file_content: Optional[str] = None
    import_type: str = Field(..., pattern=r'^(products|categories|users|orders|shops|customers)$')
    format: ImportExportFormat = Field(default=ImportExportFormat.JSON)
    mapping: Dict[str, str] = Field(default_factory=dict)
    on_conflict: str = Field(default="skip", pattern=r'^(skip|update|replace|merge)$')
    notify_on_complete: bool = Field(default=True)
    validate_only: bool = Field(default=False)

class ExportRequest(BaseModel):
    export_type: str = Field(..., pattern=r'^(products|categories|users|orders|shops|customers|transactions)$')
    filters: Dict[str, Any] = Field(default_factory=dict)
    format: ImportExportFormat = Field(default=ImportExportFormat.JSON)
    include_metadata: bool = Field(default=True)
    fields: Optional[List[str]] = None
    compression: bool = Field(default=False)

class ImportExportStatus(BaseModel):
    job_id: str
    status: str = Field(..., pattern=r'^(pending|processing|completed|failed|cancelled)$')
    progress: int = Field(..., ge=0, le=100)
    total_items: Optional[int] = None
    processed_items: Optional[int] = None
    successful_items: Optional[int] = None
    failed_items: Optional[int] = None
    result_url: Optional[HttpUrl] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    created_by: str

class BulkOperation(BaseModel):
    operation: str = Field(..., pattern=r'^(update|delete|publish|unpublish|activate|deactivate)$')
    entity_type: str = Field(..., pattern=r'^(products|categories|users|shops)$')
    ids: List[str] = Field(..., min_length=1)
    data: Optional[Dict[str, Any]] = None

# ========== AUDIT & LOG MODELS ==========

class AuditLogEntry(BaseModel):
    id: str
    user_id: str
    action: AuditAction
    resource_type: str
    resource_id: Optional[str]
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    location: Optional[Dict[str, Any]]
    timestamp: datetime
    blockchain_tx_id: Optional[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AuditLogFilter(BaseModel):
    user_id: Optional[str] = None
    action: Optional[AuditAction] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    ip_address: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

# ========== FILE UPLOAD MODELS ==========

class FileUpload(BaseModel):
    filename: str
    content_type: str = Field(..., pattern=r'^(image|application|text)/')
    file_size: int = Field(..., le=104_857_600)  # 100MB limit
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    url: HttpUrl
    content_type: str
    file_size: int
    uploaded_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ImageUpload(BaseModel):
    image_type: str = Field(..., pattern=r'^(product|profile|shop|banner|logo)$')
    max_width: Optional[int] = Field(default=None, ge=1)
    max_height: Optional[int] = Field(default=None, ge=1)
    quality: int = Field(default=85, ge=1, le=100)

# ========== CACHE & PERFORMANCE MODELS ==========

class CacheStats(BaseModel):
    hit_rate: float
    miss_rate: float
    total_items: int
    memory_usage: str
    evictions: int
    avg_item_size: Optional[float]
    max_size: Optional[int]

class PerformanceMetrics(BaseModel):
    endpoint: str
    method: str
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    request_count: int
    error_count: int
    error_rate: float
    timestamp: datetime
    status_codes: Dict[str, int]

class HealthCheck(BaseModel):
    status: str = Field(..., pattern=r'^(healthy|degraded|unhealthy)$')
    timestamp: datetime = Field(default_factory=datetime.now)
    uptime: float
    services: Dict[str, str] = Field(default_factory=dict)
    version: str
    database_connected: bool
    cache_connected: bool
    blockchain_connected: bool
    queue_healthy: bool
    memory_usage: Dict[str, float]
    response_time: float

# ========== WEBHOOK MODELS ==========

class WebhookEvent(BaseModel):
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    signature: Optional[str] = None
    attempt: int = Field(default=1)
    webhook_id: Optional[str] = None

class WebhookSubscription(BaseModel):
    url: HttpUrl
    event_types: List[str]
    secret: Optional[str] = None
    active: bool = Field(default=True)
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {"max_attempts": 3, "backoff": 1.5})
    headers: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class WebhookDelivery(BaseModel):
    webhook_id: str
    event_id: str
    status: str = Field(..., pattern=r'^(pending|delivered|failed|retrying)$')
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    attempts: int = Field(default=0)
    last_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime

# ========== RATE LIMITING MODELS ==========

class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    reset_time: datetime
    window: str = Field(..., pattern=r'^\d+[smhd]$')  # e.g., "1m", "1h", "1d"
    cost: int = Field(default=1)

class RateLimitHeaders(BaseModel):
    x_ratelimit_limit: int
    x_ratelimit_remaining: int
    x_ratelimit_reset: int
    x_ratelimit_window: str
    x_ratelimit_policy: str

# ========== ASYNC TASK MODELS ==========

class AsyncTask(BaseModel):
    task_id: str
    status: str = Field(..., pattern=r'^(pending|processing|completed|failed|cancelled)$')
    progress: int = Field(..., ge=0, le=100)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: str

class TaskCreate(BaseModel):
    task_type: str
    data: Dict[str, Any]
    priority: int = Field(default=0, ge=0, le=10)
    delay_seconds: Optional[int] = Field(default=None, ge=0)
    notify_on_complete: bool = Field(default=False)

# ========== SETTINGS MODELS ==========

class PlatformSettings(BaseModel):
    app_name: str = "E-Commerce Platform"
    currency: str = "USD"
    default_commission_rate: float = Field(default=5.0, ge=0, le=100)
    min_order_amount: float = Field(default=0.0, ge=0)
    max_products_per_shop: int = Field(default=1000, gt=0)
    notification_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    blockchain_enabled: bool = True
    auto_verify_merchants: bool = False
    require_2fa_for_merchants: bool = False
    max_file_upload_size: int = Field(default=104_857_600)  # 100MB
    allowed_file_types: List[str] = Field(default_factory=lambda: ["image/jpeg", "image/png", "image/webp", "application/pdf"])
    maintenance_mode: bool = False
    maintenance_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class SettingsUpdate(BaseModel):
    currency: Optional[str] = None
    default_commission_rate: Optional[float] = Field(default=None, ge=0, le=100)
    min_order_amount: Optional[float] = Field(default=None, ge=0)
    max_products_per_shop: Optional[int] = Field(default=None, gt=0)
    notification_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    blockchain_enabled: Optional[bool] = None
    auto_verify_merchants: Optional[bool] = None
    require_2fa_for_merchants: Optional[bool] = None
    max_file_upload_size: Optional[int] = None
    allowed_file_types: Optional[List[str]] = None
    maintenance_mode: Optional[bool] = None
    maintenance_message: Optional[str] = None

# ========== RELATIONSHIP MODELS ==========

class UserWithShopsResponse(UserResponse):
    shops: List[ShopResponse] = Field(default_factory=list)
    total_shops: int = Field(default=0)
    addresses: List[AddressResponse] = Field(default_factory=list)
    wishlists: List[WishlistResponse] = Field(default_factory=list)

class ShopWithProductsResponse(ShopResponse):
    products: List[ProductResponse] = Field(default_factory=list)
    total_products: int = Field(default=0)
    total_orders: int = Field(default=0)
    recent_orders: List[OrderResponse] = Field(default_factory=list)
    promotions: List[PromotionResponse] = Field(default_factory=list)

class ProductWithDetailsResponse(ProductResponse):
    shop: ShopResponse
    categories: List[CategoryResponse] = Field(default_factory=list)
    average_rating: Optional[float] = Field(default=None)
    rating_count: int = Field(default=0)
    review_count: int = Field(default=0)
    total_sold: int = Field(default=0)
    similar_products: List[ProductResponse] = Field(default_factory=list)
    reviews: List[ReviewResponse] = Field(default_factory=list)

# Fix circular references
CategoryResponse.model_rebuild()
CategoryWithProductsResponse.model_rebuild()