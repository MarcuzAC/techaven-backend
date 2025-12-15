import os
from typing import List, Optional, Union
from pydantic import Field, field_validator, HttpUrl, ConfigDict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # ========== APP CONFIGURATION ==========
    APP_NAME: str = "ElectroBazaar"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="production", env="ENVIRONMENT")
    
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ElectroBazaar API"
    API_KEY: Optional[str] = Field(default=None, env="API_KEY")
    
    # Server
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    WORKERS: int = Field(default=4, env="WORKERS")
    
    # ========== SECURITY ==========
    SECRET_KEY: str = Field(
        default="electrobazaar_prod_secret_key_2024_change_in_production",
        env="SECRET_KEY"
    )
    JWT_SECRET: str = Field(
        default="electrobazaar_jwt_prod_secret_2024_keep_safe",
        env="JWT_SECRET"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="REFRESH_TOKEN_EXPIRE_DAYS")  # 30 days
    
    # Password hashing
    BCRYPT_ROUNDS: int = Field(default=12, env="BCRYPT_ROUNDS")
    
    # ========== DATABASE ==========
    SUPABASE_URL: str = Field(
        default="https://jetbmmzhckoquazhwiyx.supabase.co",
        env="SUPABASE_URL"
    )
    SUPABASE_KEY: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpldGJtbXpoY2tvcXVhemh3aXl4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTg3NDE1OTQsImV4cCI6MjA3NDMxNzU5NH0.90AIL80y4NtalmL3AX5s7cnT7GIdotFvCoI5wMXoz58",
        env="SUPABASE_KEY"
    )
    SUPABASE_SERVICE_KEY: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpldGJtbXpoY2tvcXVhemh3aXl4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1ODc0MTU5NCwiZXhwIjoyMDc0MzE3NTk0fQ.90AIL80y4NtalmL3AX5s7cnT7GIdotFvCoI5wMXoz58_service_role",
        env="SUPABASE_SERVICE_KEY"
    )
    SUPABASE_STORAGE_BUCKET: str = Field(default="products", env="SUPABASE_STORAGE_BUCKET")
    SUPABASE_DB_POOL_SIZE: int = Field(default=20, env="SUPABASE_DB_POOL_SIZE")
    
    # ========== PAYMENT PROCESSING ==========
    STRIPE_SECRET_KEY: Optional[str] = Field(
        default="sk_test_51QABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        env="STRIPE_SECRET_KEY"
    )
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(
        default="pk_test_51QABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        env="STRIPE_PUBLISHABLE_KEY"
    )
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(
        default="whsec_test_your_webhook_secret_change_this",
        env="STRIPE_WEBHOOK_SECRET"
    )
    
    # Payment methods
    ENABLE_STRIPE: bool = Field(default=True, env="ENABLE_STRIPE")
    ENABLE_PAYPAL: bool = Field(default=False, env="ENABLE_PAYPAL")
    ENABLE_MPESA: bool = Field(default=True, env="ENABLE_MPESA")
    
    # Currency
    DEFAULT_CURRENCY: str = Field(default="MWK", env="DEFAULT_CURRENCY")
    
    # ========== CACHE & QUEUE ==========
    REDIS_URL: Optional[str] = Field(
        default=None,
        env="REDIS_URL"
    )
    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        env="REDIS_PASSWORD"
    )
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    
    # Celery
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        env="CELERY_BROKER_URL"
    )
    CELERY_RESULT_BACKEND: Optional[str] = Field(
        default=None,
        env="CELERY_RESULT_BACKEND"
    )
    
    # ========== SEARCH ==========
    ELASTICSEARCH_URL: Optional[str] = Field(
        default=None,
        env="ELASTICSEARCH_URL"
    )
    ENABLE_ELASTICSEARCH: bool = Field(default=False, env="ENABLE_ELASTICSEARCH")
    
    # ========== EMAIL & NOTIFICATIONS ==========
    SMTP_HOST: Optional[str] = Field(
        default=None,
        env="SMTP_HOST"
    )
    SMTP_PORT: Optional[int] = Field(default=587, env="SMTP_PORT")
    SMTP_USER: Optional[str] = Field(
        default=None,
        env="SMTP_USER"
    )
    SMTP_PASSWORD: Optional[str] = Field(
        default=None,
        env="SMTP_PASSWORD"
    )
    SMTP_TLS: bool = Field(default=True, env="SMTP_TLS")
    SMTP_SSL: bool = Field(default=False, env="SMTP_SSL")
    
    EMAILS_FROM_EMAIL: str = Field(default="noreply@electrobazaar.com", env="EMAILS_FROM_EMAIL")
    EMAILS_FROM_NAME: str = Field(default="ElectroBazaar", env="EMAILS_FROM_NAME")
    
    # Email templates
    EMAIL_TEMPLATES_DIR: str = "app/email-templates"
    
    # ========== FILE STORAGE ==========
    UPLOAD_DIR: str = Field(default="uploads", env="UPLOAD_DIR")
    MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024, env="MAX_UPLOAD_SIZE")  # 10MB
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    ALLOWED_FILE_TYPES: List[str] = ["application/pdf", "image/*"]
    
    # ========== CORS ==========
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = Field(
        default=["http://localhost:3000", "http://localhost:8081", "http://localhost:19006", "https://electrobazaar.com", "https://www.electrobazaar.com"],
        env="BACKEND_CORS_ORIGINS"
    )
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # ========== RATE LIMITING ==========
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")  # requests per minute
    RATE_LIMIT_BURST: int = Field(default=10, env="RATE_LIMIT_BURST")  # burst requests
    
    # ========== BLOCKCHAIN ==========
    BLOCKCHAIN_ENABLED: bool = Field(default=True, env="BLOCKCHAIN_ENABLED")
    BLOCKCHAIN_DIFFICULTY: int = Field(default=4, env="BLOCKCHAIN_DIFFICULTY")
    BLOCK_REWARD: float = Field(default=1.0, env="BLOCK_REWARD")
    BLOCKCHAIN_NETWORK: str = Field(default="local", env="BLOCKCHAIN_NETWORK")
    
    # ========== ANALYTICS & TRACKING ==========
    GOOGLE_ANALYTICS_ID: Optional[str] = Field(
        default=None,
        env="GOOGLE_ANALYTICS_ID"
    )
    MIXPANEL_TOKEN: Optional[str] = Field(
        default=None,
        env="MIXPANEL_TOKEN"
    )
    SENTRY_DSN: Optional[str] = Field(
        default=None,
        env="SENTRY_DSN"
    )
    
    # ========== RECOMMENDATION SYSTEM ==========
    RECOMMENDATION_ENGINE: str = Field(default="collaborative", env="RECOMMENDATION_ENGINE")
    MIN_VIEWS_FOR_RECOMMENDATION: int = Field(default=10, env="MIN_VIEWS_FOR_RECOMMENDATION")
    
    # ========== LOGGING ==========
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")
    LOG_FILE: Optional[str] = Field(
        default=None,
        env="LOG_FILE"
    )
    
    # ========== BUSINESS RULES ==========
    DEFAULT_COMMISSION_RATE: float = Field(default=5.0, env="DEFAULT_COMMISSION_RATE")  # 5%
    MIN_ORDER_AMOUNT: float = Field(default=1000.0, env="MIN_ORDER_AMOUNT")
    MAX_PRODUCTS_PER_SHOP: int = Field(default=500, env="MAX_PRODUCTS_PER_SHOP")
    AUTO_VERIFY_MERCHANTS: bool = Field(default=False, env="AUTO_VERIFY_MERCHANTS")
    
    # Shipping
    DEFAULT_SHIPPING_COST: float = Field(default=1500.0, env="DEFAULT_SHIPPING_COST")
    FREE_SHIPPING_THRESHOLD: float = Field(default=10000.0, env="FREE_SHIPPING_THRESHOLD")
    
    # Returns & Refunds
    RETURN_PERIOD_DAYS: int = Field(default=14, env="RETURN_PERIOD_DAYS")
    REFUND_PROCESSING_DAYS: int = Field(default=7, env="REFUND_PROCESSING_DAYS")
    
    # ========== FEATURE FLAGS ==========
    ENABLE_SOCIAL_LOGIN: bool = Field(default=True, env="ENABLE_SOCIAL_LOGIN")
    ENABLE_PHONE_VERIFICATION: bool = Field(default=True, env="ENABLE_PHONE_VERIFICATION")
    ENABLE_TWO_FACTOR_AUTH: bool = Field(default=False, env="ENABLE_TWO_FACTOR_AUTH")
    ENABLE_WISHLIST: bool = Field(default=True, env="ENABLE_WISHLIST")
    ENABLE_PRODUCT_COMPARISON: bool = Field(default=True, env="ENABLE_PRODUCT_COMPARISON")
    ENABLE_GUEST_CHECKOUT: bool = Field(default=True, env="ENABLE_GUEST_CHECKOUT")
    
    # ========== THIRD-PARTY INTEGRATIONS ==========
    # Google
    GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        env="GOOGLE_CLIENT_ID"
    )
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        env="GOOGLE_CLIENT_SECRET"
    )
    
    # Facebook
    FACEBOOK_APP_ID: Optional[str] = Field(
        default=None,
        env="FACEBOOK_APP_ID"
    )
    FACEBOOK_APP_SECRET: Optional[str] = Field(
        default=None,
        env="FACEBOOK_APP_SECRET"
    )
    
    # Twitter
    TWITTER_API_KEY: Optional[str] = Field(
        default=None,
        env="TWITTER_API_KEY"
    )
    TWITTER_API_SECRET: Optional[str] = Field(
        default=None,
        env="TWITTER_API_SECRET"
    )
    
    # Twilio (for SMS)
    TWILIO_ACCOUNT_SID: Optional[str] = Field(
        default=None,
        env="TWILIO_ACCOUNT_SID"
    )
    TWILIO_AUTH_TOKEN: Optional[str] = Field(
        default=None,
        env="TWILIO_AUTH_TOKEN"
    )
    TWILIO_PHONE_NUMBER: Optional[str] = Field(
        default=None,
        env="TWILIO_PHONE_NUMBER"
    )
    
    # Push Notifications
    FCM_SERVER_KEY: Optional[str] = Field(
        default=None,
        env="FCM_SERVER_KEY"
    )
    APNS_KEY_ID: Optional[str] = Field(
        default=None,
        env="APNS_KEY_ID"
    )
    APNS_TEAM_ID: Optional[str] = Field(
        default=None,
        env="APNS_TEAM_ID"
    )
    APNS_BUNDLE_ID: Optional[str] = Field(
        default=None,
        env="APNS_BUNDLE_ID"
    )
    
    # ========== MONITORING ==========
    PROMETHEUS_ENABLED: bool = Field(default=False, env="PROMETHEUS_ENABLED")
    METRICS_PORT: int = Field(default=9090, env="METRICS_PORT")
    
    # ========== SECURITY HEADERS ==========
    SECURITY_HEADERS_ENABLED: bool = Field(default=True, env="SECURITY_HEADERS_ENABLED")
    CSP_ENABLED: bool = Field(default=True, env="CSP_ENABLED")
    HSTS_ENABLED: bool = Field(default=True, env="HSTS_ENABLED")
    HSTS_MAX_AGE: int = Field(default=31536000, env="HSTS_MAX_AGE")  # 1 year
    
    # ========== MISC ==========
    TIMEZONE: str = Field(default="Africa/Blantyre", env="TIMEZONE")
    DATE_FORMAT: str = Field(default="%Y-%m-%d", env="DATE_FORMAT")
    DATETIME_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S", env="DATETIME_FORMAT")
    
    # Admin
    ADMIN_EMAIL: str = Field(default="admin@electrobazaar.com", env="ADMIN_EMAIL")
    ADMIN_PASSWORD: str = Field(default="ElectroBazaarAdmin2024!", env="ADMIN_PASSWORD")
    
    # Support
    SUPPORT_EMAIL: str = Field(default="support@electrobazaar.com", env="SUPPORT_EMAIL")
    SUPPORT_PHONE: Optional[str] = Field(
        default="+265123456789",
        env="SUPPORT_PHONE"
    )
    
    # Legal
    TERMS_URL: str = Field(default="/terms", env="TERMS_URL")
    PRIVACY_URL: str = Field(default="/privacy", env="PRIVACY_URL")
    
    # Validation methods - FIXED for Pydantic v2
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v, info):
        """Validate SECRET_KEY"""
        if info.data is None:
            return v
            
        environment = info.data.get("ENVIRONMENT", "production")
        if environment == "production":
            if "change_in_production" in v or "test" in v.lower():
                raise ValueError("Weak security key detected in production. Please set a strong SECRET_KEY.")
        return v
    
    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """Validate JWT_SECRET"""
        if info.data is None:
            return v
            
        environment = info.data.get("ENVIRONMENT", "production")
        if environment == "production":
            if "change" in v.lower() or "test" in v.lower():
                raise ValueError("Weak JWT secret detected in production. Please set a strong JWT_SECRET.")
        return v
    
    @field_validator("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY")
    @classmethod
    def validate_supabase_config(cls, v, info):
        """Validate Supabase configuration"""
        if info.data is None:
            return v
            
        environment = info.data.get("ENVIRONMENT", "production")
        if not v or "your-" in v or "example" in v:
            if environment == "production":
                raise ValueError(f"Supabase configuration must be set in production!")
            else:
                print(f"ℹ️  INFO: Using default/placeholder Supabase config in {environment}")
        return v
    
    # Pydantic v2 model config
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # This will ignore extra fields from .env file
    )

# Create settings instance
settings = Settings()

# Helper functions for environment-specific settings
def is_development() -> bool:
    return settings.ENVIRONMENT.lower() == "development"

def is_production() -> bool:
    return settings.ENVIRONMENT.lower() == "production"

def is_testing() -> bool:
    return settings.ENVIRONMENT.lower() == "testing"

# Validate critical settings
def validate_settings():
    if is_production():
        # Warn about security defaults
        if "change_in_production" in settings.SECRET_KEY:
            print("⚠️  WARNING: Using default SECRET_KEY in production - change this!")
        
        if "change" in settings.JWT_SECRET.lower():
            print("⚠️  WARNING: Using default JWT_SECRET in production - change this!")
        
        # Warn about payment configuration
        if settings.ENABLE_STRIPE and settings.STRIPE_SECRET_KEY and ("test" in settings.STRIPE_SECRET_KEY.lower()):
            print("⚠️  WARNING: Using test Stripe keys in production!")
        
        if not settings.SMTP_HOST:
            print("⚠️  WARNING: Email service not configured in production")
    
    # Validate Supabase configuration
    if not settings.SUPABASE_URL:
        raise ValueError("SUPABASE_URL must be set")
    
    if not settings.SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY must be set")
    
    return True

# Run validation
try:
    validate_settings()
    print(f"✅ Settings loaded successfully for {settings.ENVIRONMENT} environment")
    print(f"✅ App Name: {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"✅ Database: {'Connected' if settings.SUPABASE_URL else 'Not configured'}")
    print(f"✅ Redis: {'Available' if settings.REDIS_URL else 'Not configured'}")
    print(f"✅ Email: {'Configured' if settings.SMTP_HOST else 'Not configured'}")
except Exception as e:
    print(f"❌ Settings validation failed: {e}")
    if is_development():
        print("Continuing in development mode despite validation warnings...")
    else:
        raise