from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Callable, Optional
from datetime import datetime, timedelta
import redis
import json
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter (replace with Redis in production)
class RateLimiter:
    def __init__(self):
        self.requests = {}
    
    def is_rate_limited(self, key: str, limit: int, window: int) -> bool:
        """Check if rate limit is exceeded."""
        now = datetime.now()
        window_start = now - timedelta(seconds=window)
        
        # Clean up old entries
        self.requests[key] = [
            timestamp for timestamp in self.requests.get(key, [])
            if timestamp > window_start
        ]
        
        # Check limit
        if len(self.requests[key]) >= limit:
            return True
        
        # Add current request
        self.requests[key].append(now)
        return False

rate_limiter = RateLimiter()

def rate_limit(limit_str: str = "100/hour"):
    """Rate limiting decorator."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Parse limit string (e.g., "100/hour", "10/minute")
            try:
                limit, unit = limit_str.split("/")
                limit = int(limit)
                
                # Convert unit to seconds
                if unit == "second":
                    window = 1
                elif unit == "minute":
                    window = 60
                elif unit == "hour":
                    window = 3600
                elif unit == "day":
                    window = 86400
                else:
                    window = 3600  # Default to hour
                
                # Get request object
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
                
                if not request:
                    for key, value in kwargs.items():
                        if isinstance(value, Request):
                            request = value
                            break
                
                if request:
                    # Create key based on client IP and endpoint
                    client_ip = request.client.host if request.client else "unknown"
                    endpoint = request.url.path
                    key = f"{client_ip}:{endpoint}"
                    
                    # Check rate limit
                    if rate_limiter.is_rate_limited(key, limit, window):
                        raise HTTPException(
                            status_code=429,
                            detail=f"Rate limit exceeded. Try again in {window} seconds."
                        )
                
                return await func(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Rate limiting error: {str(e)}")
                # If rate limiting fails, allow the request
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# Redis-based rate limiter (for production)
class RedisRateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def check_rate_limit(
        self, 
        key: str, 
        limit: int, 
        window: int,
        request: Request
    ) -> bool:
        """Check rate limit using Redis."""
        try:
            # Use IP + endpoint as key
            client_ip = request.client.host if request.client else "unknown"
            endpoint = request.url.path
            redis_key = f"rate_limit:{client_ip}:{endpoint}"
            
            # Get current count
            current = self.redis.get(redis_key)
            if current is None:
                # First request in window
                self.redis.setex(redis_key, window, 1)
                return False
            
            current_count = int(current)
            if current_count >= limit:
                return True
            
            # Increment count
            self.redis.incr(redis_key)
            return False
            
        except Exception as e:
            logger.error(f"Redis rate limiting error: {str(e)}")
            return False

def get_rate_limit_headers(
    limit: int, 
    remaining: int, 
    reset_time: datetime
) -> dict:
    """Get rate limit headers for response."""
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(reset_time.timestamp()))
    }