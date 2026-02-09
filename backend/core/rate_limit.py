"""
Rate limiting middleware using Redis.
"""
import time
from typing import Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import redis.asyncio as redis

from backend.core.config import settings


class RateLimiter:
    """Rate limiter using Redis."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self.redis_client = None
        self.enabled = settings.RATE_LIMIT_ENABLED
        
        if self.enabled:
            try:
                # Parse Redis URL
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
            except Exception as e:
                print(f"Warning: Could not connect to Redis for rate limiting: {e}")
                self.enabled = False
    
    def parse_rate_limit(self, limit_string: str) -> tuple[int, int]:
        """
        Parse rate limit string like "10/minute" or "100/hour".
        
        Args:
            limit_string: Rate limit string
            
        Returns:
            Tuple of (max_requests, window_seconds)
        """
        parts = limit_string.split("/")
        max_requests = int(parts[0])
        
        period = parts[1].lower()
        if period == "second":
            window_seconds = 1
        elif period == "minute":
            window_seconds = 60
        elif period == "hour":
            window_seconds = 3600
        elif period == "day":
            window_seconds = 86400
        else:
            raise ValueError(f"Unknown period: {period}")
        
        return max_requests, window_seconds
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, dict]:
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique key for rate limiting (e.g., IP address)
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (allowed, info_dict)
        """
        if not self.enabled or not self.redis_client:
            return True, {}
        
        try:
            current_time = int(time.time())
            window_key = f"rate_limit:{key}:{current_time // window_seconds}"
            
            # Increment counter
            count = await self.redis_client.incr(window_key)
            
            # Set expiry on first request
            if count == 1:
                await self.redis_client.expire(window_key, window_seconds)
            
            allowed = count <= max_requests
            
            info = {
                "limit": max_requests,
                "remaining": max(0, max_requests - count),
                "reset": (current_time // window_seconds + 1) * window_seconds,
            }
            
            return allowed, info
            
        except Exception as e:
            print(f"Rate limit check error: {e}")
            # Fail open - allow request if Redis fails
            return True, {}
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client IP address
    """
    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Check for real IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct connection
    return request.client.host if request.client else "unknown"


async def rate_limit_middleware(
    request: Request,
    call_next: Callable,
    limit_string: str = None
) -> JSONResponse:
    """
    Rate limiting middleware.
    
    Args:
        request: FastAPI request
        call_next: Next middleware/handler
        limit_string: Rate limit string (e.g., "10/minute")
        
    Returns:
        Response
    """
    # Determine rate limit based on endpoint
    if not limit_string:
        path = request.url.path
        if path.startswith("/api/v1/public"):
            limit_string = settings.RATE_LIMIT_GUEST
        elif path.startswith("/api/v1/auth"):
            limit_string = settings.RATE_LIMIT_USER
        else:
            limit_string = settings.RATE_LIMIT_USER
    
    # Get client identifier
    client_ip = get_client_ip(request)
    
    # Parse rate limit
    max_requests, window_seconds = rate_limiter.parse_rate_limit(limit_string)
    
    # Check rate limit
    allowed, info = await rate_limiter.check_rate_limit(
        key=client_ip,
        max_requests=max_requests,
        window_seconds=window_seconds
    )
    
    # Add rate limit headers to response
    response = await call_next(request)
    
    if info:
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])
    
    # Block if rate limit exceeded
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded. Please try again later.",
                "limit": info.get("limit"),
                "reset": info.get("reset"),
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["reset"] - int(time.time())),
            }
        )
    
    return response
