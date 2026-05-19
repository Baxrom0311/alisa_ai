from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ..config import settings
from ..database import get_db
from ..schemas.audio import AudioUploadResponse, AudioProgressUpdate, AudioProgressResponse
from ..services.audio_service import get_audio_file, upload_audio, save_progress, get_progress
from ..services.storage_service import get_storage_backend
from ..middleware.auth import get_current_user
from ..models.user import User
from ..middleware.rate_limit import limiter, user_or_remote_address
from ..utils.file_validation import ensure_content_length_allowed
from ..utils.streaming import create_range_response

router = APIRouter(prefix="/api/books", tags=["audio"])


@router.post("/{book_id}/audio", response_model=AudioUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/hour", key_func=user_or_remote_address)
async def upload_audio_file(
    book_id: int,
    request: Request,
    file: UploadFile = File(...),
    duration_seconds: Optional[float] = Form(None, gt=0, description="Duration must be positive"),
    format: Optional[str] = Form(None),
    bitrate: Optional[int] = Form(None, gt=0, description="Bitrate must be positive if provided"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ensure_content_length_allowed(request, settings.MAX_AUDIO_FILE_SIZE, "Audio")

    normalized_format = format.lower() if format is not None else None
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload audio files"
        )
    
    allowed_formats = ["mp3", "ogg", "aac", "wav", "m4a"]
    if normalized_format is not None and normalized_format not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format must be one of: {', '.join(allowed_formats)}"
        )

    return await upload_audio(db, book_id, file, duration_seconds, normalized_format, bitrate)


@router.get("/{book_id}/audio", response_model=AudioUploadResponse)
async def get_audio_metadata(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_audio_file(db, book_id)


@router.head("/{book_id}/audio/stream")
@router.get("/{book_id}/audio/stream")
async def stream_audio(
    book_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    audio = await get_audio_file(db, book_id)
    
    # Map format to MIME type
    format_to_mime = {
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "aac": "audio/aac",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "flac": "audio/flac"
    }
    media_type = format_to_mime.get(audio.format.lower(), "audio/mpeg")

    storage = get_storage_backend()
    return await create_range_response(
        audio.file_path,
        storage,
        media_type,
        request,
        filename=f"book-{book_id}.{audio.format.lower()}"
    )


@router.put("/{book_id}/audio/progress", response_model=AudioProgressResponse)
async def save_listening_progress(
    book_id: int,
    progress_data: AudioProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    progress = await save_progress(db, current_user.id, book_id, progress_data)
    return AudioProgressResponse(
        position_seconds=progress.position_seconds,
        updated_at=progress.updated_at
    )


@router.get("/{book_id}/audio/progress", response_model=AudioProgressResponse)
async def get_listening_progress(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_progress(db, current_user.id, book_id)
