# app/dependencies.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any, List
import time
import json
from app.utils.security import verify_token, verify_refresh_token
from app.database import supabase
from app.config import settings
from .utils.redis_client import redis_client  # Fixed import path
import jwt

# Initialize security
security = HTTPBearer(auto_error=False)

# Cache for frequently accessed users (reduces database calls)
USER_CACHE_TTL = 300  # 5 minutes
TOKEN_BLACKLIST_TTL = 3600  # 1 hour


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Get current authenticated user with caching and enhanced security.
    
    Features:
    - Token validation with expiry check
    - User caching to reduce DB calls
    - Token blacklist checking
    - Rate limiting tracking
    - Security headers validation
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = credentials.credentials
        
        # Check token blacklist (for logged out users)
        if await is_token_blacklisted(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Verify and decode token
        try:
            payload = verify_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"}
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Extract user info from token
        # IMPORTANT FIX: The "sub" field contains EMAIL, not user_id
        email = payload.get("sub")  # This is EMAIL, not ID!
        user_type = payload.get("type")
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload - missing email",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Also get user_id from separate claim if available
        user_id = payload.get("user_id")
        
        # Check cache first - try both email and user_id
        cache_key = f"user:email:{email}"
        cached_user = await redis_client.get(cache_key)
        
        if cached_user:
            try:
                user_data = json.loads(cached_user)
                
                # Verify user_id matches if provided in token
                if user_id and str(user_data.get("id")) != user_id:
                    # Token user_id doesn't match cached user, clear cache
                    await redis_client.delete(cache_key)
                else:
                    # Update last active timestamp
                    user_data["last_active"] = time.time()
                    await redis_client.setex(cache_key, USER_CACHE_TTL, json.dumps(user_data))
                    
                    # Track rate limiting
                    await track_user_request(user_data.get("id"), request)
                    
                    return user_data
            except json.JSONDecodeError:
                # Cache corrupted, fetch from DB
                pass
        
        # Fetch from database using EMAIL
        result = supabase.table("users").select(
            "id, email, name, type, phone_number, profile_picture, "
            "is_active, is_verified, created_at, updated_at, "
            "blockchain_tx_id, settings"
        ).eq("email", email).execute()  # CHANGED: Using email, not id
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = result.data[0]
        
        # Verify user_id matches if provided in token
        if user_id and str(user.get("id")) != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token user_id mismatch"
            )
        
        # Check if user is active
        # Note: is_active column might not exist - handle gracefully
        if "is_active" in user and not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated"
            )
        
        # Add default values for missing columns
        if "is_active" not in user:
            user["is_active"] = True
        if "updated_at" not in user:
            user["updated_at"] = user.get("created_at")
        if "settings" not in user:
            user["settings"] = {}
        
        # Add additional fields for convenience
        user["user_id"] = user["id"]
        user["last_active"] = time.time()
        user["token_issued_at"] = payload.get("iat")
        user["token_expires_at"] = payload.get("exp")
        
        # Cache the user by email
        await redis_client.setex(
            cache_key, 
            USER_CACHE_TTL, 
            json.dumps(user)
        )
        
        # Also cache by user_id for faster lookup if needed
        if user.get("id"):
            id_cache_key = f"user:id:{user['id']}"
            await redis_client.setex(
                id_cache_key,
                USER_CACHE_TTL,
                json.dumps(user)
            )
        
        # Track rate limiting
        await track_user_request(user.get("id"), request)
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the error for monitoring
        print(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable"
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Optional dependency that returns user if authenticated, None otherwise.
    Useful for endpoints that work for both authenticated and guest users.
    """
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


async def get_current_merchant(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current user only if they are a merchant or admin.
    """
    if current_user["type"] not in ["merchant", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access required"
        )
    
    # Additional merchant verification check
    if current_user["type"] == "merchant" and not current_user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant account needs verification"
        )
    
    return current_user


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current user only if they are an admin.
    """
    if current_user["type"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    # Additional admin privilege check
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is deactivated"
        )
    
    return current_user


async def get_current_customer(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current user only if they are a customer.
    """
    if current_user["type"] != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required"
        )
    
    # Customer-specific checks
    if not current_user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account needs email verification"
        )
    
    return current_user


async def get_refresh_token_user(
    refresh_token: str
) -> Dict[str, Any]:
    """
    Validate refresh token and return user.
    Used for token refresh endpoints.
    """
    try:
        payload = verify_refresh_token(refresh_token)
        email = payload.get("sub")  # This should be email
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Query by email since refresh tokens should follow same pattern
        result = supabase.table("users").select(
            "id, email, type, is_active"
        ).eq("email", email).execute()  # CHANGED: Query by email
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = result.data[0]
        
        if "is_active" in user and not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated"
            )
        
        return user
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}"
        )


# Rate limiting dependency
async def check_rate_limit(
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
) -> None:
    """
    Check if request exceeds rate limits.
    Different limits for authenticated vs unauthenticated users.
    """
    if not getattr(settings, 'RATE_LIMIT_ENABLED', True):
        return
    
    # Use user ID if authenticated, IP if not
    if current_user:
        identifier = current_user.get("id", "anonymous")
    else:
        identifier = request.client.host if request.client else "unknown"
    
    endpoint = request.url.path
    
    # Create rate limit key
    minute = int(time.time() / 60)
    key = f"rate_limit:{identifier}:{endpoint}:{minute}"
    
    # Get current count
    current_count = await redis_client.get(key)
    count = int(current_count) if current_count else 0
    
    # Determine limit with safe defaults
    limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)
    burst_limit = getattr(settings, 'RATE_LIMIT_BURST', 100)
    
    # Apply stricter limits for sensitive endpoints
    sensitive_endpoints = ["/auth", "/payments", "/orders"]
    if any(endpoint.startswith(ep) for ep in sensitive_endpoints):
        limit = limit // 2  # Half the normal limit for sensitive endpoints
    
    # Check if limit exceeded
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {60 - (time.time() % 60):.0f} seconds.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(60 - (time.time() % 60)))
            }
        )
    
    # Increment counter
    await redis_client.incr(key)
    if count == 0:  # Set expiry on first increment
        await redis_client.expire(key, 60)
    
    # Add rate limit headers
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(limit - count - 1),
        "X-RateLimit-Reset": str(int(60 - (time.time() % 60)))
    }


# Permission-based dependencies
def require_permission(permission: str):
    """
    Factory function to create permission-based dependencies.
    Usage: @require_permission("products.create")
    """
    async def permission_dependency(
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        # For now, using simple role-based permissions
        # In production, you might want a more sophisticated permission system
        
        role_permissions = {
            "admin": ["*"],  # Admin has all permissions
            "merchant": [
                "products.*", "orders.view_own", "analytics.view_own",
                "shop.*", "promotions.*"
            ],
            "customer": [
                "products.view", "orders.*", "reviews.*",
                "favorites.*", "profile.*"
            ]
        }
        
        user_role = current_user["type"]
        allowed_permissions = role_permissions.get(user_role, [])
        
        # Check if user has permission
        has_permission = (
            "*" in allowed_permissions or
            permission in allowed_permissions or
            any(p.endswith(".*") and permission.startswith(p[:-2]) 
                for p in allowed_permissions)
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )
        
        return current_user
    
    return permission_dependency


# Feature flag dependencies
def require_feature(feature_name: str):
    """
    Check if a feature is enabled before allowing access.
    Usage: @require_feature("social_login")
    """
    async def feature_dependency(
        current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
    ) -> Optional[Dict[str, Any]]:
        feature_flags = {
            "social_login": getattr(settings, 'ENABLE_SOCIAL_LOGIN', False),
            "phone_verification": getattr(settings, 'ENABLE_PHONE_VERIFICATION', False),
            "two_factor_auth": getattr(settings, 'ENABLE_TWO_FACTOR_AUTH', False),
            "wishlist": getattr(settings, 'ENABLE_WISHLIST', True),
            "product_comparison": getattr(settings, 'ENABLE_PRODUCT_COMPARISON', False),
            "guest_checkout": getattr(settings, 'ENABLE_GUEST_CHECKOUT', True),
        }
        
        if not feature_flags.get(feature_name, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature_name}' is not enabled"
            )
        
        return current_user
    
    return feature_dependency


# Utility functions
async def is_token_blacklisted(token: str) -> bool:
    """Check if token is in blacklist (logged out users)"""
    blacklist_key = f"token_blacklist:{token}"
    return await redis_client.exists(blacklist_key)


async def blacklist_token(token: str, expires_in: int = TOKEN_BLACKLIST_TTL):
    """Add token to blacklist (for logout)"""
    blacklist_key = f"token_blacklist:{token}"
    await redis_client.setex(blacklist_key, expires_in, "1")


async def clear_user_cache(user_id: str):
    """Clear user cache (call after user updates)"""
    cache_key = f"user:id:{user_id}"
    await redis_client.delete(cache_key)
    
    # Also clear by email cache if we have the email
    # This would require storing email in cache or fetching from DB


async def track_user_request(user_id: str, request: Request):
    """Track user activity for analytics"""
    if not getattr(settings, 'REDIS_URL', None):
        return
    
    try:
        # Store last active timestamp
        activity_key = f"user_activity:{user_id}"
        await redis_client.setex(activity_key, 3600, str(time.time()))
        
        # Store request log (limited to recent requests)
        log_key = f"user_requests:{user_id}"
        log_entry = {
            "timestamp": time.time(),
            "method": request.method,
            "path": request.url.path,
            "ip": request.client.host if request.client else "unknown"
        }
        
        # Keep only last 100 requests
        await redis_client.lpush(log_key, json.dumps(log_entry))
        await redis_client.ltrim(log_key, 0, 99)
        await redis_client.expire(log_key, 86400)  # Keep for 24 hours
    except Exception as e:
        print(f"Error tracking user request: {e}")


# Specialized dependencies for specific use cases
async def get_current_user_with_shop(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current user with their shop information (for merchants).
    """
    if current_user["type"] not in ["merchant", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access required"
        )
    
    # Get shop info for merchant
    if current_user["type"] == "merchant":
        shop_result = supabase.table("shops").select("*").eq(
            "user_id", current_user["id"]
        ).execute()
        
        if shop_result.data:
            current_user["shop"] = shop_result.data[0]
        else:
            current_user["shop"] = None
    
    return current_user


async def validate_api_key(
    x_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate API key for external integrations.
    """
    api_key = getattr(settings, 'API_KEY', None)
    if not api_key or not x_api_key or x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Return a system user for API operations
    return {
        "id": "system",
        "type": "system",
        "name": "API System",
        "is_active": True,
        "is_verified": True
    }


# Response middleware to add rate limit headers
async def add_rate_limit_headers(request: Request, call_next):
    response = await call_next(request)
    
    if hasattr(request.state, 'rate_limit_headers'):
        for key, value in request.state.rate_limit_headers.items():
            response.headers[key] = str(value)
    
    return response