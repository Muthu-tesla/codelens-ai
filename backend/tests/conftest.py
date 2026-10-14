import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.database import Base
from app.db.session import get_db
import app.models  # Register all models with Base
from app.main import app

# Use an in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def temp_sample_repo() -> Generator[Path, None, None]:
    """Create a temporary directory simulating a multi-file repository with ignored directories."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_test_repo_")
    repo_root = Path(temp_dir)

    try:
        # 1. Supported root and nested python files
        src_dir = repo_root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        py_file1 = src_dir / "service.py"
        py_file1.write_text(
            'import math\nfrom typing import Optional\n\n'
            'class BaseCalculator:\n'
            '    """Base calculator docstring."""\n'
            '    def reset(self) -> None:\n'
            '        pass\n\n'
            'class MathService(BaseCalculator):\n'
            '    """Service for math operations."""\n'
            '    @staticmethod\n'
            '    def add(a: int, b: int) -> int:\n'
            '        return a + b\n\n'
            '    async def compute_async(self, factor: int) -> int:\n'
            '        """Compute asynchronously."""\n'
            '        return factor * 2\n\n'
            'def standalone_func(x: str) -> str:\n'
            '    """A top-level helper function."""\n'
            '    return x.strip()\n',
            encoding="utf-8",
        )

        # 2. Supported non-python files (.ts, .java)
        ts_file = src_dir / "index.ts"
        ts_file.write_text("export const hello = (): string => 'hello';", encoding="utf-8")

        java_file = src_dir / "Main.java"
        java_file.write_text("public class Main { public static void main(String[] args) {} }", encoding="utf-8")

        # 3. Ignored directories and files
        git_dir = repo_root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("dummy git config", encoding="utf-8")

        nm_dir = repo_root / "node_modules" / "some_pkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_text("console.log('ignored');", encoding="utf-8")

        venv_dir = repo_root / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "site.py").write_text("x = 1", encoding="utf-8")

        pycache_dir = src_dir / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "service.cpython-312.pyc").write_text("binary", encoding="utf-8")

        # 4. Unsupported extension
        (repo_root / "README.md").write_text("# Test Repo", encoding="utf-8")

        yield repo_root
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class MockArray:
    def __init__(self, data: list[list[float]]):
        self._data = data

    def tolist(self) -> list[list[float]]:
        return self._data


class MockSentenceTransformer:
    def __init__(self, dimension: int = settings.EMBEDDING_DIMENSION):
        self.dimension = dimension

    def encode(
        self,
        texts: str | list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> MockArray:
        import hashlib
        import math
        import random
        import re

        if isinstance(texts, str):
            input_texts = [texts]
        else:
            input_texts = list(texts)

        vectors: list[list[float]] = []
        for t in input_texts:
            tokens = re.findall(r"[a-zA-Z0-9]+", t.lower())
            if not tokens:
                tokens = [t.lower()]

            raw = [0.0] * self.dimension
            for tok in tokens:
                t_seed = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:8], "big")
                rng = random.Random(t_seed)
                for i in range(self.dimension):
                    raw[i] += rng.gauss(0, 1)

                # Light stemming for common morphological variants (e.g. created -> create)
                for suffix in ("ed", "ing", "es", "s"):
                    if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                        stem = tok[: -len(suffix)]
                        s_seed = int.from_bytes(hashlib.sha256(stem.encode("utf-8")).digest()[:8], "big")
                        s_rng = random.Random(s_seed)
                        for i in range(self.dimension):
                            raw[i] += s_rng.gauss(0, 1) * 0.8
                        break

            if normalize_embeddings:
                norm = math.sqrt(sum(x * x for x in raw)) or 1.0
                vec = [round(x / norm, 6) for x in raw]
            else:
                vec = raw
            vectors.append(vec)
        return MockArray(vectors)


@pytest.fixture(autouse=True)
def mock_embedding_model() -> Generator[MockSentenceTransformer, None, None]:
    """Ensure tests run with a deterministic 384-dimensional embedding model fixture."""
    from app.services.embedding_service import embedding_service

    original_model = embedding_service._model
    mock = MockSentenceTransformer()
    embedding_service.set_model(mock)
    yield mock
    embedding_service.set_model(original_model)
