from contextlib import contextmanager
import logging
from typing import Iterator

from sqlalchemy import text


logger = logging.getLogger(__name__)

# Stable signed int64 key derived from "kitobxon"; used only for PostgreSQL advisory locks.
MIGRATION_ADVISORY_LOCK_KEY = int.from_bytes(b"kitobxon", "big", signed=False)


def _uses_postgresql(connection) -> bool:
    return getattr(getattr(connection, "dialect", None), "name", None) == "postgresql"


@contextmanager
def migration_advisory_lock(connection) -> Iterator[bool]:
    """Serialize PostgreSQL migrations across concurrent app startups."""
    if not _uses_postgresql(connection):
        yield False
        return

    connection.execute(
        text("SELECT pg_advisory_lock(:lock_key)"),
        {"lock_key": MIGRATION_ADVISORY_LOCK_KEY},
    )
    try:
        yield True
    finally:
        try:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": MIGRATION_ADVISORY_LOCK_KEY},
            )
        except Exception:
            logger.warning("Failed to release PostgreSQL migration advisory lock", exc_info=True)
