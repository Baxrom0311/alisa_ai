from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from typing import List
from ..database import get_db
from ..schemas.category import CategoryCreate, CategoryResponse, TagCreate, TagResponse
from ..schemas.book import BookResponse
from ..models.category import Category, Tag
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/categories", tags=["categories"])
tag_router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=List[CategoryResponse])
async def get_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(func.lower(Category.name), Category.id))
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create categories"
        )
    
    # Check if category already exists
    result = await db.execute(
        select(Category).where(func.lower(Category.name) == category_data.name.lower())
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category already exists"
        )
    
    db_category = Category(
        name=category_data.name,
        description=category_data.description
    )
    db.add(db_category)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category already exists"
        )
    await db.refresh(db_category)
    return db_category


@router.get("/{category_id}/books", response_model=List[BookResponse])
async def get_books_by_category(
    category_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    from ..services.book_service import list_books
    from ..schemas.book import BookFilter

    category = await db.execute(select(Category.id).where(Category.id == category_id))
    if category.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    filter_params = BookFilter(category_id=category_id)
    books_response = await list_books(db, skip=skip, limit=limit, filters=filter_params)
    return books_response.items


@tag_router.get("", response_model=List[TagResponse])
async def get_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).order_by(Tag.name, Tag.id))
    return result.scalars().all()


@tag_router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create tags"
        )

    result = await db.execute(select(Tag).where(func.lower(Tag.name) == tag_data.name.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag already exists"
        )

    db_tag = Tag(name=tag_data.name)
    db.add(db_tag)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag already exists"
        )
    await db.refresh(db_tag)
    return db_tag
