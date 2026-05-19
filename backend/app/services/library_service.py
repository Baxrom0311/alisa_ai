from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime, timezone
from ..models.library import LibraryEntry
from ..models.book import Book
from ..schemas.library import LibraryStatusUpdate, ReadingProgressUpdate, LibraryEntryResponse
from ..schemas.book import BookResponse, book_cover_url


def _convert_library_entry_to_response(entry: LibraryEntry) -> LibraryEntryResponse:
    """Convert LibraryEntry model to LibraryEntryResponse"""
    book_response = None
    if entry.book:
        book_response = BookResponse(
            id=entry.book.id,
            title=entry.book.title,
            author=entry.book.author,
            description=entry.book.description,
            cover_path=entry.book.cover_path,
            cover_url=book_cover_url(entry.book.id, entry.book.cover_path),
            file_path=entry.book.file_path,
            file_type=entry.book.file_type,
            total_pages=entry.book.total_pages,
            category_id=entry.book.category_id,
            category=entry.book.category,
            tags=[tag.name for tag in entry.book.tags] if entry.book.tags else [],
            created_at=entry.book.created_at,
            updated_at=entry.book.updated_at
        )
    
    return LibraryEntryResponse(
        id=entry.id,
        user_id=entry.user_id,
        book_id=entry.book_id,
        status=entry.status,
        is_favorite=entry.is_favorite,
        current_page=entry.current_page,
        last_read_at=entry.last_read_at,
        created_at=entry.created_at,
        book=book_response
    )


async def add_to_library(db: AsyncSession, user_id: int, book_id: int) -> LibraryEntryResponse:
    # Check if book exists
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    # Check if already in library
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book))
        .where(
            LibraryEntry.user_id == user_id,
            LibraryEntry.book_id == book_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Book already in library"
        )
    
    # Add to library
    entry = LibraryEntry(
        user_id=user_id,
        book_id=book_id,
        status="want_to_read"
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    
    # Load the book relationship
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book).selectinload(Book.category),
                selectinload(LibraryEntry.book).selectinload(Book.tags))
        .where(LibraryEntry.id == entry.id)
    )
    entry_with_book = result.scalar_one()
    return _convert_library_entry_to_response(entry_with_book)


async def remove_from_library(db: AsyncSession, user_id: int, book_id: int) -> None:
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book))
        .where(
            LibraryEntry.user_id == user_id,
            LibraryEntry.book_id == book_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found in library"
        )
    
    await db.delete(entry)
    await db.commit()


async def get_library(
    db: AsyncSession, 
    user_id: int, 
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> dict:
    query = select(LibraryEntry).options(
        selectinload(LibraryEntry.book).selectinload(Book.category),
        selectinload(LibraryEntry.book).selectinload(Book.tags)
    ).where(LibraryEntry.user_id == user_id)
    
    if status_filter:
        query = query.where(LibraryEntry.status == status_filter)
    
    # Get total count
    count_query = select(func.count(LibraryEntry.id)).where(LibraryEntry.user_id == user_id)
    if status_filter:
        count_query = count_query.where(LibraryEntry.status == status_filter)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    query = query.order_by(LibraryEntry.created_at.desc(), LibraryEntry.id.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    # Convert to response format
    response_items = [_convert_library_entry_to_response(item) for item in items]
    
    return {
        "items": response_items,
        "total": total,
        "skip": skip,
        "limit": limit
    }


async def get_recent_activity(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 20
) -> dict:
    activity_at = func.coalesce(LibraryEntry.last_read_at, LibraryEntry.created_at)
    query = select(LibraryEntry).options(
        selectinload(LibraryEntry.book).selectinload(Book.category),
        selectinload(LibraryEntry.book).selectinload(Book.tags)
    ).where(LibraryEntry.user_id == user_id).order_by(
        activity_at.desc(),
        LibraryEntry.id.desc()
    )

    count_query = select(func.count(LibraryEntry.id)).where(LibraryEntry.user_id == user_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    return {
        "items": [_convert_library_entry_to_response(item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit
    }


async def update_status(
    db: AsyncSession, 
    user_id: int, 
    book_id: int, 
    status_data: LibraryStatusUpdate
) -> LibraryEntryResponse:
    result = await db.execute(
        select(LibraryEntry).where(
            LibraryEntry.user_id == user_id,
            LibraryEntry.book_id == book_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found in library"
        )
    
    entry.status = status_data.status
    if status_data.is_favorite is not None:
        entry.is_favorite = status_data.is_favorite
    
    await db.commit()
    await db.refresh(entry)
    
    # Reload with book relationship
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book).selectinload(Book.category),
                selectinload(LibraryEntry.book).selectinload(Book.tags))
        .where(LibraryEntry.id == entry.id)
    )
    entry_with_book = result.scalar_one()
    return _convert_library_entry_to_response(entry_with_book)


async def update_reading_progress(
    db: AsyncSession, 
    user_id: int, 
    book_id: int, 
    progress_data: ReadingProgressUpdate
) -> LibraryEntryResponse:
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book))
        .where(
            LibraryEntry.user_id == user_id,
            LibraryEntry.book_id == book_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found in library"
        )
    
    total_pages = entry.book.total_pages if entry.book else None
    if total_pages is not None and progress_data.current_page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current page cannot exceed book total pages"
        )

    entry.current_page = progress_data.current_page
    entry.last_read_at = datetime.now(timezone.utc)
    
    if total_pages is not None and progress_data.current_page >= total_pages:
        entry.status = "completed"
    elif entry.status == "want_to_read" or (
        total_pages is not None
        and progress_data.current_page < total_pages
        and entry.status == "completed"
    ):
        entry.status = "reading"
    
    await db.commit()
    await db.refresh(entry)
    
    # Reload with book relationship
    result = await db.execute(
        select(LibraryEntry)
        .options(selectinload(LibraryEntry.book).selectinload(Book.category),
                selectinload(LibraryEntry.book).selectinload(Book.tags))
        .where(LibraryEntry.id == entry.id)
    )
    entry_with_book = result.scalar_one()
    return _convert_library_entry_to_response(entry_with_book)


async def get_favorites(db: AsyncSession, user_id: int) -> List[LibraryEntryResponse]:
    query = select(LibraryEntry).options(
        selectinload(LibraryEntry.book).selectinload(Book.category),
        selectinload(LibraryEntry.book).selectinload(Book.tags)
    ).where(
        LibraryEntry.user_id == user_id,
        LibraryEntry.is_favorite == True
    )
    
    result = await db.execute(query)
    entries = result.scalars().all()
    return [_convert_library_entry_to_response(entry) for entry in entries]
