import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.config import DEFAULT_SECRET_KEY, settings
import app.middleware.rate_limit as rate_limit_module
from app.middleware.rate_limit import (
    InMemoryRateLimitStorage,
    RedisRateLimitStorage,
    limiter,
    reset_rate_limits,
)
from app.main import (
    ALEMBIC_INI_PATH,
    ALEMBIC_SCRIPT_LOCATION,
    _bootstrap_initial_admin,
    app,
    lifespan,
)
from app.migration_lock import MIGRATION_ADVISORY_LOCK_KEY, migration_advisory_lock
from app.models.user import User
from app.utils.security import hash_password, verify_password


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_health_live_endpoint(client):
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_health_ready_endpoint(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "alembic_version", "storage_ok", "db_ok"}
    assert data["status"] == "ok"
    assert data["db_ok"] is True
    assert data["storage_ok"] is True
    assert "X-Request-ID" in response.headers


def test_get_books_empty(client):
    response = client.get("/api/books")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_get_categories_empty(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == []


def test_swagger_docs(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_unhandled_exception_handler_returns_sanitized_response():
    route_count = len(app.router.routes)

    async def raise_generic_error():
        raise RuntimeError("sensitive traceback detail")

    app.add_api_route("/api/test-unhandled-exception", raise_generic_error, methods=["GET"])
    try:
        with TestClient(app, raise_server_exceptions=False) as error_client:
            response = error_client.get("/api/test-unhandled-exception")
    finally:
        del app.router.routes[route_count:]
        app.openapi_schema = None

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "sensitive traceback detail" not in response.text
    assert "Traceback" not in response.text


def test_reset_rate_limits_rearms_limiter_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    reset_rate_limits()
    assert getattr(limiter, "enabled", False) is False

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    reset_rate_limits()
    assert getattr(limiter, "enabled", True) is True


def test_rate_limit_storage_defaults_to_memory(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_STORAGE_URL", "")

    storage = rate_limit_module._create_rate_limit_storage()

    assert isinstance(storage, InMemoryRateLimitStorage)


def test_slowapi_limiter_uses_configured_storage_url(monkeypatch):
    captured_kwargs = {}

    class CapturingLimiter:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.enabled = kwargs["enabled"]

    monkeypatch.setattr(settings, "RATE_LIMIT_STORAGE_URL", "redis://localhost:6379/3")
    monkeypatch.setattr(rate_limit_module, "Limiter", CapturingLimiter)

    created = rate_limit_module._create_limiter()

    assert created.enabled is settings.RATE_LIMIT_ENABLED
    assert captured_kwargs["storage_uri"] == "redis://localhost:6379/3"


@pytest.mark.asyncio
async def test_in_memory_rate_limit_storage_enforces_window():
    storage = InMemoryRateLimitStorage()

    assert await storage.hit("bucket", "identity", "2/minute", 1000.0) is None
    assert await storage.hit("bucket", "identity", "2/minute", 1001.0) is None
    assert await storage.hit("bucket", "identity", "2/minute", 1002.0) == 58
    assert await storage.hit("bucket", "identity", "2/minute", 1062.0) is None


@pytest.mark.asyncio
async def test_redis_rate_limit_storage_uses_atomic_script(monkeypatch):
    class FakeRedisClient:
        def __init__(self):
            self.calls = []
            self.responses = [[1, 0], [0, 1000.0]]

        async def eval(self, *args):
            self.calls.append(args)
            return self.responses.pop(0)

    fake_client = FakeRedisClient()
    redis_module = ModuleType("redis")
    redis_asyncio_module = ModuleType("redis.asyncio")

    def from_url(url, decode_responses=False):
        assert url == "redis://localhost:6379/0"
        assert decode_responses is True
        return fake_client

    redis_asyncio_module.from_url = from_url
    redis_module.asyncio = redis_asyncio_module
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio_module)

    storage = RedisRateLimitStorage("redis://localhost:6379/0")

    assert await storage.hit("POST:/api/auth/login", "login:user:ip:test", "1/minute", 1000.0) is None
    assert await storage.hit("POST:/api/auth/login", "login:user:ip:test", "1/minute", 1001.0) == 59
    assert len(fake_client.calls) == 2
    assert fake_client.calls[0][1] == 1
    assert fake_client.calls[0][2] == "rate-limit:POST:/api/auth/login:login:user:ip:test:60"


def test_migration_advisory_lock_wraps_postgresql_connection():
    class FakeConnection:
        dialect = SimpleNamespace(name="postgresql")

        def __init__(self):
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))

    connection = FakeConnection()

    with migration_advisory_lock(connection) as locked:
        assert locked is True
        assert len(connection.calls) == 1
        assert "pg_advisory_lock" in connection.calls[0][0]

    assert len(connection.calls) == 2
    assert "pg_advisory_unlock" in connection.calls[1][0]
    assert connection.calls[0][1] == {"lock_key": MIGRATION_ADVISORY_LOCK_KEY}
    assert connection.calls[1][1] == {"lock_key": MIGRATION_ADVISORY_LOCK_KEY}


def test_migration_advisory_lock_releases_after_migration_error():
    class FakeConnection:
        dialect = SimpleNamespace(name="postgresql")

        def __init__(self):
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))

    connection = FakeConnection()

    with pytest.raises(RuntimeError, match="migration failed"):
        with migration_advisory_lock(connection):
            raise RuntimeError("migration failed")

    assert len(connection.calls) == 2
    assert "pg_advisory_unlock" in connection.calls[1][0]


def test_migration_advisory_lock_skips_non_postgresql_connection():
    class FakeConnection:
        dialect = SimpleNamespace(name="sqlite")

        def __init__(self):
            self.calls = []

        def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))

    connection = FakeConnection()

    with migration_advisory_lock(connection) as locked:
        assert locked is False

    assert connection.calls == []


@pytest.mark.asyncio
async def test_lifespan_rejects_default_secret_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_lifespan_allows_default_secret_in_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr("app.main.command.upgrade", lambda *args, **kwargs: None)

    async with lifespan(app):
        assert True


@pytest.mark.asyncio
async def test_lifespan_creates_configured_local_upload_dir(monkeypatch, tmp_path):
    upload_dir = tmp_path / "configured-uploads"
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(upload_dir))
    monkeypatch.setattr("app.main.command.upgrade", lambda *args, **kwargs: None)

    async with lifespan(app):
        assert upload_dir.is_dir()


@pytest.mark.asyncio
async def test_lifespan_skips_local_upload_dir_for_supabase(monkeypatch, tmp_path):
    upload_dir = tmp_path / "supabase-uploads"
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(upload_dir))
    monkeypatch.setattr("app.main.command.upgrade", lambda *args, **kwargs: None)

    async with lifespan(app):
        assert not upload_dir.exists()


@pytest.mark.asyncio
async def test_lifespan_resolves_alembic_paths_from_backend_dir(monkeypatch, tmp_path):
    captured = {}

    def capture_upgrade(config, revision):
        captured["config_file_name"] = config.config_file_name
        captured["script_location"] = config.get_main_option("script_location")
        captured["revision"] = revision

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr("app.main.command.upgrade", capture_upgrade)

    async with lifespan(app):
        assert True

    assert captured == {
        "config_file_name": str(ALEMBIC_INI_PATH),
        "script_location": str(ALEMBIC_SCRIPT_LOCATION),
        "revision": "head",
    }


@pytest.mark.asyncio
async def test_lifespan_reraises_migration_failures_in_production(monkeypatch):
    def fail_upgrade(*args, **kwargs):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "production-secret")
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", True)
    monkeypatch.setattr("app.main.command.upgrade", fail_upgrade)

    with pytest.raises(RuntimeError, match="migration failed"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_lifespan_skips_startup_migrations_in_production_by_default(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("upgrade should not run")

    async def pass_head_check(*args, **kwargs):
        return None

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "production-secret")
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr("app.main.command.upgrade", fail_if_called)
    monkeypatch.setattr("app.main._assert_database_at_head", pass_head_check)

    async with lifespan(app):
        assert True


@pytest.mark.asyncio
async def test_lifespan_rejects_stale_production_schema(monkeypatch):
    async def old_database_version():
        return "old-revision"

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "production-secret")
    monkeypatch.setattr(settings, "RUN_MIGRATIONS_ON_STARTUP", False)
    monkeypatch.setattr("app.main._get_database_alembic_version", old_database_version)

    with pytest.raises(RuntimeError, match="does not match Alembic head"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_initial_admin_bootstrap_from_env(db_session, monkeypatch):
    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    monkeypatch.setattr(settings, "INITIAL_ADMIN_EMAIL", "SeedAdmin@Example.COM")
    monkeypatch.setattr(settings, "INITIAL_ADMIN_PASSWORD", "adminpass123")
    monkeypatch.setattr("app.main.async_session", SessionFactory())

    await _bootstrap_initial_admin()
    await _bootstrap_initial_admin()

    result = await db_session.execute(select(User).where(User.email == "seedadmin@example.com"))
    user = result.scalar_one()

    count_result = await db_session.execute(select(func.count(User.id)))
    assert count_result.scalar_one() == 1
    assert user.is_admin is True
    assert verify_password("adminpass123", user.hashed_password)


@pytest.mark.asyncio
async def test_initial_admin_bootstrap_does_not_mutate_existing_admin(db_session, monkeypatch):
    existing_hash = hash_password("existingpass123")
    existing_admin = User(
        email="existing-admin@example.com",
        full_name="Existing Admin",
        hashed_password=existing_hash,
        is_admin=True,
    )
    db_session.add(existing_admin)
    await db_session.commit()

    class SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    monkeypatch.setattr(settings, "INITIAL_ADMIN_EMAIL", "seed-admin@example.com")
    monkeypatch.setattr(settings, "INITIAL_ADMIN_PASSWORD", "newpass123")
    monkeypatch.setattr("app.main.async_session", SessionFactory())

    await _bootstrap_initial_admin()

    result = await db_session.execute(select(User).where(User.email == "existing-admin@example.com"))
    user = result.scalar_one()
    count_result = await db_session.execute(select(func.count(User.id)))

    assert count_result.scalar_one() == 1
    assert user.full_name == "Existing Admin"
    assert user.hashed_password == existing_hash
    assert verify_password("existingpass123", user.hashed_password)
