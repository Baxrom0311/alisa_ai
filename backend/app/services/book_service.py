from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from typing import Optional, List
import logging
from ..models.book import Book, BookTag
from ..models.audio import AudioFile
from ..models.category import Category, Tag
from ..schemas.book import (
    BookCreate,
    BookFilter,
    BookListResponse,
    BookResponse,
    BookUpdate,
    book_cover_url,
)


logger = logging.getLogger(__name__)


def _apply_book_filters(query, filters: Optional[BookFilter]):
    """Apply filters to a book query"""
    if not filters:
        return query
    
    if filters.search:
        search_term = f"%{filters.search}%"
        query = query.where(
            or_(
                Book.title.ilike(search_term),
                Book.author.ilike(search_term)
            )
        )
    if filters.title:
        query = query.where(Book.title.ilike(f"%{filters.title}%"))
    if filters.category_id:
        query = query.where(Book.category_id == filters.category_id)
    category_name = filters.genre or filters.category
    if category_name:
        query = query.where(Book.category.has(Category.name.ilike(f"%{category_name}%")))
    if filters.author:
        query = query.where(Book.author.ilike(f"%{filters.author}%"))
    if filters.tag:
        normalized_tag = filters.tag.strip().lower()
        if normalized_tag:
            query = query.join(BookTag).join(Tag).where(Tag.name == normalized_tag)
    
    return query


def _book_to_response(book: Book) -> BookResponse:
    return BookResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        description=book.description,
        cover_path=book.cover_path,
        cover_url=book_cover_url(book.id, book.cover_path),
        file_path=book.file_path,
        file_type=book.file_type,
        total_pages=book.total_pages,
        category_id=book.category_id,
        category=book.category,
        tags=[tag.name for tag in book.tags] if book.tags else [],
        created_at=book.created_at,
        updated_at=book.updated_at
    )


def _normalize_tag_names(tag_names: List[str]) -> List[str]:
    normalized = []
    seen = set()
    for raw_name in tag_names:
        name = raw_name.strip().lower()
        if not name or name in seen:
            continue
        normalized.append(name)
        seen.add(name)
    return normalized


async def _validate_category_exists(db: AsyncSession, category_id: Optional[int]) -> None:
    if category_id is None:
        return

    result = await db.execute(select(Category.id).where(Category.id == category_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )


async def _get_or_create_tags(db: AsyncSession, tag_names: List[str]) -> List[Tag]:
    tags = []
    for tag_name in _normalize_tag_names(tag_names):
        result = await db.execute(select(Tag).where(Tag.name == tag_name))
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Tag already exists"
                )
        tags.append(tag)
    return tags


async def _sync_book_tags(db: AsyncSession, book: Book, tag_names: List[str]) -> None:
    await db.execute(delete(BookTag).where(BookTag.book_id == book.id))
    for tag in await _get_or_create_tags(db, tag_names):
        db.add(BookTag(book_id=book.id, tag_id=tag.id))


async def create_book(db: AsyncSession, book_data: BookCreate) -> BookResponse:
    await _validate_category_exists(db, book_data.category_id)

    db_book = Book(
        title=book_data.title,
        author=book_data.author,
        description=book_data.description,
        category_id=book_data.category_id,
        total_pages=book_data.total_pages
    )
    db.add(db_book)
    await db.flush()

    if book_data.tags:
        await _sync_book_tags(db, db_book, book_data.tags)

    await db.commit()
    
    # Reload book with tags and category
    result = await db.execute(
        select(Book)
        .options(selectinload(Book.category), selectinload(Book.tags))
        .where(Book.id == db_book.id)
    )
    book_with_relations = result.scalar_one()
    
    return _book_to_response(book_with_relations)


async def _get_book_model(db: AsyncSession, book_id: int) -> Book:
    """Helper function to get raw Book model"""
    result = await db.execute(
        select(Book)
        .options(
            selectinload(Book.category),
            selectinload(Book.tags),
        )
        .where(Book.id == book_id)
        .execution_options(populate_existing=True)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book


async def _get_book_delete_model(db: AsyncSession, book_id: int) -> Book:
    """Load a book with relationships needed for deletion cleanup."""
    result = await db.execute(
        select(Book)
        .options(
            selectinload(Book.category),
            selectinload(Book.tags),
            selectinload(Book.audio_files).selectinload(AudioFile.listening_progress),
            selectinload(Book.library_entries),
        )
        .where(Book.id == book_id)
        .execution_options(populate_existing=True)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book


async def get_book(db: AsyncSession, book_id: int) -> BookResponse:
    book = await _get_book_model(db, book_id)
    return _book_to_response(book)


async def list_books(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    filters: Optional[BookFilter] = None
) -> BookListResponse:
    query = select(Book).options(selectinload(Book.category), selectinload(Book.tags))
    query = _apply_book_filters(query, filters)
    
    # Get total count
    count_query = select(func.count(func.distinct(Book.id)))
    count_query = _apply_book_filters(count_query, filters)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get books with pagination
    query = query.order_by(Book.created_at.desc(), Book.id.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    books = result.scalars().all()
    
    book_responses = [_book_to_response(book) for book in books]
    
    return BookListResponse(
        items=book_responses,
        total=total,
        skip=skip,
        limit=limit
    )


async def update_book(db: AsyncSession, book_id: int, book_data: BookUpdate) -> BookResponse:
    result = await db.execute(
        select(Book)
        .options(selectinload(Book.tags))
        .where(Book.id == book_id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )

    update_data = book_data.model_dump(exclude_unset=True)

    if "category_id" in update_data:
        await _validate_category_exists(db, update_data["category_id"])
        book.category_id = update_data["category_id"]

    for field in ("title", "author", "description", "total_pages"):
        if field in update_data:
            setattr(book, field, update_data[field])

    if "tags" in update_data:
        await _sync_book_tags(db, book, update_data["tags"] or [])

    await db.commit()
    return await get_book(db, book_id)


async def delete_book(db: AsyncSession, book_id: int) -> None:
    # Get the book with all related data
    book = await _get_book_delete_model(db, book_id)
    
    # Get storage backend for file cleanup
    from ..services.storage_service import get_storage_backend
    storage = get_storage_backend()
    
    # Delete book file if exists
    if book.file_path:
        try:
            await storage.delete(book.file_path)
        except Exception:
            logger.warning("Failed to delete book file from storage: %s", book.file_path, exc_info=True)
    
    # Delete cover file if exists
    if book.cover_path:
        try:
            await storage.delete(book.cover_path)
        except Exception:
            logger.warning("Failed to delete cover file from storage: %s", book.cover_path, exc_info=True)
    
    # Delete audio files
    for audio_file in book.audio_files:
        if audio_file.file_path:
            try:
                await storage.delete(audio_file.file_path)
            except Exception:
                logger.warning("Failed to delete audio file from storage: %s", audio_file.file_path, exc_info=True)
    
    # Delete the book (cascading will handle related records)
    await db.delete(book)
    await db.commit()
