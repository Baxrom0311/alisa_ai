from abc import ABC, abstractmethod
from typing import AsyncIterator


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, file_data: bytes, path: str, content_type: str | None = None) -> str:
        """Save file data to storage and return the stored path"""
        pass

    @abstractmethod
    async def save_stream(
        self,
        chunks: AsyncIterator[bytes],
        path: str,
        content_type: str | None = None,
    ) -> str:
        """Save streamed file data to storage and return the stored path"""
        pass
    
    @abstractmethod
    async def get(self, path: str) -> AsyncIterator[bytes]:
        """Get file data as async iterator"""
        pass

    @abstractmethod
    async def get_range(self, path: str, start: int, end: int) -> AsyncIterator[bytes]:
        """Get an inclusive byte range as an async iterator."""
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete file from storage"""
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists in storage"""
        pass

    @abstractmethod
    async def get_size(self, path: str) -> int | None:
        """Return file size in bytes when the backend can provide it"""
        pass
