import os
from typing import List, Optional, Union
from pydantic import Field, validator, SecretStr, model_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # ========== APP CONFIGURATION ==========
    APP_NAME: str = "ElectroBazaar"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    
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
        default="development-secret-key-change-in-production",
        env="SECRET_KEY"
    )
    JWT_SECRET: str = Field(
        default="development-jwt-secret-change-in-production",
        env="JWT_SECRET"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # Password hashing
    BCRYPT_ROUNDS: int = Field(default=12, env="BCRYPT_ROUNDS")
    
    # ========== DATABASE ==========
    SUPABASE_URL: str = Field(
        default="",
        env="SUPABASE_URL"
    )
    SUPABASE_KEY: str = Field(
        default="",
        env="SUPABASE_KEY"
    )
    SUPABASE_SERVICE_KEY: Optional[str] = Field(
        default=None,
        env="SUPABASE_SERVICE_KEY"
    )
    SUPABASE_STORAGE_BUCKET: str = Field(default="products", env="SUPABASE_STORAGE_BUCKET")
    SUPABASE_DB_POOL_SIZE: int = Field(default=10, env="SUPABASE_DB_POOL_SIZE")
    
    # ========== PAYMENT PROCESSING ==========
    STRIPE_SECRET_KEY: Optional[str] = Field(
        default=None,
        env="STRIPE_SECRET_KEY"
    )
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(
        default=None,
        env="STRIPE_PUBLISHABLE_KEY"
    )
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(
        default=None,
        env="STRIPE_WEBHOOK_SECRET"
    )
    
    # Payment methods
    ENABLE_STRIPE: bool = Field(default=False, env="ENABLE_STRIPE")
    ENABLE_PAYPAL: bool = Field(default=False, env="ENABLE_PAYPAL")
    ENABLE_MPESA: bool = Field(default=False, env="ENABLE_MPESA")
    
    # Currency
    DEFAULT_CURRENCY: str = Field(default="USD", env="DEFAULT_CURRENCY")
    
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
    
    EMAILS_FROM_EMAIL: str = Field(default="noreply@example.com", env="EMAILS_FROM_EMAIL")
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
        default=["http://localhost:3000", "http://localhost:8081"],
        env="BACKEND_CORS_ORIGINS"
    )
    
    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # ========== RATE LIMITING ==========
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_BURST: int = Field(default=10, env="RATE_LIMIT_BURST")
    
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
    DEFAULT_COMMISSION_RATE: float = Field(default=5.0, env="DEFAULT_COMMISSION_RATE")
    MIN_ORDER_AMOUNT: float = Field(default=0.0, env="MIN_ORDER_AMOUNT")
    MAX_PRODUCTS_PER_SHOP: int = Field(default=1000, env="MAX_PRODUCTS_PER_SHOP")
    AUTO_VERIFY_MERCHANTS: bool = Field(default=False, env="AUTO_VERIFY_MERCHANTS")
    
    # Shipping
    DEFAULT_SHIPPING_COST: float = Field(default=5.0, env="DEFAULT_SHIPPING_COST")
    FREE_SHIPPING_THRESHOLD: float = Field(default=50.0, env="FREE_SHIPPING_THRESHOLD")
    
    # Returns & Refunds
    RETURN_PERIOD_DAYS: int = Field(default=30, env="RETURN_PERIOD_DAYS")
    REFUND_PROCESSING_DAYS: int = Field(default=7, env="REFUND_PROCESSING_DAYS")
    
    # ========== FEATURE FLAGS ==========
    ENABLE_SOCIAL_LOGIN: bool = Field(default=False, env="ENABLE_SOCIAL_LOGIN")
    ENABLE_PHONE_VERIFICATION: bool = Field(default=False, env="ENABLE_PHONE_VERIFICATION")
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
    HSTS_MAX_AGE: int = Field(default=31536000, env="HSTS_MAX_AGE")
    
    # ========== MISC ==========
    TIMEZONE: str = Field(default="UTC", env="TIMEZONE")
    DATE_FORMAT: str = Field(default="%Y-%m-%d", env="DATE_FORMAT")
    DATETIME_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S", env="DATETIME_FORMAT")
    
    # Admin
    ADMIN_EMAIL: str = Field(default="admin@example.com", env="ADMIN_EMAIL")
    ADMIN_PASSWORD: Optional[str] = Field(
        default=None,
        env="ADMIN_PASSWORD"
    )
    
    # Support
    SUPPORT_EMAIL: str = Field(default="support@example.com", env="SUPPORT_EMAIL")
    SUPPORT_PHONE: Optional[str] = Field(
        default=None,
        env="SUPPORT_PHONE"
    )
    
    # Legal
    TERMS_URL: str = Field(default="/terms", env="TERMS_URL")
    PRIVACY_URL: str = Field(default="/privacy", env="PRIVACY_URL")
    
    # Pydantic v2 validator - FIXED SIGNATURE
    @model_validator(mode='after')
    def validate_security_keys(self):
        """Validate security keys after model is created"""
        if self.ENVIRONMENT == "production":
            # Check SECRET_KEY
            if not self.SECRET_KEY or "change" in self.SECRET_KEY.lower() or "development" in self.SECRET_KEY.lower() or len(self.SECRET_KEY) < 32:
                print(f"⚠️  WARNING: Using weak SECRET_KEY in production: {self.SECRET_KEY[:20]}...")
                print("   Please set a strong SECRET_KEY in production!")
            
            # Check JWT_SECRET
            if not self.JWT_SECRET or "change" in self.JWT_SECRET.lower() or "development" in self.JWT_SECRET.lower() or len(self.JWT_SECRET) < 32:
                print(f"⚠️  WARNING: Using weak JWT_SECRET in production: {self.JWT_SECRET[:20]}...")
                print("   Please set a strong JWT_SECRET in production!")
            
            # Check Supabase configuration
            if not self.SUPABASE_URL or not self.SUPABASE_KEY:
                print("❌ ERROR: Supabase configuration is required in production")
                print("   Please set SUPABASE_URL and SUPABASE_KEY")
                # Don't raise error here, let the validation function handle it
        
        return self
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Helper functions
def is_development() -> bool:
    return settings.ENVIRONMENT.lower() == "development"

def is_production() -> bool:
    return settings.ENVIRONMENT.lower() == "production"

def is_testing() -> bool:
    return settings.ENVIRONMENT.lower() == "testing"

# Validate settings
def validate_settings():
    if is_production():
        # Check required settings
        required = [
            ("SECRET_KEY", settings.SECRET_KEY),
            ("JWT_SECRET", settings.JWT_SECRET),
            ("SUPABASE_URL", settings.SUPABASE_URL),
            ("SUPABASE_KEY", settings.SUPABASE_KEY),
        ]
        
        missing = []
        for name, value in required:
            if not value or value.strip() == "":
                missing.append(name)
        
        if missing:
            raise ValueError(f"Missing required settings in production: {', '.join(missing)}")
        
        # Warn about weak keys
        if "change" in settings.SECRET_KEY.lower():
            print("⚠️  WARNING: Using default SECRET_KEY in production - please change this!")
        
        if "change" in settings.JWT_SECRET.lower():
            print("⚠️  WARNING: Using default JWT_SECRET in production - please change this!")
    
    return True

# Run validation
try:
    validate_settings()
    print(f"✅ Settings loaded successfully for {settings.ENVIRONMENT} environment")
    print(f"✅ App Name: {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"✅ Database: {'Configured' if settings.SUPABASE_URL and settings.SUPABASE_URL.strip() else 'Not configured'}")
    print(f"✅ Redis: {'Available' if settings.REDIS_URL else 'Not configured'}")
    print(f"✅ Email: {'Configured' if settings.SMTP_HOST else 'Not configured'}")
except Exception as e:
    print(f"❌ Settings validation failed: {e}")
    if is_development():
        print("Continuing in development mode despite validation warnings...")
    else:
        raise