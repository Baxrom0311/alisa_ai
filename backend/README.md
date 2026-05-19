# Kitobxon Backend

FastAPI backend for reading books, streaming audiobooks, saving progress, and managing a personal library.

## Requirements

- Python 3.11+
- SQLite for local development
- PostgreSQL-compatible async database URL for production

## Setup

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Before deploying, set `ENVIRONMENT=production`, replace `SECRET_KEY` with a long random value, and configure a production database URL. Production startup refuses the built-in default JWT signing key and refuses to start if the database Alembic revision does not match the application head.

The first registered user is promoted to admin only in `development`. For production bootstrap, set both `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD`; startup creates or promotes that user when no admin exists.

## Run

```bash
cd backend
./venv/bin/uvicorn app.main:app --reload
```

Useful URLs:

- API liveness check: `http://127.0.0.1:8000/api/health/live`
- API readiness check: `http://127.0.0.1:8000/api/health/ready`
- Swagger UI: `http://127.0.0.1:8000/docs`

The application runs Alembic migrations during startup in `development`, or in any environment when `RUN_MIGRATIONS_ON_STARTUP=true`. In production, run migrations manually before starting the API:

```bash
cd backend
./venv/bin/alembic upgrade head
```

Startup creates `LOCAL_STORAGE_PATH` only when `STORAGE_BACKEND=local`. Production readiness compares the database `alembic_version` to the current Alembic head so the API does not run against a stale schema.

Rate limits use in-process memory by default. For multi-instance deployments, set `RATE_LIMIT_STORAGE_URL` to a Redis URL so all API workers share counters:

```env
RATE_LIMIT_STORAGE_URL=redis://redis:6379/0
```

## Test

```bash
cd backend
./venv/bin/python -m pytest -v
```

## Storage

Local storage is the default and writes uploaded files under `LOCAL_STORAGE_PATH`.

Uploads are checked by magic bytes before storage. Book files accept PDF/EPUB, covers accept JPG/PNG/WebP, and audio accepts MP3/OGG/AAC/WAV/M4A. The stored extension is derived from detected content, not the client filename.

To use Supabase Storage, set:

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
SUPABASE_BUCKET=kitobxon
```

The app uses a storage abstraction, so book and audio upload flows call the same interface for local and Supabase backends.

## Main Endpoints

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `PUT /api/auth/profile`
- `GET /api/books`
- `POST /api/books`
- `POST /api/books/{id}/file`
- `GET /api/books/{id}/read`
- `POST /api/books/{id}/audio`
- `GET /api/books/{id}/audio`
- `GET /api/books/{id}/audio/stream`
- `PUT /api/books/{id}/audio/progress`
- `GET /api/library`
- `GET /api/library/activity`
- `POST /api/library/{book_id}`
- `PUT /api/library/{book_id}/status`
- `PUT /api/library/{book_id}/progress`
- `GET /api/categories`
- `POST /api/categories`
- `GET /api/tags`
- `POST /api/tags`
