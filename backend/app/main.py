from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from .database import async_session, engine, get_db
from .config import DEFAULT_SECRET_KEY, settings
from .logging_config import configure_logging
from .middleware.request_context import RequestContextMiddleware
from .middleware.rate_limit import install_rate_limiter
from .middleware.upload_limits import UploadContentLengthLimitMiddleware
from .routers import auth, books, categories, audio, library
from .services.auth_service import ensure_initial_admin
from .services.storage_service import close_storage_backend, get_storage_backend


configure_logging()
logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = BACKEND_DIR / "alembic"


def _is_production() -> bool:
    return settings.ENVIRONMENT.lower() == "production"


def _validate_startup_settings() -> None:
    if _is_production() and settings.SECRET_KEY in {DEFAULT_SECRET_KEY, ""}:
        raise RuntimeError("SECRET_KEY must be set to a strong non-default value in production")


def _alembic_config() -> Config:
    alembic_cfg = Config(str(ALEMBIC_INI_PATH))
    alembic_cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    alembic_cfg.attributes["skip_logging_config"] = True
    return alembic_cfg


def _should_run_migrations_on_startup() -> bool:
    return settings.RUN_MIGRATIONS_ON_STARTUP or settings.ENVIRONMENT.lower() == "development"


async def _get_database_alembic_version() -> str | None:
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()
    except SQLAlchemyError:
        return None


async def _get_session_alembic_version(db: AsyncSession) -> str | None:
    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar_one_or_none()
    except SQLAlchemyError:
        return None


async def _assert_database_at_head(alembic_cfg: Config) -> None:
    expected_head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    database_version = await _get_database_alembic_version()
    if database_version != expected_head:
        raise RuntimeError(
            "Database migration version "
            f"{database_version or 'missing'} does not match Alembic head {expected_head}"
        )


async def _bootstrap_initial_admin() -> None:
    if not settings.INITIAL_ADMIN_EMAIL or not settings.INITIAL_ADMIN_PASSWORD:
        return

    async with async_session() as db:
        admin = await ensure_initial_admin(db)
        if admin is not None:
            logger.info("Initial admin user ensured: %s", admin.email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_startup_settings()

    if settings.STORAGE_BACKEND.lower() == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    alembic_cfg = _alembic_config()
    if _should_run_migrations_on_startup():
        try:
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        except Exception:
            logger.exception("Could not run database migrations during startup")
            if _is_production():
                raise

    if _is_production():
        await _assert_database_at_head(alembic_cfg)

    await _bootstrap_initial_admin()
    
    try:
        yield
    finally:
        await close_storage_backend()


app = FastAPI(
    title="Kitobxon API",
    description="Book reading and audiobook listening platform",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(RequestContextMiddleware)

install_rate_limiter(app)

app.add_middleware(UploadContentLengthLimitMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(books.router)
app.include_router(categories.router)
app.include_router(categories.tag_router)
app.include_router(audio.router)
app.include_router(library.router)


@app.get("/api/health")
@app.get("/api/health/live")
async def health_check():
    return {"status": "ok"}


@app.get("/api/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    db_ok = False
    alembic_version = None
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        alembic_version = await _get_session_alembic_version(db)
    except SQLAlchemyError:
        logger.warning("Database readiness check failed", exc_info=True)

    storage_ok = False
    try:
        await get_storage_backend().exists(".healthcheck")
        storage_ok = True
    except Exception:
        logger.warning("Storage readiness check failed", exc_info=True)

    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "alembic_version": alembic_version,
        "storage_ok": storage_ok,
        "db_ok": db_ok,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
