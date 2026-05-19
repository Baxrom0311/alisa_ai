from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging
import uuid
from pathlib import PurePosixPath
from ..config import settings
from ..database import get_db
from ..schemas.book import (
    BookCreate,
    BookFilter,
    BookListResponse,
    BookResponse,
    BookUpdate,
    book_cover_url,
)
from ..services.book_service import create_book, get_book, list_books, update_book, delete_book, _get_book_model
from ..services.storage_service import get_storage_backend
from ..middleware.auth import get_current_user
from ..models.user import User
from ..utils.file_validation import (
    BOOK_FILE_TYPES,
    COVER_MAX_SIZE,
    IMAGE_FILE_TYPES,
    ensure_content_length_allowed,
    prepare_validated_upload,
)
from ..middleware.rate_limit import limiter, user_or_remote_address

router = APIRouter(prefix="/api/books", tags=["books"])
logger = logging.getLogger(__name__)


_COVER_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


async def _delete_storage_path(storage, path: str, context: str) -> None:
    try:
        await storage.delete(path)
    except Exception:
        logger.warning("Failed to delete %s from storage: %s", context, path, exc_info=True)


async def _commit_uploaded_book_asset(
    db: AsyncSession,
    storage,
    stored_path: str,
    old_path: str | None,
    new_context: str,
    old_context: str,
) -> None:
    try:
        await db.commit()
    except BaseException:
        await db.rollback()
        await _delete_storage_path(storage, stored_path, new_context)
        raise

    if old_path and old_path != stored_path:
        await _delete_storage_path(storage, old_path, old_context)


def _cover_media_type(cover_path: str) -> str:
    extension = PurePosixPath(cover_path).suffix.lower().lstrip(".")
    return _COVER_MEDIA_TYPES.get(extension, "application/octet-stream")


@router.get("", response_model=BookListResponse)
async def get_books(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=300),
    title: Optional[str] = Query(None, max_length=300),
    category_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None, max_length=80),
    genre: Optional[str] = Query(None, max_length=80),
    author: Optional[str] = Query(None, max_length=200),
    tag: Optional[str] = Query(None, max_length=40),
    db: AsyncSession = Depends(get_db)
):
    filters = BookFilter(
        search=search,
        title=title,
        category_id=category_id,
        category=category,
        genre=genre,
        author=author,
        tag=tag,
    )
    return await list_books(db, skip, limit, filters)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book_by_id(book_id: int, db: AsyncSession = Depends(get_db)):
    return await get_book(db, book_id)


@router.head("/{book_id}/cover")
@router.get("/{book_id}/cover")
async def get_book_cover(
    book_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    book = await _get_book_model(db, book_id)
    if not book.cover_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover not found"
        )

    from ..utils.streaming import create_range_response

    storage = get_storage_backend()
    media_type = _cover_media_type(book.cover_path)
    extension = PurePosixPath(book.cover_path).suffix.lower().lstrip(".") or "cover"
    return await create_range_response(
        book.cover_path,
        storage,
        media_type,
        request,
        filename=f"{book.title}.{extension}",
    )


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def create_new_book(
    book_data: BookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create books"
        )
    return await create_book(db, book_data)


@router.put("/{book_id}", response_model=BookResponse)
async def update_book_by_id(
    book_id: int,
    book_data: BookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update books"
        )
    return await update_book(db, book_id, book_data)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book_by_id(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete books"
        )
    await delete_book(db, book_id)


@router.post("/{book_id}/cover", response_model=dict)
@limiter.limit("30/hour", key_func=user_or_remote_address)
async def upload_book_cover(
    book_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ensure_content_length_allowed(request, COVER_MAX_SIZE, "Cover image")

    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload covers"
        )

    book = await _get_book_model(db, book_id)
    old_cover_path = book.cover_path

    upload = await prepare_validated_upload(
        file,
        IMAGE_FILE_TYPES,
        COVER_MAX_SIZE,
        "Cover image",
    )
    unique_filename = f"covers/{uuid.uuid4()}.{upload.extension}"

    storage = get_storage_backend()
    try:
        stored_path = await storage.save_stream(
            upload.iter_chunks(),
            unique_filename,
            content_type=upload.mime_type,
        )
    except BaseException:
        await _delete_storage_path(storage, unique_filename, "partial cover upload")
        raise
    
    book.cover_path = stored_path
    await _commit_uploaded_book_asset(
        db,
        storage,
        stored_path,
        old_cover_path,
        "new cover upload after failed database commit",
        "old cover",
    )
    
    return {
        "message": "Cover uploaded successfully",
        "path": stored_path,
        "cover_url": book_cover_url(book.id, stored_path),
    }


@router.post("/{book_id}/file", response_model=dict)
@limiter.limit("30/hour", key_func=user_or_remote_address)
async def upload_book_file(
    book_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    ensure_content_length_allowed(request, settings.MAX_BOOK_FILE_SIZE, "Book")

    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can upload book files"
        )

    book = await _get_book_model(db, book_id)
    old_file_path = book.file_path

    upload = await prepare_validated_upload(
        file,
        BOOK_FILE_TYPES,
        settings.MAX_BOOK_FILE_SIZE,
        "Book",
    )
    unique_filename = f"books/{uuid.uuid4()}.{upload.extension}"

    storage = get_storage_backend()
    try:
        stored_path = await storage.save_stream(
            upload.iter_chunks(),
            unique_filename,
            content_type=upload.mime_type,
        )
    except BaseException:
        await _delete_storage_path(storage, unique_filename, "partial book upload")
        raise
    
    book.file_path = stored_path
    book.file_type = upload.extension
    await _commit_uploaded_book_asset(
        db,
        storage,
        stored_path,
        old_file_path,
        "new book upload after failed database commit",
        "old book file",
    )
    
    return {"message": "Book file uploaded successfully", "path": stored_path}


@router.head("/{book_id}/read")
@router.get("/{book_id}/read")
async def read_book(
    book_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    book = await get_book(db, book_id)
    
    if not book.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book file not found"
        )
    
    storage = get_storage_backend()
    media_type = "application/pdf" if book.file_type == "pdf" else "application/epub+zip"
    
    from ..utils.streaming import create_range_response
    return await create_range_response(
        book.file_path,
        storage,
        media_type,
        request,
        filename=f"{book.title}.{book.file_type}"
    )
