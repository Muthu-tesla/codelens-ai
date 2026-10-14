import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.rag import AskResponse, QuestionRequest
from app.services.llm.base import LLMConfigurationError, LLMGenerationError
from app.services.llm.provider import llm_service
from app.services.rag.citation_validator import citation_validator
from app.services.rag.evidence_builder import evidence_builder
from app.services.rag.prompt_builder import prompt_builder
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)


class AskService:
    """
    Orchestrates evidence-grounded codebase question answering.
    Connects repository validation, evidence building, grounded prompt construction,
    LLM invocation, and citation validation.
    """

    FALLBACK_NO_EVIDENCE = "I couldn't determine this confidently from the indexed codebase."

    def ask(
        self,
        db: Session,
        repository_id: int,
        request: QuestionRequest,
    ) -> AskResponse:
        """Process question against repository code evidence."""
        # 1. Validate repository exists
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

        # 3. Retrieve code evidence
        evidence = evidence_builder.build_evidence(
            db=db,
            repository_id=repository_id,
            question=clean_question,
        )

        if not evidence:
            return AskResponse(
                answer=self.FALLBACK_NO_EVIDENCE,
                evidence=[],
            )

        # 4. Construct grounded prompt
        prompt = prompt_builder.build_prompt(
            question=clean_question,
            evidence=evidence,
        )

        # 5. Call LLM provider exactly once
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

        # 6. Validate citations against retrieved evidence
        val_result = citation_validator.validate(
            answer=raw_answer,
            evidence=evidence,
        )

        return AskResponse(
            answer=val_result.answer,
            evidence=val_result.cited_evidence,
        )


ask_service = AskService()
