import logging
import time
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.architecture import (
    ArchitectureExplainRequest,
    ArchitectureExplainResponse,
    ArchitectureExplainTrace,
    ArchitectureTraceRequest,
)
from app.services.architecture.evidence_collector import architecture_evidence_collector
from app.services.architecture.prompt_builder import architecture_prompt_builder
from app.services.architecture.symbol_resolver import start_symbol_resolver
from app.services.architecture.trace_service import trace_service
from app.services.llm.base import LLMConfigurationError, LLMGenerationError
from app.services.llm.provider import llm_service
from app.services.rag.citation_validator import citation_validator
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)


class ArchitectureExplainService:
    """
    Orchestrates Architecture-Aware RAG.
    Combines semantic symbol discovery, deterministic static call trace,
    source code evidence collection, architecture grounded prompt construction,
    LLM invocation, and citation validation.
    """

    FALLBACK_NO_SYMBOL = "I couldn't determine this confidently from the indexed codebase."

    def explain(
        self,
        db: Session,
        repository_id: int,
        request: ArchitectureExplainRequest,
    ) -> ArchitectureExplainResponse:
        """Process architecture explanation question against repository."""
        t_start = time.perf_counter()

        # 1. Validate repository existence
        repository_service.get_repository(db, repository_id)

        # 2. Validate question
        clean_question = request.question.strip()
        if not clean_question:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Question cannot be empty.",
            )
        if len(clean_question) > settings.MAX_QUESTION_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question exceeds maximum allowed length of {settings.MAX_QUESTION_LENGTH} characters.",
            )

        # 3. Discover start symbol candidate via semantic search
        t_sem_start = time.perf_counter()
        selected_symbol, search_res = start_symbol_resolver.resolve_start_symbol(
            db=db,
            repository_id=repository_id,
            question=clean_question,
        )
        t_sem_end = time.perf_counter()
        semantic_ms = (t_sem_end - t_sem_start) * 1000

        # Safety: If no suitable CodeSymbol identified in the repository, return safe fallback without calling LLM
        if not selected_symbol:
            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                "Architecture explain (no symbol): semantic=%.2fms, total=%.2fms",
                semantic_ms,
                total_ms,
            )
            return ArchitectureExplainResponse(
                question=clean_question,
                answer=self.FALLBACK_NO_SYMBOL,
                trace=None,
                evidence=[],
            )

        # 4. Deterministic Architecture Trace starting from discovered symbol
        t_trace_start = time.perf_counter()
        trace_res = trace_service.trace_architecture(
            db=db,
            repository_id=repository_id,
            request=ArchitectureTraceRequest(start_symbol=selected_symbol.qualified_name),
            max_depth=settings.ARCHITECTURE_TRACE_MAX_DEPTH,
            max_nodes=settings.ARCHITECTURE_TRACE_MAX_NODES,
        )
        t_trace_end = time.perf_counter()
        trace_ms = (t_trace_end - t_trace_start) * 1000

        explain_trace = ArchitectureExplainTrace(
            start_symbol=trace_res.start_symbol,
            nodes=trace_res.nodes,
            edges=trace_res.edges,
        )

        # 5. Retrieve source code evidence for traced nodes and relevant context
        t_ev_start = time.perf_counter()
        evidence = architecture_evidence_collector.collect_evidence(
            db=db,
            repository_id=repository_id,
            trace_nodes=trace_res.nodes,
            search_res=search_res,
            max_items=12,
        )
        t_ev_end = time.perf_counter()
        evidence_ms = (t_ev_end - t_ev_start) * 1000

        # 6. Construct architecture grounded prompt
        prompt = architecture_prompt_builder.build_prompt(
            question=clean_question,
            trace=explain_trace,
            evidence=evidence,
        )

        # 7. Call LLM provider
        t_llm_start = time.perf_counter()
        try:
            raw_answer = llm_service.generate_answer(prompt)
        except LLMConfigurationError as exc:
            logger.error("LLM configuration error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"LLM service is not configured: {exc}",
            ) from exc
        except LLMGenerationError as exc:
            logger.error("LLM generation error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM provider error: {exc}",
            ) from exc
        t_llm_end = time.perf_counter()
        llm_ms = (t_llm_end - t_llm_start) * 1000

        # 8. Validate citations strictly against retrieved evidence
        val_result = citation_validator.validate(
            answer=raw_answer,
            evidence=evidence,
        )

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            "Architecture explain timing: semantic=%.2fms, trace=%.2fms, evidence=%.2fms, llm=%.2fms, total=%.2fms",
            semantic_ms,
            trace_ms,
            evidence_ms,
            llm_ms,
            total_ms,
        )

        return ArchitectureExplainResponse(
            question=clean_question,
            answer=val_result.answer,
            trace=explain_trace,
            evidence=val_result.cited_evidence,
        )


architecture_explain_service = ArchitectureExplainService()
