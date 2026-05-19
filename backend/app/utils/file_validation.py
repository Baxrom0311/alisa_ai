from dataclasses import dataclass
from typing import AsyncIterator, Mapping

from fastapi import HTTPException, Request, UploadFile, status

from ..config import settings


CHUNK_SIZE = 64 * 1024
COVER_MAX_SIZE = 5 * 1024 * 1024

IMAGE_FILE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

BOOK_FILE_TYPES = {
    "application/pdf": "pdf",
    "application/epub+zip": "epub",
}

AUDIO_FILE_TYPES = {
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
}

_DEFAULT_EXTENSION_BY_MIME = {
    **IMAGE_FILE_TYPES,
    **BOOK_FILE_TYPES,
    **AUDIO_FILE_TYPES,
}


@dataclass(frozen=True)
class DetectedFileType:
    mime_type: str
    extension: str


@dataclass
class ValidatedUpload:
    mime_type: str
    extension: str
    first_chunk: bytes
    file: UploadFile
    max_size: int
    file_type: str
    size: int = 0

    async def iter_chunks(self) -> AsyncIterator[bytes]:
        if self.first_chunk:
            self.size = len(self.first_chunk)
            _raise_if_too_large(self.size, self.max_size, self.file_type)
            yield self.first_chunk

        while True:
            chunk = await self.file.read(CHUNK_SIZE)
            if not chunk:
                break
            self.size += len(chunk)
            _raise_if_too_large(self.size, self.max_size, self.file_type)
            yield chunk


def _raise_if_too_large(total_size: int, max_size: int, file_type: str) -> None:
    if total_size <= max_size:
        return

    raise HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"{file_type} file size exceeds maximum allowed size of {max_size // (1024 * 1024)}MB",
    )


def _normalize_allowed_types(
    allowed_types: Mapping[str, str] | set[str] | list[str] | tuple[str, ...],
) -> dict[str, str]:
    if isinstance(allowed_types, Mapping):
        return {mime.lower(): ext.lower().lstrip(".") for mime, ext in allowed_types.items()}

    normalized: dict[str, str] = {}
    for mime in allowed_types:
        lower_mime = mime.lower()
        extension = _DEFAULT_EXTENSION_BY_MIME.get(lower_mime)
        if extension is None:
            raise ValueError(f"No canonical extension configured for MIME type: {mime}")
        normalized[lower_mime] = extension
    return normalized


def _manual_sniff(data: bytes) -> DetectedFileType | None:
    if data.startswith(b"%PDF-"):
        return DetectedFileType("application/pdf", "pdf")

    if data.startswith(b"\xff\xd8\xff"):
        return DetectedFileType("image/jpeg", "jpg")

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedFileType("image/png", "png")

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return DetectedFileType("image/webp", "webp")

    if data.startswith(b"PK\x03\x04") and b"mimetype" in data[:4096] and b"application/epub+zip" in data[:4096]:
        return DetectedFileType("application/epub+zip", "epub")

    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return DetectedFileType("audio/mpeg", "mp3")

    if data.startswith(b"OggS"):
        return DetectedFileType("audio/ogg", "ogg")

    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return DetectedFileType("audio/wav", "wav")

    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xF6) == 0xF0:
        return DetectedFileType("audio/aac", "aac")

    if len(data) >= 12 and data[4:8] == b"ftyp":
        brands = data[8:64].lower()
        if any(brand in brands for brand in (b"m4a", b"mp42", b"mp41", b"isom")):
            return DetectedFileType("audio/mp4", "m4a")

    return None


def sniff_file_type(data: bytes) -> DetectedFileType | None:
    manual = _manual_sniff(data)
    if manual is not None:
        return manual

    try:
        import filetype
    except ImportError:
        return None

    kind = filetype.guess(data)
    if kind is None:
        return None

    extension = _DEFAULT_EXTENSION_BY_MIME.get(kind.mime, kind.extension)
    return DetectedFileType(kind.mime.lower(), extension.lower().lstrip("."))


def ensure_content_length_allowed(request: Request, max_size: int, file_type: str) -> None:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return

    try:
        size = int(content_length)
    except ValueError:
        return

    _raise_if_too_large(size, max_size, file_type)


def _validate_detected_type(
    detected: DetectedFileType | None,
    declared_content_type: str | None,
    allowed_types: dict[str, str],
    file_type: str,
) -> DetectedFileType:
    if not declared_content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_type} file must include a Content-Type header",
        )

    declared_mime = declared_content_type.lower()
    if declared_mime not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_type} file type must be one of: {', '.join(sorted(allowed_types))}",
        )

    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not detect {file_type.lower()} file type from file content",
        )

    sniffed_mime = detected.mime_type.lower()
    if sniffed_mime not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Detected {sniffed_mime} content is not allowed for {file_type.lower()} uploads",
        )

    declared_extension = allowed_types[declared_mime]
    sniffed_extension = allowed_types[sniffed_mime]
    if declared_extension != sniffed_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Declared {declared_mime} content does not match detected {sniffed_mime} content",
        )

    return DetectedFileType(sniffed_mime, sniffed_extension)


async def prepare_validated_upload(
    file: UploadFile,
    allowed_types: Mapping[str, str] | set[str] | list[str] | tuple[str, ...],
    max_size: int,
    file_type: str,
) -> ValidatedUpload:
    allowed = _normalize_allowed_types(allowed_types)
    first_chunk = await file.read(CHUNK_SIZE)
    if not first_chunk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_type} file must not be empty",
        )

    detected = _validate_detected_type(
        sniff_file_type(first_chunk),
        file.content_type,
        allowed,
        file_type,
    )
    return ValidatedUpload(
        mime_type=detected.mime_type,
        extension=detected.extension,
        first_chunk=first_chunk,
        file=file,
        max_size=max_size,
        file_type=file_type,
    )


async def sniff_and_validate(
    file: UploadFile,
    allowed_types: Mapping[str, str] | set[str] | list[str] | tuple[str, ...],
    max_size: int,
    file_type: str = "Upload",
) -> tuple[bytes, str]:
    """
    Validate size and magic bytes, returning the file data and canonical extension.

    Upload handlers should prefer prepare_validated_upload() plus storage.save_stream()
    so large files are not buffered in memory.
    """
    upload = await prepare_validated_upload(file, allowed_types, max_size, file_type)
    file_data = bytearray()
    async for chunk in upload.iter_chunks():
        file_data.extend(chunk)
    return bytes(file_data), upload.extension


async def validate_file_size(file: UploadFile, max_size: int, file_type: str) -> bytes:
    """Validate file size and return file data."""
    file_data = bytearray()
    total_size = 0

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break

        total_size += len(chunk)
        _raise_if_too_large(total_size, max_size, file_type)
        file_data.extend(chunk)

    return bytes(file_data)

