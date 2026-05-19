import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.database import get_db, Base
from app.config import settings
from app.middleware.rate_limit import reset_rate_limits


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session, tmp_path):
    original_storage_backend = settings.STORAGE_BACKEND
    original_storage_path = settings.LOCAL_STORAGE_PATH
    original_rate_limit_enabled = settings.RATE_LIMIT_ENABLED
    original_rate_limit_storage_url = settings.RATE_LIMIT_STORAGE_URL
    original_run_migrations = settings.RUN_MIGRATIONS_ON_STARTUP
    settings.STORAGE_BACKEND = "local"
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "uploads")
    settings.RATE_LIMIT_ENABLED = False
    settings.RATE_LIMIT_STORAGE_URL = "memory://"
    settings.RUN_MIGRATIONS_ON_STARTUP = False
    reset_rate_limits()

    monkeypatch = MonkeyPatch()
    monkeypatch.setattr("app.main.command.upgrade", lambda *args, **kwargs: None)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        monkeypatch.undo()
        settings.STORAGE_BACKEND = original_storage_backend
        settings.LOCAL_STORAGE_PATH = original_storage_path
        settings.RATE_LIMIT_ENABLED = original_rate_limit_enabled
        settings.RATE_LIMIT_STORAGE_URL = original_rate_limit_storage_url
        settings.RUN_MIGRATIONS_ON_STARTUP = original_run_migrations
        reset_rate_limits()


@pytest.fixture
def auth_headers(client: TestClient):
    """Create a user and return auth headers"""
    # Register a test user
    user_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    register_response = client.post("/api/auth/register", json=user_data)
    assert register_response.status_code == 201
    
    # Login to get token
    login_data = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    login_response = client.post("/api/auth/login", json=login_data)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}
