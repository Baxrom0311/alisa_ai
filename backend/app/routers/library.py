from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from ..database import get_db
from ..schemas.library import (
    LibraryEntryResponse,
    LibraryListResponse,
    LibraryStatusUpdate,
    ReadingProgressUpdate,
    ReadingStatus,
)
from ..services.library_service import (
    add_to_library, remove_from_library, get_library, 
    update_status, update_reading_progress, get_favorites, get_recent_activity
)
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/favorites", response_model=List[LibraryEntryResponse])
async def get_favorite_books(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await get_favorites(db, current_user.id)


@router.get("/activity", response_model=LibraryListResponse)
async def get_library_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await get_recent_activity(db, current_user.id, skip, limit)
    return LibraryListResponse(**result)


@router.get("", response_model=LibraryListResponse)
async def get_user_library(
    status_filter: Optional[ReadingStatus] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await get_library(db, current_user.id, status_filter, skip, limit)
    return LibraryListResponse(**result)


@router.post("/{book_id}", response_model=LibraryEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_book_to_library(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await add_to_library(db, current_user.id, book_id)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_book_from_library(
    book_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await remove_from_library(db, current_user.id, book_id)


@router.put("/{book_id}/status", response_model=LibraryEntryResponse)
async def update_book_status(
    book_id: int,
    status_data: LibraryStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await update_status(db, current_user.id, book_id, status_data)


@router.put("/{book_id}/progress", response_model=LibraryEntryResponse)
async def update_book_progress(
    book_id: int,
    progress_data: ReadingProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await update_reading_progress(db, current_user.id, book_id, progress_data)
