"""
Base Model

Base class for all SQLAlchemy models.
"""

from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base

# Create base class
Base = declarative_base()


class BaseModel(Base):
    """
    Base model class with common fields and methods.
    """
    __abstract__ = True
    
    # Common fields
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    def __repr__(self) -> str:
        """String representation of the model."""
        class_name = self.__class__.__name__
        return f"{class_name}(id={self.id})"
    
    def to_dict(self) -> dict:
        """
        Convert model to dictionary.
        
        Returns:
            Dictionary representation of the model
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    @classmethod
    def from_dict(cls, data: dict):
        """
        Create model instance from dictionary.
        
        Args:
            data: Dictionary of field values
            
        Returns:
            Model instance
        """
        return cls(**data)
