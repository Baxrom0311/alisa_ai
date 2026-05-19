from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, func, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    status = Column(String, default="want_to_read", nullable=False)  # want_to_read, reading, completed
    is_favorite = Column(Boolean, default=False, nullable=False)
    current_page = Column(Integer, default=0, nullable=False)
    last_read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    __table_args__ = (UniqueConstraint('user_id', 'book_id', name='_user_book_uc'),)
    
    # Relationships
    user = relationship("User", back_populates="library_entries")
    book = relationship("Book", back_populates="library_entries")


class ListeningProgress(Base):
    __tablename__ = "listening_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    audio_id = Column(Integer, ForeignKey("audio_files.id"), index=True, nullable=False)
    position_seconds = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (UniqueConstraint('user_id', 'audio_id', name='_user_audio_uc'),)
    
    # Relationships
    user = relationship("User", back_populates="listening_progress")
    audio = relationship("AudioFile", back_populates="listening_progress")
