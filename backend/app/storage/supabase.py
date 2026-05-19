import httpx
from pathlib import PurePosixPath
from typing import AsyncIterator
from urllib.parse import quote
from .base import StorageBackend
from ..config import settings


class SupabaseStorage(StorageBackend):
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be configured for supabase storage")
        if not settings.SUPABASE_BUCKET:
            raise ValueError("SUPABASE_BUCKET must be configured for supabase storage")

        self.url = settings.SUPABASE_URL.rstrip("/")
        self.key = settings.SUPABASE_KEY
        self.bucket = settings.SUPABASE_BUCKET.strip("/")
        self.base_url = f"{self.url}/storage/v1/object/{self.bucket}"
        
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        if self._client is None:
            return

        aclose = getattr(self._client, "aclose", None)
        if aclose is not None:
            await aclose()
        self._client = None

    def _upload_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = dict(self.headers)
        headers["x-upsert"] = "true"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _validate_path(self, path: str) -> str:
        storage_path = PurePosixPath(path)
        if not path or path == "." or storage_path.is_absolute():
            raise ValueError("Storage path must be relative")
        if "\\" in path:
            raise ValueError("Storage path must use POSIX separators")
        if any(part in {"", ".", ".."} for part in storage_path.parts):
            raise ValueError("Storage path escapes base directory")

        normalized_path = storage_path.as_posix()
        if normalized_path != path:
            raise ValueError("Storage path must be normalized")
        return normalized_path

    def _object_url(self, path: str) -> str:
        safe_path = self._validate_path(path)
        return f"{self.base_url}/{quote(safe_path, safe='/')}"
    
    async def save(
        self,
        file_data: bytes,
        path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload file to Supabase Storage"""
        async def chunks() -> AsyncIterator[bytes]:
            yield file_data

        return await self.save_stream(chunks(), path, content_type=content_type)

    async def save_stream(
        self,
        chunks: AsyncIterator[bytes],
        path: str,
        content_type: str | None = None,
    ) -> str:
        """Upload streamed file data to Supabase Storage"""
        object_url = self._object_url(path)
        client = self._get_client()
        response = await client.post(
            object_url,
            content=chunks,
            headers=self._upload_headers(content_type),
        )
        response.raise_for_status()
        return path
    
    async def get(self, path: str) -> AsyncIterator[bytes]:
        """Download file from Supabase Storage in chunks"""
        object_url = self._object_url(path)
        client = self._get_client()
        async with client.stream("GET", object_url, headers=self.headers) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(64 * 1024):  # 64KB chunks
                yield chunk

    async def get_range(self, path: str, start: int, end: int) -> AsyncIterator[bytes]:
        """Download an inclusive byte range from Supabase Storage."""
        headers = dict(self.headers)
        headers["Range"] = f"bytes={start}-{end}"

        object_url = self._object_url(path)
        client = self._get_client()
        async with client.stream("GET", object_url, headers=headers) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(64 * 1024):
                yield chunk
    
    async def delete(self, path: str) -> None:
        """Delete file from Supabase Storage"""
        object_url = self._object_url(path)
        client = self._get_client()
        response = await client.delete(
            object_url,
            headers=self.headers
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
    
    async def exists(self, path: str) -> bool:
        """Check if file exists in Supabase Storage"""
        object_url = self._object_url(path)
        client = self._get_client()
        try:
            response = await client.head(
                object_url,
                headers=self.headers
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_size(self, path: str) -> int | None:
        """Return file size from Supabase object metadata when available."""
        object_url = self._object_url(path)
        client = self._get_client()
        try:
            response = await client.head(
                object_url,
                headers=self.headers
            )
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None

        content_length = response.headers.get("content-length")
        if not content_length:
            return None

        try:
            return int(content_length) if content_length else None
        except ValueError:
            return None
