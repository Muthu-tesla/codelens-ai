"""
End-to-end RAG verification script for Phase 3B-2.1.
Executes the full pipeline against real fixture repositories:
registration -> AST analysis -> graph -> chunking -> embeddings ->
semantic retrieval -> 1-hop graph enrichment -> evidence builder ->
prompt construction -> real LLM provider -> citation validation.
"""
import functools
import os
import sys
import time
from pathlib import Path

print = functools.partial(print, flush=True)

# Add backend directory to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.database import Base
from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.models.repository import Repository
from app.schemas.rag import EvidenceItem, QuestionRequest
from app.services.llm.base import LLMConfigurationError, LLMGenerationError
from app.services.llm.provider import OpenAILLMProvider, llm_service
from app.services.rag.ask_service import ask_service
from app.services.rag.citation_validator import citation_validator
from app.services.rag.evidence_builder import evidence_builder
from app.services.rag.prompt_builder import prompt_builder
from app.services.repository_service import repository_service


def setup_in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def main():
    print("=" * 80)
    print("CodeLens AI -- Phase 3B-2.1 Real End-to-End RAG Verification")
    print("=" * 80)

    db = setup_in_memory_db()

    fixtures_dir = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures"
    fixture_a_path = fixtures_dir / "rag_fixture_a"
    fixture_b_path = fixtures_dir / "rag_fixture_b"

    from app.schemas.repository import RepositoryCreate

    print(f"\n[1] Registering and analyzing Repository A: {fixture_a_path}")
    repo_a = repository_service.create_repository(
        db,
        repo_in=RepositoryCreate(name="fixture_app_a", path=str(fixture_a_path)),
    )
    analysis_a = repository_service.analyze_repository(db, repo_a.id)
    print(f"    Repository A analyzed: {analysis_a.files_analyzed} files, "
          f"{analysis_a.classes} classes, {analysis_a.functions} functions, {analysis_a.methods} methods, "
          f"{analysis_a.relationships} relationships, {analysis_a.chunks_created} chunks.")

    print(f"\n[2] Registering and analyzing Repository B: {fixture_b_path}")
    repo_b = repository_service.create_repository(
        db,
        repo_in=RepositoryCreate(name="fixture_app_b", path=str(fixture_b_path)),
    )
    analysis_b = repository_service.analyze_repository(db, repo_b.id)
    print(f"    Repository B analyzed: {analysis_b.files_analyzed} files, "
          f"{analysis_b.classes} classes, {analysis_b.functions} functions, {analysis_b.methods} methods, "
          f"{analysis_b.relationships} relationships, {analysis_b.chunks_created} chunks.")

    # 3. Test the 5 required questions against Repository A
    questions = [
        "How does payment processing work?",
        "Where is inventory checked before an order is created?",
        "How are user login credentials verified?",
        "Which function creates the order and persists it?",
        "What authentication mechanism is used by this repository?",
    ]

    print("\n" + "=" * 80)
    print("[3] Evaluating the 5 Questions on Repository A")
    print("=" * 80)

    for i, q in enumerate(questions, start=1):
        print(f"\n--- Question {i}: \"{q}\" ---")

        t0 = time.perf_counter()
        # Semantic search step
        search_res = repository_service.semantic_search(
            db=db,
            repository_id=repo_a.id,
            query=q,
            limit=settings.RAG_TOP_K_SEMANTIC,
        )
        t_retrieval = time.perf_counter() - t0

        t1 = time.perf_counter()
        # Full evidence building step (semantic + 1-hop graph)
        evidence = evidence_builder.build_evidence(
            db=db,
            repository_id=repo_a.id,
            question=q,
        )
        t_evidence = time.perf_counter() - t1

        print(f"    [Timing] Semantic Retrieval: {t_retrieval * 1000:.2f} ms | Evidence Builder: {t_evidence * 1000:.2f} ms")
        print(f"    [Evidence Count] {len(evidence)} items retrieved")

        for item in evidence:
            sim_str = f"{item.similarity:.4f}" if item.similarity is not None else "1-hop graph"
            print(f"      - {item.id}: {item.file} :: {item.qualified_name} (Lines {item.line_start}-{item.line_end}) [{sim_str}]")

        prompt = prompt_builder.build_prompt(q, evidence)
        print(f"    [Prompt Length] {len(prompt)} chars")

        # Attempt Real LLM Call
        t2 = time.perf_counter()
        llm_answer = None
        llm_error = None
        try:
            llm_answer = llm_service.generate_answer(prompt)
            t_llm = time.perf_counter() - t2
            print(f"    [Timing] Real LLM Generation: {t_llm * 1000:.2f} ms")
            print(f"    [Real LLM Answer]:\n{llm_answer}")

            # Validate citations of real LLM output
            val = citation_validator.validate(llm_answer, evidence)
            print(f"    [Citation Valid]: {val.is_valid}")
            print(f"    [Referenced IDs]: {val.referenced_ids}")
            print(f"    [Invalid IDs]: {val.invalid_ids}")
        except (LLMConfigurationError, LLMGenerationError) as exc:
            t_llm = time.perf_counter() - t2
            llm_error = str(exc)
            print(f"    [Real LLM Notice]: {llm_error}")

    # 4. Citation Integrity Verification
    print("\n" + "=" * 80)
    print("[4] Citation Integrity Verification")
    print("=" * 80)

    q1_evidence = evidence_builder.build_evidence(db=db, repository_id=repo_a.id, question="How does payment processing work?")

    # Test A: Valid Answer
    valid_ans = "PaymentService.process_payment calls StripeGateway.charge_card [E1][E2]."
    res_valid = citation_validator.validate(valid_ans, q1_evidence)
    print(f"A. Valid Citation Test: valid={res_valid.is_valid}, cited={[e.id for e in res_valid.cited_evidence]}")
    assert res_valid.is_valid is True
    assert [e.id for e in res_valid.cited_evidence] == ["E1", "E2"]

    # Test B: Invalid Citation ([E99])
    invalid_ans = "Payment processing uses Stripe [E99]."
    res_invalid = citation_validator.validate(invalid_ans, q1_evidence)
    print(f"B. Invalid Citation Test ([E99]): valid={res_invalid.is_valid}, fallback_answer=\"{res_invalid.answer}\"")
    assert res_invalid.is_valid is False
    assert res_invalid.answer == citation_validator.FALLBACK_MESSAGE

    # Test C: No Citations (substantive claim without evidence)
    no_cite_ans = "Payment processing charges a card via Stripe without any markers."
    res_no_cite = citation_validator.validate(no_cite_ans, q1_evidence)
    print(f"C. No Citations Test: valid={res_no_cite.is_valid}, fallback_answer=\"{res_no_cite.answer}\"")
    assert res_no_cite.is_valid is False
    assert res_no_cite.answer == citation_validator.FALLBACK_MESSAGE

    # Test D: Honest Uncertainty Fallback without citations
    honest_ans = "I couldn't determine this confidently from the indexed codebase."
    res_honest = citation_validator.validate(honest_ans, q1_evidence)
    print(f"D. Honest Uncertainty Fallback Test: valid={res_honest.is_valid}, answer=\"{res_honest.answer}\"")
    assert res_honest.is_valid is True
    assert res_honest.answer == citation_validator.FALLBACK_MESSAGE

    # 5. Repository Isolation Verification
    print("\n" + "=" * 80)
    print("[5] Repository Isolation Verification")
    print("=" * 80)

    # Search against Repo A: ensure no PayPal / Repo B evidence leaks
    evidence_a = evidence_builder.build_evidence(
        db=db,
        repository_id=repo_a.id,
        question="How does payment processing work?",
    )
    repo_a_files = [e.file for e in evidence_a]
    repo_a_contents = " ".join(e.content for e in evidence_a)
    has_paypal = "PayPal" in repo_a_contents or "paypal" in repo_a_contents
    has_stripe = "Stripe" in repo_a_contents or "stripe" in repo_a_contents
    print(f"Repo A Evidence Files: {repo_a_files}")
    print(f"Repo A Contains Stripe: {has_stripe} | Contains PayPal: {has_paypal}")
    assert has_stripe is True
    assert has_paypal is False

    # Search against Repo B: ensure no Stripe / Repo A evidence leaks
    evidence_b = evidence_builder.build_evidence(
        db=db,
        repository_id=repo_b.id,
        question="How does payment processing work?",
    )
    repo_b_files = [e.file for e in evidence_b]
    repo_b_contents = " ".join(e.content for e in evidence_b)
    has_paypal_b = "PayPal" in repo_b_contents or "paypal" in repo_b_contents
    has_stripe_b = "Stripe" in repo_b_contents or "stripe" in repo_b_contents
    print(f"Repo B Evidence Files: {repo_b_files}")
    print(f"Repo B Contains PayPal: {has_paypal_b} | Contains Stripe: {has_stripe_b}")
    assert has_paypal_b is True
    assert has_stripe_b is False

    print("\n>>> REPOSITORY ISOLATION: PASS")
    print("\n" + "=" * 80)
    print("Verification Completed Successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
