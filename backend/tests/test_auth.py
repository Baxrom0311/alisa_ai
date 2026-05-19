import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.middleware.rate_limit import reset_rate_limits
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import register_user, update_user_profile
from app.utils.security import create_access_token, decode_access_token, hash_password, verify_password


def _signed_hs256_token(payload: dict) -> str:
    def encode_segment(value: dict | bytes) -> str:
        raw = (
            json.dumps(value, separators=(",", ":")).encode("utf-8")
            if isinstance(value, dict)
            else value
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header_segment = encode_segment({"alg": "HS256", "typ": "JWT"})
    payload_segment = encode_segment(payload)
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{encode_segment(signature)}"


def test_register_user(client: TestClient):
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["is_admin"] == True  # First user is admin


def test_first_registered_user_is_not_admin_in_production(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    user_data = {
        "email": "prod@example.com",
        "password": "testpass123",
        "full_name": "Production User"
    }

    response = client.post("/api/auth/register", json=user_data)

    assert response.status_code == 201
    assert response.json()["is_admin"] is False


def test_register_duplicate_email(client: TestClient):
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    # First registration
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 201
    
    # Duplicate registration
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_translates_integrity_error_to_409(db_session, monkeypatch):
    async def raise_unique_conflict():
        raise IntegrityError(
            statement="",
            params={},
            orig=Exception("unique"),
        )

    monkeypatch.setattr(db_session, "commit", raise_unique_conflict)

    with pytest.raises(HTTPException) as exc_info:
        await register_user(
            db_session,
            UserCreate(
                email="race@example.com",
                password="testpass123",
                full_name="Race User",
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email already registered"


def test_register_normalizes_email_and_rejects_case_variant(client: TestClient):
    user_data = {
        "email": "MixedCase@Example.COM",
        "password": "testpass123",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 201
    assert response.json()["email"] == "mixedcase@example.com"

    duplicate_data = {
        "email": "mixedcase@example.com",
        "password": "testpass123",
        "full_name": "Duplicate User"
    }
    response = client.post("/api/auth/register", json=duplicate_data)
    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient):
    user_data = {
        "email": "short@example.com",
        "password": "12345",
        "full_name": "Short Password"
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 422


def test_register_rejects_overlong_password(client: TestClient):
    user_data = {
        "email": "long-password@example.com",
        "password": "a" * 129,
        "full_name": "Long Password"
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 422


def test_password_hash_distinguishes_bcrypt_truncation_collision():
    password = ("a" * 72) + "x"
    truncated_collision = ("a" * 72) + "y"

    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password(truncated_collision, hashed) is False


def test_legacy_short_bcrypt_hashes_remain_verifiable():
    password = "legacy-pass-123"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    assert verify_password(password, legacy_hash) is True
    assert verify_password("wrong-pass-123", legacy_hash) is False


def test_legacy_overlong_bcrypt_hashes_are_not_accepted():
    password = ("a" * 72) + "x"
    legacy_hash = bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    assert verify_password(password, legacy_hash) is False


def test_register_and_login_with_unicode_password_over_bcrypt_limit(client: TestClient):
    password = ("\U0001f510" * 20) + "securepass123"
    user_data = {
        "email": "unicode-password@example.com",
        "password": password,
        "full_name": "Unicode Password"
    }

    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={"email": "unicode-password@example.com", "password": password},
    )
    assert login_response.status_code == 200

    wrong_login_response = client.post(
        "/api/auth/login",
        json={"email": "unicode-password@example.com", "password": ("\U0001f510" * 20) + "securepass124"},
    )
    assert wrong_login_response.status_code == 401


def test_register_rejects_overlong_full_name(client: TestClient):
    user_data = {
        "email": "long-name@example.com",
        "password": "testpass123",
        "full_name": "A" * 121
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 422


def test_login_success(client: TestClient):
    # Register user first
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    # Login
    login_data = {
        "email": "test@example.com",
        "password": "testpass123"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_matches_email_case_insensitively(client: TestClient):
    user_data = {
        "email": "CaseLogin@Example.com",
        "password": "testpass123",
        "full_name": "Case Login"
    }
    client.post("/api/auth/register", json=user_data)

    login_data = {
        "email": "caselogin@example.com",
        "password": "testpass123"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client: TestClient):
    # Register user first
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    # Login with wrong password
    login_data = {
        "email": "test@example.com",
        "password": "wrongpass"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401


def test_login_nonexistent_user(client: TestClient):
    login_data = {
        "email": "nonexistent@example.com",
        "password": "testpass123"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401


def test_get_current_user(client: TestClient):
    # Register and login
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    login_data = {
        "email": "test@example.com",
        "password": "testpass123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    
    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"


def test_expired_access_token_is_rejected(client: TestClient):
    user_data = {
        "email": "expired@example.com",
        "password": "testpass123",
        "full_name": "Expired User"
    }
    register_response = client.post("/api/auth/register", json=user_data)
    assert register_response.status_code == 201
    user_id = register_response.json()["id"]
    expired_token = create_access_token(
        data={"sub": str(user_id), "tv": 0},
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401


def test_access_token_includes_hardened_claims():
    token = create_access_token(data={"sub": "42", "tv": 3})

    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["tv"] == 3
    assert payload["typ"] == "access"
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE
    assert payload["jti"]
    assert payload["iat"] <= payload["exp"]
    assert payload["nbf"] <= payload["exp"]


def test_legacy_token_missing_required_claims_is_rejected():
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    legacy_token = _signed_hs256_token({
        "sub": "1",
        "tv": 0,
        "typ": "access",
        "exp": int(expires_at.timestamp()),
    })

    assert decode_access_token(legacy_token) is None


def test_refresh_flow_returns_usable_tokens(client: TestClient):
    user_data = {
        "email": "refresh@example.com",
        "password": "testpass123",
        "full_name": "Refresh User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201
    login_response = client.post(
        "/api/auth/login",
        json={"email": "refresh@example.com", "password": "testpass123"},
    )
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]

    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == 200
    tokens = refresh_response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "refresh@example.com"


def test_refresh_rejects_access_token(client: TestClient):
    user_data = {
        "email": "refresh-access@example.com",
        "password": "testpass123",
        "full_name": "Refresh Access User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201
    login_response = client.post(
        "/api/auth/login",
        json={"email": "refresh-access@example.com", "password": "testpass123"},
    )
    assert login_response.status_code == 200

    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_response.json()["access_token"]},
    )

    assert response.status_code == 401


def test_get_current_user_no_token(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_update_profile(client: TestClient):
    # Register and login
    user_data = {
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)
    
    login_data = {
        "email": "test@example.com",
        "password": "testpass123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    token = login_response.json()["access_token"]
    
    # Update profile
    headers = {"Authorization": f"Bearer {token}"}
    update_data = {"full_name": "Updated Name"}
    response = client.put("/api/auth/profile", json=update_data, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"


def test_update_profile_can_change_email_and_normalizes(client: TestClient):
    user_data = {
        "email": "old@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=user_data)

    login_response = client.post(
        "/api/auth/login",
        json={"email": "old@example.com", "password": "testpass123"}
    )
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = client.put(
        "/api/auth/profile",
        json={"email": "NewEmail@Example.COM", "full_name": "Updated Name"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newemail@example.com"
    assert data["full_name"] == "Updated Name"

    old_login = client.post(
        "/api/auth/login",
        json={"email": "old@example.com", "password": "testpass123"}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"email": "newemail@example.com", "password": "testpass123"}
    )
    assert new_login.status_code == 200


def test_update_profile_rejects_duplicate_email_case_insensitively(client: TestClient):
    user_data = {
        "email": "owner@example.com",
        "password": "testpass123",
        "full_name": "Owner"
    }
    client.post("/api/auth/register", json=user_data)
    login_response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "testpass123"}
    )
    token = login_response.json()["access_token"]

    client.post(
        "/api/auth/register",
        json={
            "email": "taken@example.com",
            "password": "testpass123",
            "full_name": "Taken User"
        }
    )

    response = client.put(
        "/api/auth/profile",
        json={"email": "TAKEN@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


@pytest.mark.asyncio
async def test_update_profile_translates_integrity_error_to_409(db_session, monkeypatch):
    user = User(
        email="profile-race@example.com",
        full_name="Profile Race",
        hashed_password="hashed",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    async def raise_unique_conflict():
        raise IntegrityError(
            statement="",
            params={},
            orig=Exception("unique"),
        )

    monkeypatch.setattr(db_session, "commit", raise_unique_conflict)

    with pytest.raises(HTTPException) as exc_info:
        await update_user_profile(
            db_session,
            user,
            UserUpdate(email="new-profile-race@example.com"),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email already registered"


def test_password_change_invalidates_old_tokens(client: TestClient):
    user_data = {
        "email": "password-change@example.com",
        "password": "testpass123",
        "full_name": "Password Change User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201
    login_response = client.post(
        "/api/auth/login",
        json={"email": "password-change@example.com", "password": "testpass123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = client.post(
        "/api/auth/password",
        json={"current_password": "testpass123", "new_password": "newpass123"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["email"] == "password-change@example.com"

    old_me_response = client.get("/api/auth/me", headers=headers)
    assert old_me_response.status_code == 401

    old_refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert old_refresh_response.status_code == 401

    old_login_response = client.post(
        "/api/auth/login",
        json={"email": "password-change@example.com", "password": "testpass123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/auth/login",
        json={"email": "password-change@example.com", "password": "newpass123"},
    )
    assert new_login_response.status_code == 200


def test_password_change_requires_current_password(client: TestClient):
    user_data = {
        "email": "bad-current@example.com",
        "password": "testpass123",
        "full_name": "Bad Current User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201
    login_response = client.post(
        "/api/auth/login",
        json={"email": "bad-current@example.com", "password": "testpass123"},
    )
    token = login_response.json()["access_token"]

    response = client.post(
        "/api/auth/password",
        json={"current_password": "wrongpass", "new_password": "newpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect current password"


def test_logout_invalidates_old_tokens(client: TestClient):
    user_data = {
        "email": "logout@example.com",
        "password": "testpass123",
        "full_name": "Logout User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201
    login_response = client.post(
        "/api/auth/login",
        json={"email": "logout@example.com", "password": "testpass123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out."
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    ).status_code == 401


def test_login_rate_limit_triggers_429(client: TestClient, monkeypatch):
    user_data = {
        "email": "limited@example.com",
        "password": "testpass123",
        "full_name": "Limited User"
    }
    assert client.post("/api/auth/register", json=user_data).status_code == 201

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    reset_rate_limits()

    login_data = {
        "email": "limited@example.com",
        "password": "wrongpass"
    }
    for _ in range(5):
        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == 401

    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"


def test_login_rate_limit_is_scoped_to_email_and_ip(client: TestClient, monkeypatch):
    first_user = {
        "email": "limited-one@example.com",
        "password": "testpass123",
        "full_name": "Limited One"
    }
    second_user = {
        "email": "limited-two@example.com",
        "password": "testpass123",
        "full_name": "Limited Two"
    }
    assert client.post("/api/auth/register", json=first_user).status_code == 201
    assert client.post("/api/auth/register", json=second_user).status_code == 201

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    reset_rate_limits()

    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"email": "limited-one@example.com", "password": "wrongpass"},
        )
        assert response.status_code == 401

    locked_response = client.post(
        "/api/auth/login",
        json={"email": "limited-one@example.com", "password": "wrongpass"},
    )
    assert locked_response.status_code == 429

    other_email_response = client.post(
        "/api/auth/login",
        json={"email": "limited-two@example.com", "password": "wrongpass"},
    )
    assert other_email_response.status_code == 401
