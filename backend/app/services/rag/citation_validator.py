import re
from app.schemas.rag import EvidenceItem


class CitationValidationResult:
    """Outcome of citation validation."""

    def __init__(
        self,
        is_valid: bool,
        answer: str,
        cited_evidence: list[EvidenceItem],
        referenced_ids: list[str],
        invalid_ids: list[str],
    ) -> None:
        self.is_valid = is_valid
        self.answer = answer
        self.cited_evidence = cited_evidence
        self.referenced_ids = referenced_ids
        self.invalid_ids = invalid_ids


class CitationValidator:
    """
    Validates evidence markers ([E1], [E2]) in LLM-generated answers.
    Ensures answers are grounded strictly in the retrieved evidence set.
    """

    FALLBACK_MESSAGE = "I couldn't determine this confidently from the indexed codebase."
    CITATION_PATTERN = re.compile(r"\[(E\d+)\]")

    def validate(
        self,
        answer: str,
        evidence: list[EvidenceItem],
    ) -> CitationValidationResult:
        """
        Validate that all citations in the answer exist in the provided evidence.
        Rejects hallucinated citation IDs and ungrounded substantive claims.
        """
        cleaned_answer = answer.strip()
        valid_ids_map = {item.id: item for item in evidence}

        # Extract all referenced citation markers (e.g. ['E1', 'E2'])
        raw_matches = self.CITATION_PATTERN.findall(cleaned_answer)
        referenced_ids = list(dict.fromkeys(raw_matches))  # deduplicated preserving order

        invalid_ids = [eid for eid in referenced_ids if eid not in valid_ids_map]

        # 1. Hallucinated or invalid evidence IDs detected
        if invalid_ids:
            return CitationValidationResult(
                is_valid=False,
                answer=self.FALLBACK_MESSAGE,
                cited_evidence=[],
                referenced_ids=referenced_ids,
                invalid_ids=invalid_ids,
            )

        # 2. No citations found in the answer
        if not referenced_ids:
            # Check if model appropriately acknowledged insufficient evidence
            is_honest_fallback = (
                "couldn't determine" in cleaned_answer.lower()
                or "could not determine" in cleaned_answer.lower()
                or "insufficient evidence" in cleaned_answer.lower()
            )
            if is_honest_fallback:
                return CitationValidationResult(
                    is_valid=True,
                    answer=self.FALLBACK_MESSAGE,
                    cited_evidence=[],
                    referenced_ids=[],
                    invalid_ids=[],
                )
            else:
                # Substantive answer without evidence citations -> ungrounded
                return CitationValidationResult(
                    is_valid=False,
                    answer=self.FALLBACK_MESSAGE,
                    cited_evidence=[],
                    referenced_ids=[],
                    invalid_ids=[],
                )

        # 3. All citations are valid
        cited_evidence = [valid_ids_map[eid] for eid in referenced_ids]
        return CitationValidationResult(
            is_valid=True,
            answer=cleaned_answer,
            cited_evidence=cited_evidence,
            referenced_ids=referenced_ids,
            invalid_ids=[],
        )


citation_validator = CitationValidator()
