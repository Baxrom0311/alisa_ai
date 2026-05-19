from ..storage.base import StorageBackend
from ..storage.local import LocalStorage
from ..storage.supabase import SupabaseStorage
from ..config import settings


_storage_backend: StorageBackend | None = None
_storage_key: tuple[str, ...] | None = None


def _current_storage_key() -> tuple[str, ...]:
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "local":
        return (backend, settings.LOCAL_STORAGE_PATH)
    if backend == "supabase":
        return (
            backend,
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY,
            settings.SUPABASE_BUCKET,
        )
    return (backend,)


def get_storage_backend() -> StorageBackend:
    """Factory function to get storage backend based on settings"""
    global _storage_backend, _storage_key

    key = _current_storage_key()
    if _storage_backend is not None and _storage_key == key:
        return _storage_backend

    backend = settings.STORAGE_BACKEND.lower()
    if backend == "local":
        _storage_backend = LocalStorage()
    elif backend == "supabase":
        _storage_backend = SupabaseStorage()
    else:
        raise ValueError(f"Unsupported storage backend: {settings.STORAGE_BACKEND}")

    _storage_key = key
    return _storage_backend


async def close_storage_backend() -> None:
    """Close any cached storage backend resources."""
    global _storage_backend, _storage_key

    storage = _storage_backend
    _storage_backend = None
    _storage_key = None

    close = getattr(storage, "close", None)
    if close is not None:
        await close()
