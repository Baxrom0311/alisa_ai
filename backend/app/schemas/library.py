from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import datetime
from typing import Optional, List, Literal
from .book import BookResponse

ReadingStatus = Literal["want_to_read", "unread", "reading", "completed"]
UNSTARTED_READING_STATUSES = {"want_to_read", "unread"}


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
    status: Optional[ReadingStatus] = None
    is_favorite: Optional[bool] = None

    @model_validator(mode="after")
    def require_status_or_favorite(self) -> "LibraryStatusUpdate":
        if self.status is None and self.is_favorite is None:
            raise ValueError("At least one of status or is_favorite must be provided")
        return self


class ReadingProgressUpdate(BaseModel):
    current_page: int = Field(ge=0, description="Current page must be non-negative")


class LibraryListResponse(BaseModel):
    items: List[LibraryEntryResponse]
    total: int
    skip: int
    limit: int
