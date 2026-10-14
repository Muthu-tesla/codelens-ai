from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.config import settings
from app.db.database import Base


class VectorColumn(TypeDecorator):
    """
    Vector column that adapts to PostgreSQL (pgvector Vector)
    or SQLite (JSON list of floats) for cross-environment testing.
    """
    impl = Vector
    cache_ok = True

    def __init__(self, dim: int = settings.EMBEDDING_DIMENSION):
        super().__init__(dim)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        else:
            return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            return value.tolist()
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return list(value)


class CodeChunk(Base):
    """
    Represents a semantic chunk of code extracted from a repository
    with associated vector embedding for similarity search.
    """

    __tablename__ = "code_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    qualified_name: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        VectorColumn(settings.EMBEDDING_DIMENSION),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "file_id",
            "chunk_type",
            "qualified_name",
            name="uq_code_chunks_identity",
        ),
    )

    repository = relationship("Repository", back_populates="code_chunks")
    file = relationship("CodeFile", back_populates="chunks")
    symbol = relationship("CodeSymbol", back_populates="chunks")
