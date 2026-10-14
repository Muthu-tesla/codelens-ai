"""
CLI runner for CodeLens retrieval evaluation.
Usage:
    python -m app.evaluation.run
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # Register all models with Base
from app.db.database import Base
from app.db.session import SessionLocal, engine, init_db
from app.evaluation.runner import (
    DEFAULT_FIXTURE_PATH,
    EvaluationRunner,
    format_evaluation_report,
    load_dataset,
)
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate
from app.services.repository_service import repository_service


def get_evaluation_session():
    """
    Acquire a database session for evaluation.
    Prefers the configured PostgreSQL database; if unavailable, falls back
    to an in-memory SQLite database so evaluation can run self-contained.
    """
    try:
        init_db()
        with engine.connect() as conn:
            pass
        return SessionLocal(), False
    except Exception:
        # Fallback to in-memory SQLite database
        eval_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=eval_engine)
        EvalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eval_engine)
        return EvalSessionLocal(), True


def main() -> int:
    """Main execution workflow for retrieval evaluation."""
    fixture_path = DEFAULT_FIXTURE_PATH.resolve()
    if not fixture_path.exists():
        print(f"Error: Fixture repository not found at {fixture_path}", file=sys.stderr)
        return 1

    db, is_fallback = get_evaluation_session()
    try:
        # 1. Register fixture repository in database
        repo_name = "eval_fixture_repo"
        repo = db.query(Repository).filter(Repository.name == repo_name).first()
        if not repo:
            repo = repository_service.create_repository(
                db,
                RepositoryCreate(name=repo_name, path=str(fixture_path)),
            )

        # 2. Analyze fixture repository
        analysis_summary = repository_service.analyze_repository(db, repo.id)
        if analysis_summary.errors:
            print(f"Warning: Analysis generated errors: {analysis_summary.errors}", file=sys.stderr)

        # 3. Load evaluation queries dataset
        dataset = load_dataset()

        # 4. Execute evaluation runner
        runner = EvaluationRunner(k_values=[1, 3, 5])
        summary = runner.evaluate_queries(db, repo.id, dataset)

        # 5. Print formatted report
        report = format_evaluation_report(summary)
        print(report)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
