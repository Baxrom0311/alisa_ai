import os
import uuid
import aiofiles
from pathlib import Path
from typing import AsyncIterator
from .base import StorageBackend
from ..config import settings


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.LOCAL_STORAGE_PATH).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_full_path(self, path: str) -> Path:
        storage_path = Path(path)
        if not path or storage_path.is_absolute():
            raise ValueError("Storage path must be relative")

        full_path = (self.base_path / storage_path).resolve()
        try:
            full_path.relative_to(self.base_path)
        except ValueError as exc:
            raise ValueError("Storage path escapes base directory") from exc

        return full_path
    
    def _generate_unique_filename(self, category: str, original_filename: str) -> str:
        """Generate unique filename with category prefix"""
        ext = os.path.splitext(original_filename)[1]
        unique_id = str(uuid.uuid4())
        return f"{category}/{unique_id}{ext}"
    
    async def save(self, file_data: bytes, path: str, content_type: str | None = None) -> str:
        """Save file data and return the path"""
        async def chunks() -> AsyncIterator[bytes]:
            yield file_data

        return await self.save_stream(chunks(), path, content_type=content_type)

    async def save_stream(
        self,
        chunks: AsyncIterator[bytes],
        path: str,
        content_type: str | None = None,
    ) -> str:
        """Save streamed file data and return the path"""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = full_path.with_name(f".{full_path.name}.{uuid.uuid4().hex}.tmp")

        try:
            async with aiofiles.open(temp_path, 'wb') as f:
                async for chunk in chunks:
                    await f.write(chunk)
            os.replace(temp_path, full_path)
        except BaseException:
            if temp_path.exists():
                temp_path.unlink()
            raise

        return path
    
    async def get(self, path: str) -> AsyncIterator[bytes]:
        """Get file data in chunks"""
        full_path = self._get_full_path(path)
        async with aiofiles.open(full_path, 'rb') as f:
            while True:
                chunk = await f.read(64 * 1024)  # 64KB chunks
                if not chunk:
                    break
                yield chunk

    async def get_range(self, path: str, start: int, end: int) -> AsyncIterator[bytes]:
        """Get an inclusive byte range in bounded chunks."""
        remaining = end - start + 1
        if remaining <= 0:
            return

        full_path = self._get_full_path(path)
        async with aiofiles.open(full_path, 'rb') as f:
            await f.seek(start)
            while remaining > 0:
                chunk = await f.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    
    async def delete(self, path: str) -> None:
        """Delete file"""
        full_path = self._get_full_path(path)
        if full_path.exists():
            full_path.unlink()
    
    async def exists(self, path: str) -> bool:
        """Check if file exists"""
        full_path = self._get_full_path(path)
        return full_path.exists()

    async def get_size(self, path: str) -> int | None:
        """Get file size in bytes"""
        full_path = self._get_full_path(path)
        if not full_path.exists():
            return None
        return full_path.stat().st_size
