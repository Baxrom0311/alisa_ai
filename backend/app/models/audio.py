from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from ..database import Base


class AudioFile(Base):
    __tablename__ = "audio_files"
    __table_args__ = (UniqueConstraint("book_id", name="uq_audio_files_book_id"),)
    
    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    file_path = Column(String, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    format = Column(String, nullable=False)
    bitrate = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    book = relationship("Book", back_populates="audio_files")
    listening_progress = relationship("ListeningProgress", back_populates="audio", cascade="all, delete-orphan")
