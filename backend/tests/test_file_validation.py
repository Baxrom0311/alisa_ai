import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.utils.file_validation import BOOK_FILE_TYPES, ensure_content_length_allowed, sniff_and_validate, validate_file_size


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


class MockUploadFile:
    def __init__(self, content: bytes, content_type: str = "application/octet-stream"):
        self.content = content
        self.content_type = content_type
        self.position = 0
    
    async def read(self, size: int = -1):
        if size == -1:
            chunk = self.content[self.position:]
            self.position = len(self.content)
        else:
            chunk = self.content[self.position:self.position + size]
            self.position += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_file_size_validation_success():
    """Test that small files pass validation"""
    small_content = b"small file content"
    mock_file = MockUploadFile(small_content)
    
    result = await validate_file_size(mock_file, 1024, "Test")
    assert result == small_content


@pytest.mark.asyncio
async def test_file_size_validation_handles_multi_megabyte_payload():
    content = b"x" * (5 * 1024 * 1024)
    mock_file = MockUploadFile(content)

    result = await validate_file_size(mock_file, len(content), "Test")

    assert len(result) == len(content)
    assert result == content


@pytest.mark.asyncio
async def test_file_size_validation_failure():
    """Test that large files fail validation"""
    large_content = b"x" * 2048  # 2KB content
    mock_file = MockUploadFile(large_content)
    
    with pytest.raises(HTTPException) as exc_info:
        await validate_file_size(mock_file, 1024, "Test")  # 1KB limit
    
    assert exc_info.value.status_code == 413
    assert "Test file size exceeds maximum" in exc_info.value.detail


@pytest.mark.asyncio
async def test_sniff_and_validate_accepts_pdf_magic_bytes():
    mock_file = MockUploadFile(PDF_BYTES + b"content", "application/pdf")

    data, extension = await sniff_and_validate(mock_file, BOOK_FILE_TYPES, 1024, "Book")

    assert data.startswith(PDF_BYTES)
    assert extension == "pdf"


@pytest.mark.asyncio
async def test_sniff_and_validate_rejects_mismatched_magic_bytes():
    mock_file = MockUploadFile(PNG_BYTES + b"content", "application/pdf")

    with pytest.raises(HTTPException) as exc_info:
        await sniff_and_validate(mock_file, BOOK_FILE_TYPES, 1024, "Book")

    assert exc_info.value.status_code == 400
    assert "not allowed" in exc_info.value.detail


def test_content_length_oversize_rejects_before_file_read():
    request = SimpleNamespace(headers={"content-length": "2048"})

    with pytest.raises(HTTPException) as exc_info:
        ensure_content_length_allowed(request, 1024, "Book")

    assert exc_info.value.status_code == 413
