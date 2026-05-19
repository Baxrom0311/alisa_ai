from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Annotated, Optional, List
from .category import CategoryResponse


TagName = Annotated[str, Field(min_length=1, max_length=40)]


def book_cover_url(book_id: int, cover_path: Optional[str]) -> Optional[str]:
    if not cover_path:
        return None
    return f"/api/books/{book_id}/cover"


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    author: str
    description: Optional[str] = None
    cover_path: Optional[str] = None
    cover_url: Optional[str] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    total_pages: Optional[int] = None
    category_id: Optional[int] = None
    category: Optional[CategoryResponse] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    category_id: Optional[int] = None
    total_pages: Optional[int] = Field(None, ge=0)
    tags: List[TagName] = Field(default_factory=list)


class BookUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    author: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    category_id: Optional[int] = None
    total_pages: Optional[int] = Field(None, ge=0)
    tags: Optional[List[TagName]] = None


class BookFilter(BaseModel):
    search: Optional[str] = Field(None, max_length=300)
    title: Optional[str] = Field(None, max_length=300)
    category_id: Optional[int] = None
    category: Optional[str] = Field(None, max_length=80)
    genre: Optional[str] = Field(None, max_length=80)
    author: Optional[str] = Field(None, max_length=200)
    tag: Optional[str] = Field(None, max_length=40)


class BookListResponse(BaseModel):
    items: List[BookResponse]
    total: int
    skip: int
    limit: int
