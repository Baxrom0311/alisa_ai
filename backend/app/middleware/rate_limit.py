import json
import re
import time
import logging
import uuid
from collections import defaultdict
from typing import Callable, Protocol

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import settings
from ..utils.security import decode_access_token


logger = logging.getLogger(__name__)


try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    from slowapi import _rate_limit_exceeded_handler

    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    SlowAPIMiddleware = None
    RateLimitExceeded = None
    _rate_limit_exceeded_handler = None

    def get_remote_address(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    class Limiter:
        def __init__(
            self,
            key_func: Callable[[Request], str],
            enabled: bool = True,
            storage_uri: str = "memory://",
        ):
            self.key_func = key_func
            self.enabled = enabled
            self.storage_uri = storage_uri

        def limit(self, *limits: str, key_func: Callable[[Request], str] | None = None):
            def decorator(func):
                func.__rate_limits__ = limits
                func.__rate_limit_key_func__ = key_func or self.key_func
                return func

            return decorator


def _configured_storage_url() -> str:
    return settings.RATE_LIMIT_STORAGE_URL.strip() or "memory://"


def _create_limiter():
    limiter_kwargs = {
        "key_func": get_remote_address,
        "enabled": settings.RATE_LIMIT_ENABLED,
        "storage_uri": _configured_storage_url(),
    }
    return Limiter(**limiter_kwargs)


limiter = _create_limiter()
if hasattr(limiter, "enabled"):
    limiter.enabled = settings.RATE_LIMIT_ENABLED


class RateLimitStorage(Protocol):
    async def hit(self, bucket: str, identity: str, limit: str, now: float) -> int | None:
        """Record a hit and return Retry-After seconds when the limit is exceeded."""

    def reset(self) -> None:
        """Clear local state when supported."""


class InMemoryRateLimitStorage:
    def __init__(self):
        self._hits: dict[tuple[str, str, int], list[float]] = defaultdict(list)

    async def hit(self, bucket: str, identity: str, limit: str, now: float) -> int | None:
        amount, period = _parse_limit(limit)
        key = (bucket, identity, period)
        window_start = now - period
        hits = [hit for hit in self._hits[key] if hit > window_start]
        self._hits[key] = hits

        if len(hits) >= amount:
            return max(1, int(period - (now - hits[0])))

        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


class RedisRateLimitStorage:
    _HIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local amount = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local member = ARGV[5]

redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start)
local count = redis.call("ZCARD", key)
if count >= amount then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    if oldest[2] then
        return {0, oldest[2]}
    end
    return {0, now}
end

redis.call("ZADD", key, now, member)
redis.call("EXPIRE", key, ttl)
return {1, 0}
"""

    def __init__(self, storage_url: str):
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis rate-limit storage requires the 'redis' package to be installed"
            ) from exc

        self._client = redis.from_url(storage_url, decode_responses=True)

    async def hit(self, bucket: str, identity: str, limit: str, now: float) -> int | None:
        amount, period = _parse_limit(limit)
        key = f"rate-limit:{bucket}:{identity}:{period}"
        window_start = now - period
        member = f"{now}:{uuid.uuid4().hex}"
        result = await self._client.eval(
            self._HIT_SCRIPT,
            1,
            key,
            now,
            window_start,
            amount,
            period,
            member,
        )

        allowed = int(result[0]) == 1
        if allowed:
            return None

        oldest = float(result[1])
        return max(1, int(period - (now - oldest)))

    def reset(self) -> None:
        logger.info("Redis rate-limit storage reset is not performed automatically")


def _create_rate_limit_storage(storage_url: str | None = None) -> RateLimitStorage:
    resolved_url = (storage_url or _configured_storage_url()).strip() or "memory://"
    if resolved_url == "memory://":
        return InMemoryRateLimitStorage()
    if resolved_url.startswith(("redis://", "rediss://")):
        return RedisRateLimitStorage(resolved_url)
    raise RuntimeError(f"Unsupported RATE_LIMIT_STORAGE_URL: {resolved_url}")


_rate_limit_storage = (
    InMemoryRateLimitStorage() if SLOWAPI_AVAILABLE else _create_rate_limit_storage()
)


def reset_rate_limits() -> None:
    _rate_limit_storage.reset()
    if hasattr(limiter, "enabled"):
        limiter.enabled = settings.RATE_LIMIT_ENABLED

    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        try:
            storage.reset()
        except Exception:
            logger.warning("Failed to reset slowapi rate-limit storage", exc_info=True)


def user_or_remote_address(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() == "bearer" and token:
        payload = decode_access_token(token)
        subject = payload.get("sub") if payload else None
        if subject:
            return f"user:{subject}"
    return f"ip:{get_remote_address(request)}"


def _normalize_login_email(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return "unknown"


def _login_email_from_cached_body(request: Request) -> str:
    cached_email = getattr(request.state, "rate_limit_login_email", None)
    if cached_email:
        return cached_email

    body = getattr(request, "_body", None)
    if not body:
        return "unknown"

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "unknown"

    return _normalize_login_email(payload.get("email"))


def login_email_or_remote_address(request: Request) -> str:
    email = _login_email_from_cached_body(request)
    return f"login:{email}:ip:{get_remote_address(request)}"


def _parse_limit(limit: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(second|minute|hour|day)s?\s*", limit)
    if not match:
        raise ValueError(f"Unsupported rate limit format: {limit}")

    amount = int(match.group(1))
    period_name = match.group(2)
    periods = {
        "second": 1,
        "minute": 60,
        "hour": 60 * 60,
        "day": 24 * 60 * 60,
    }
    return amount, periods[period_name]


_AUTH_RULES = {
    ("POST", "/api/auth/login"): ("login", ("5/minute", "20/hour")),
    ("POST", "/api/auth/register"): ("ip", ("5/hour",)),
}

_UPLOAD_RULE = re.compile(r"^/api/books/\d+/(cover|file|audio)$")


def _rules_for_request(request: Request) -> tuple[str, tuple[str, ...]] | None:
    auth_rule = _AUTH_RULES.get((request.method, request.url.path))
    if auth_rule is not None:
        return auth_rule

    if request.method == "POST" and _UPLOAD_RULE.fullmatch(request.url.path):
        return "user", ("30/hour",)

    return None


def _bucket_for_request(request: Request) -> str:
    upload_match = _UPLOAD_RULE.fullmatch(request.url.path)
    if request.method == "POST" and upload_match:
        return f"{request.method}:/api/books/{{book_id}}/{upload_match.group(1)}"
    return f"{request.method}:{request.url.path}"


async def _login_identity_for_request(request: Request) -> str:
    body = await request.body()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        email = "unknown"
    else:
        email = _normalize_login_email(payload.get("email"))

    request.state.rate_limit_login_email = email
    return f"login:{email}:ip:{get_remote_address(request)}"


async def _identity_for_request(request: Request, identity_type: str) -> str:
    if identity_type == "login":
        return await _login_identity_for_request(request)
    if identity_type == "user":
        return user_or_remote_address(request)
    return f"ip:{get_remote_address(request)}"


class StorageBackedRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        rule = _rules_for_request(request)
        if rule is None:
            return await call_next(request)

        identity_type, limits = rule
        identity = await _identity_for_request(request, identity_type)
        bucket = _bucket_for_request(request)
        now = time.time()

        for limit in limits:
            retry_after = await _rate_limit_storage.hit(bucket, identity, limit, now)
            if retry_after is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)


def install_rate_limiter(app) -> None:
    if SLOWAPI_AVAILABLE:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
        return

    app.add_middleware(StorageBackedRateLimitMiddleware)
