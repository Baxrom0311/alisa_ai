from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from ..database import Base


class Book(Base):
    __tablename__ = "books"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    author = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    cover_path = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    file_type = Column(String, nullable=True)  # "pdf" or "epub"
    total_pages = Column(Integer, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), index=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    category = relationship("Category", back_populates="books")
    tags = relationship("Tag", secondary="book_tags", back_populates="books")
    audio_files = relationship("AudioFile", back_populates="book", cascade="all, delete-orphan")
    library_entries = relationship("LibraryEntry", back_populates="book", cascade="all, delete-orphan")


class BookTag(Base):
    __tablename__ = "book_tags"
    
    book_id = Column(Integer, ForeignKey("books.id"), primary_key=True, index=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True, index=True)
