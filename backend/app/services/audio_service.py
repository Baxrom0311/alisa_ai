from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status, UploadFile
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional
from datetime import datetime, timezone
import aiofiles
import logging
import tempfile
import uuid
import wave

from ..config import settings
from ..models.audio import AudioFile
from ..models.library import LibraryEntry, ListeningProgress
from ..models.book import Book
from ..schemas.audio import AudioProgressUpdate, AudioProgressResponse
from ..schemas.library import UNSTARTED_READING_STATUSES
from ..services.storage_service import get_storage_backend
from ..utils.file_validation import AUDIO_FILE_TYPES, prepare_validated_upload


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioMetadata:
    duration_seconds: float
    format: str
    bitrate: int | None


def _extract_metadata_with_mutagen(file_path: str, detected_format: str) -> AudioMetadata | None:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None

    try:
        parsed = MutagenFile(file_path)
    except Exception:
        return None
    if parsed is None or parsed.info is None:
        return None

    duration_seconds = getattr(parsed.info, "length", None)
    if duration_seconds is None or duration_seconds <= 0:
        return None

    bitrate = getattr(parsed.info, "bitrate", None)
    bitrate_kbps = max(1, round(bitrate / 1000)) if bitrate else None
    return AudioMetadata(
        duration_seconds=float(duration_seconds),
        format=detected_format,
        bitrate=bitrate_kbps,
    )


def _extract_wav_metadata(file_path: str, detected_format: str) -> AudioMetadata | None:
    if detected_format != "wav":
        return None

    try:
        with wave.open(file_path, "rb") as audio:
            frame_rate = audio.getframerate()
            frame_count = audio.getnframes()
            channel_count = audio.getnchannels()
            sample_width = audio.getsampwidth()
    except (EOFError, wave.Error):
        return None

    if frame_rate <= 0 or frame_count <= 0:
        return None

    bitrate = round(frame_rate * channel_count * sample_width * 8 / 1000)
    return AudioMetadata(
        duration_seconds=frame_count / frame_rate,
        format=detected_format,
        bitrate=max(1, bitrate),
    )


def _extract_audio_metadata(file_path: str, detected_format: str) -> AudioMetadata:
    metadata = (
        _extract_metadata_with_mutagen(file_path, detected_format)
        or _extract_wav_metadata(file_path, detected_format)
    )
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract audio metadata from file",
        )
    return metadata


def _relative_difference(value: float, expected: float) -> float:
    return abs(value - expected) / expected


def _ensure_metadata_matches_client_claims(
    metadata: AudioMetadata,
    duration_seconds: float | None,
    format: str | None,
    bitrate: int | None,
) -> None:
    if duration_seconds is not None and _relative_difference(duration_seconds, metadata.duration_seconds) > 0.02:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duration field does not match extracted audio metadata",
        )

    if format is not None and format.lower() != metadata.format:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format field '{format}' does not match detected '{metadata.format}' content",
        )

    if bitrate is not None and metadata.bitrate is not None and _relative_difference(bitrate, metadata.bitrate) > 0.02:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bitrate field does not match extracted audio metadata",
        )


async def _delete_upload_path(storage, path: str, context: str) -> None:
    try:
        await storage.delete(path)
    except Exception:
        logger.warning("Failed to delete %s: %s", context, path, exc_info=True)


async def get_audio_file(db: AsyncSession, book_id: int) -> AudioFile:
    result = await db.execute(select(AudioFile).where(AudioFile.book_id == book_id))
    audio = result.scalar_one_or_none()
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found"
        )
    return audio


async def upload_audio(
    db: AsyncSession, 
    book_id: int, 
    file: UploadFile,
    duration_seconds: float | None = None,
    format: str | None = None,
    bitrate: Optional[int] = None
) -> AudioFile:
    # Check if book exists
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    # Check if audio already exists for this book
    result = await db.execute(select(AudioFile).where(AudioFile.book_id == book_id))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio file already exists for this book"
        )
    
    upload = await prepare_validated_upload(
        file,
        AUDIO_FILE_TYPES,
        settings.MAX_AUDIO_FILE_SIZE,
        "Audio",
    )

    unique_filename = f"audio/{uuid.uuid4()}.{upload.extension}"
    storage = get_storage_backend()
    probe_file = tempfile.NamedTemporaryFile(delete=False)
    probe_path = probe_file.name
    probe_file.close()
    stored_path = unique_filename

    try:
        async def persisted_chunks() -> AsyncIterator[bytes]:
            async with aiofiles.open(probe_path, "wb") as probe:
                async for chunk in upload.iter_chunks():
                    await probe.write(chunk)
                    yield chunk

        stored_path = await storage.save_stream(
            persisted_chunks(),
            unique_filename,
            content_type=upload.mime_type,
        )
        metadata = _extract_audio_metadata(probe_path, upload.extension)
        _ensure_metadata_matches_client_claims(
            metadata,
            duration_seconds,
            format,
            bitrate,
        )
    except BaseException:
        await _delete_upload_path(storage, stored_path, "partial audio upload")
        raise
    finally:
        Path(probe_path).unlink(missing_ok=True)
    
    # Create audio record
    audio_file = AudioFile(
        book_id=book_id,
        file_path=stored_path,
        duration_seconds=metadata.duration_seconds,
        format=metadata.format,
        bitrate=metadata.bitrate,
        file_size=upload.size
    )
    
    db.add(audio_file)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        await _delete_upload_path(storage, stored_path, "conflicted audio upload")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio file already exists for this book"
        )
    await db.refresh(audio_file)
    
    return audio_file


async def get_audio_stream(db: AsyncSession, book_id: int) -> AsyncIterator[bytes]:
    # Get audio file (should exist since we checked in router)
    audio = await get_audio_file(db, book_id)
    
    # Stream from storage
    storage = get_storage_backend()
    async for chunk in storage.get(audio.file_path):
        yield chunk


async def save_progress(
    db: AsyncSession, 
    user_id: int, 
    book_id: int, 
    progress_data: AudioProgressUpdate
) -> ListeningProgress:
    # Get audio file
    audio = await get_audio_file(db, book_id)

    if progress_data.position_seconds > audio.duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Position cannot exceed audio duration"
        )
    
    # Get or create progress record
    result = await db.execute(
        select(ListeningProgress).where(
            ListeningProgress.user_id == user_id,
            ListeningProgress.audio_id == audio.id
        )
    )
    progress = result.scalar_one_or_none()
    
    if progress:
        progress.position_seconds = progress_data.position_seconds
    else:
        progress = ListeningProgress(
            user_id=user_id,
            audio_id=audio.id,
            position_seconds=progress_data.position_seconds
        )
        db.add(progress)

    result = await db.execute(
        select(LibraryEntry).where(
            LibraryEntry.user_id == user_id,
            LibraryEntry.book_id == book_id
        )
    )
    library_entry = result.scalar_one_or_none()
    if library_entry:
        library_entry.last_read_at = datetime.now(timezone.utc)
        if progress_data.position_seconds >= audio.duration_seconds:
            library_entry.status = "completed"
        elif progress_data.position_seconds > 0 and (
            library_entry.status in UNSTARTED_READING_STATUSES
            or library_entry.status == "completed"
        ):
            library_entry.status = "reading"
    
    await db.commit()
    await db.refresh(progress)
    return progress


async def get_progress(db: AsyncSession, user_id: int, book_id: int) -> AudioProgressResponse:
    # Get audio file
    audio = await get_audio_file(db, book_id)
    
    # Get progress
    result = await db.execute(
        select(ListeningProgress).where(
            ListeningProgress.user_id == user_id,
            ListeningProgress.audio_id == audio.id
        )
    )
    progress = result.scalar_one_or_none()
    
    if not progress:
        return AudioProgressResponse(
            position_seconds=0.0,
            updated_at=None
        )

    return AudioProgressResponse(
        position_seconds=progress.position_seconds,
        updated_at=progress.updated_at
    )
