from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Literal

# Allowed audio formats
AudioFormat = Literal["mp3", "ogg", "aac", "wav", "m4a"]


class AudioUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    book_id: int
    file_path: str = Field(max_length=1024)
    duration_seconds: float = Field(gt=0, description="Duration must be positive")
    format: AudioFormat
    bitrate: Optional[int] = Field(None, gt=0, description="Bitrate must be positive if provided")
    file_size: int = Field(gt=0, description="File size must be positive")
    created_at: datetime


class AudioProgressUpdate(BaseModel):
    position_seconds: float = Field(ge=0, description="Position must be non-negative")


class AudioProgressResponse(BaseModel):
    position_seconds: float = Field(ge=0, description="Position must be non-negative")
    updated_at: Optional[datetime] = None
