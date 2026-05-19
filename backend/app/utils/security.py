from datetime import datetime, timedelta, timezone
from typing import Optional
import base64
import bcrypt
import binascii
import hashlib
import hmac
import json
from uuid import uuid4

try:
    import jwt
    from jwt import InvalidTokenError
except ImportError:  # pragma: no cover - dependency fallback for constrained local envs
    jwt = None

    class InvalidTokenError(Exception):
        pass

from ..config import settings


REQUIRED_TOKEN_CLAIMS = ("exp", "iat", "nbf", "sub", "typ", "tv", "iss", "aud", "jti")
SUPPORTED_TOKEN_TYPES = {"access", "refresh"}
PASSWORD_HASH_SCHEME_PREFIX = "bcrypt-sha256$"
_BCRYPT_MAX_PASSWORD_BYTES = 72
_PASSWORD_PREHASH_DOMAIN = b"kitobxon-password-bcrypt-sha256-v1:"


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")


def _prehash_password(password: str) -> bytes:
    digest = hashlib.sha256(_PASSWORD_PREHASH_DOMAIN + _password_bytes(password)).hexdigest()
    return digest.encode("ascii")


def hash_password(password: str) -> str:
    """Hash password without exposing bcrypt's 72-byte truncation behavior."""
    password_bytes = _prehash_password(password)
    salt = bcrypt.gensalt()
    return PASSWORD_HASH_SCHEME_PREFIX + bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash"""
    if hashed_password.startswith(PASSWORD_HASH_SCHEME_PREFIX):
        stored_hash = hashed_password.removeprefix(PASSWORD_HASH_SCHEME_PREFIX)
        return bcrypt.checkpw(_prehash_password(plain_password), stored_hash.encode("utf-8"))

    password_bytes = _password_bytes(plain_password)
    if len(password_bytes) > _BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def _validate_token_claims(payload: dict) -> dict | None:
    if any(claim not in payload for claim in REQUIRED_TOKEN_CLAIMS):
        return None

    if payload.get("iss") != settings.JWT_ISSUER:
        return None
    if payload.get("aud") != settings.JWT_AUDIENCE:
        return None

    token_type = payload.get("typ")
    if token_type not in SUPPORTED_TOKEN_TYPES:
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal():
        return None

    token_version = payload.get("tv")
    if isinstance(token_version, bool) or not isinstance(token_version, int):
        return None

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return None

    return payload


def _json_default(value):
    if isinstance(value, datetime):
        return int(value.timestamp())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _encode_hs256_token(payload: dict) -> str:
    if settings.ALGORITHM != "HS256":
        raise RuntimeError("PyJWT is required for non-HS256 JWT algorithms")

    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _base64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _base64url_encode(
        json.dumps(payload, default=_json_default, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def _decode_hs256_token(token: str) -> dict:
    if settings.ALGORITHM != "HS256":
        raise RuntimeError("PyJWT is required for non-HS256 JWT algorithms")

    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        header = json.loads(_base64url_decode(header_segment))
        payload = json.loads(_base64url_decode(payload_segment))
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidTokenError("Malformed token")

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise InvalidTokenError("Unsupported token header")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    try:
        signature = _base64url_decode(signature_segment)
    except (ValueError, binascii.Error):
        raise InvalidTokenError("Malformed token signature")

    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidTokenError("Invalid token signature")

    now = int(datetime.now(timezone.utc).timestamp())
    for claim in ("exp", "iat", "nbf"):
        if isinstance(payload.get(claim), bool) or not isinstance(payload.get(claim), int):
            raise InvalidTokenError(f"Invalid {claim} claim")

    if payload["exp"] <= now:
        raise InvalidTokenError("Token has expired")
    if payload["nbf"] > now or payload["iat"] > now:
        raise InvalidTokenError("Token is not yet valid")

    return payload


def _create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    if token_type not in SUPPORTED_TOKEN_TYPES:
        raise ValueError(f"Unsupported token type: {token_type}")

    if "sub" not in data or "tv" not in data:
        raise ValueError("JWT subject and token version are required")

    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode["sub"] = str(to_encode["sub"])
    to_encode["tv"] = int(to_encode["tv"])
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "typ": token_type,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": uuid4().hex,
    })
    if jwt is None:
        return _encode_hs256_token(to_encode)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    expires = expires_delta or timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    return _create_token(data, "access", expires)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    expires = expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(data, "refresh", expires)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        if jwt is None:
            payload = _decode_hs256_token(token)
        else:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                issuer=settings.JWT_ISSUER,
                audience=settings.JWT_AUDIENCE,
                options={"require": list(REQUIRED_TOKEN_CLAIMS)},
            )
        return _validate_token_claims(payload)
    except (InvalidTokenError, ValueError, RuntimeError, binascii.Error):
        return None
