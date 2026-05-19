from sqlalchemy import Column, Integer, String, DateTime, Index, func
from sqlalchemy.orm import relationship
from ..database import Base


class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("uq_categories_name_lower", func.lower(name), unique=True),
    )
    
    # Relationships
    books = relationship("Book", back_populates="category")


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    __table_args__ = (
        Index("uq_tags_name_lower", func.lower(name), unique=True),
    )
    
    # Relationships
    books = relationship("Book", secondary="book_tags", back_populates="tags")
