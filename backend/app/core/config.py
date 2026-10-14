from typing import Any
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CodeLens AI — AI Codebase Intelligence Platform"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/codelens"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Allowed parent directory roots for repository registration in production/multi-tenant setup.
    # When None or empty, local filesystem registration is allowed.
    ALLOWED_REPO_ROOTS: list[str] | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        if isinstance(v, (list, set, tuple)):
            return list(v)
        return []

    @field_validator("ALLOWED_REPO_ROOTS", mode="before")
    @classmethod
    def assemble_allowed_repo_roots(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if isinstance(v, str):
            parts = [i.strip() for i in v.split(",") if i.strip()]
            return parts or None
        if isinstance(v, (list, set, tuple)):
            return list(v)
        return None

    # Embedding and Vector Search Settings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    SEARCH_DEFAULT_LIMIT: int = 5
    SEARCH_MAX_LIMIT: int = 20

    # LLM and Evidence Grounding Settings
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    LLM_MODEL: str = "gpt-4o-mini"
    RAG_TOP_K_SEMANTIC: int = 8
    RAG_MAX_EVIDENCE_ITEMS: int = 12
    MAX_QUESTION_LENGTH: int = 1000

    # Architecture Trace Settings
    ARCHITECTURE_TRACE_MAX_DEPTH: int = 8
    ARCHITECTURE_TRACE_MAX_NODES: int = 20

    # Discovery settings
    MAX_FILE_SIZE_BYTES: int = 1_000_000  # Ignore files > 1MB
    MAX_FILES_PER_REPO: int = 5_000  # Cap maximum discovered files per repository
    SUPPORTED_EXTENSIONS: set[str] = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".java",
        ".cpp",
        ".c",
        ".go",
        ".rs",
    }
    IGNORED_DIRS: set[str] = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        "target",
        "coverage",
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
