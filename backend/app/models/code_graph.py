from datetime import datetime
from enum import Enum
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SymbolType(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class RelationshipType(str, Enum):
    IMPORTS = "imports"
    CONTAINS = "contains"
    INHERITS = "inherits"
    CALLS = "calls"


class CodeFile(Base):
    """Represents a discovered source file in a repository."""

    __tablename__ = "code_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "relative_path", name="uq_code_files_repo_relpath"),
    )

    repository = relationship("Repository", back_populates="code_files")
    symbols = relationship("CodeSymbol", back_populates="file", cascade="all, delete-orphan")
    chunks = relationship("CodeChunk", back_populates="file", cascade="all, delete-orphan")


class CodeSymbol(Base):
    """Represents a code symbol (module, class, function, method) in a source file."""

    __tablename__ = "code_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    symbol_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    signature: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("file_id", "qualified_name", name="uq_code_symbols_file_qname"),
    )

    file = relationship("CodeFile", back_populates="symbols")
    outgoing_relationships = relationship(
        "CodeRelationship",
        foreign_keys="CodeRelationship.source_symbol_id",
        back_populates="source_symbol",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "CodeRelationship",
        foreign_keys="CodeRelationship.target_symbol_id",
        back_populates="target_symbol",
        cascade="all, delete-orphan",
    )
    chunks = relationship("CodeChunk", back_populates="symbol", cascade="all, delete-orphan")


class CodeRelationship(Base):
    """Represents a direct relationship between two code symbols."""

    __tablename__ = "code_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_symbol_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_symbol_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_symbol_id",
            "target_symbol_id",
            "relationship_type",
            name="uq_code_relationships_edge",
        ),
    )

    source_symbol = relationship(
        "CodeSymbol",
        foreign_keys=[source_symbol_id],
        back_populates="outgoing_relationships",
    )
    target_symbol = relationship(
        "CodeSymbol",
        foreign_keys=[target_symbol_id],
        back_populates="incoming_relationships",
    )
