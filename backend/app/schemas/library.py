from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List, Literal
from .book import BookResponse

ReadingStatus = Literal["want_to_read", "reading", "completed"]


class LibraryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    book_id: int
    status: ReadingStatus
    is_favorite: bool
    current_page: int = Field(ge=0, description="Current page must be non-negative")
    last_read_at: Optional[datetime] = None
    created_at: datetime
    book: Optional[BookResponse] = None


class LibraryStatusUpdate(BaseModel):
    status: ReadingStatus
    is_favorite: Optional[bool] = None


class ReadingProgressUpdate(BaseModel):
    current_page: int = Field(ge=0, description="Current page must be non-negative")


class LibraryListResponse(BaseModel):
    items: List[LibraryEntryResponse]
    total: int
    skip: int
    limit: int
