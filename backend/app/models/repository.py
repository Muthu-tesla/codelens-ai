from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol


class Repository(Base):
    """SQLAlchemy model representing a registered code repository."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    code_files = relationship("CodeFile", back_populates="repository", cascade="all, delete-orphan")
    relationships = relationship("CodeRelationship", cascade="all, delete-orphan")
    code_chunks = relationship("CodeChunk", back_populates="repository", cascade="all, delete-orphan")
