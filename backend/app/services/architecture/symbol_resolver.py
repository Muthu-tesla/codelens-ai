import logging
import re
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile, CodeSymbol
from app.schemas.repository import SemanticSearchResponse
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)


class StartSymbolResolver:
    """
    Discovers and validates a starting CodeSymbol for architecture tracing
    from a user's natural-language question using semantic code search.
    Enforces strict repository isolation and symbol validity.
    """

    def __init__(self, top_k_candidates: int = settings.RAG_TOP_K_SEMANTIC) -> None:
        self.top_k_candidates = top_k_candidates

    def resolve_start_symbol(
        self,
        db: Session,
        repository_id: int,
        question: str,
    ) -> tuple[CodeSymbol | None, SemanticSearchResponse]:
        """
        Execute semantic search, identify relevant symbols, and select the
        highest-confidence valid CodeSymbol candidate in the repository.
        Returns (selected_symbol, search_response).
        """
        # 1. Semantic search strictly within the specified repository
        search_res = repository_service.semantic_search(
            db=db,
            repository_id=repository_id,
            query=question,
            limit=self.top_k_candidates,
        )

        if not search_res.results:
            return None, search_res

        # 2. Gather candidates that correspond to actual CodeSymbols in this repository
        chunk_ids = [r.chunk_id for r in search_res.results if r.chunk_id]
        db_chunks = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repository_id,
                CodeChunk.id.in_(chunk_ids),
            )
            .all()
        )
        chunk_by_id = {c.id: c for c in db_chunks}

        # Collect candidate qualified names and their similarity in retrieval order
        candidates: list[tuple[CodeSymbol, float | None]] = []
        seen_symbol_ids: set[int] = set()

        for item in search_res.results:
            db_chunk = chunk_by_id.get(item.chunk_id)
            symbol: CodeSymbol | None = None

            if db_chunk and db_chunk.symbol_id:
                symbol = (
                    db.query(CodeSymbol)
                    .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
                    .filter(
                        CodeFile.repository_id == repository_id,
                        CodeSymbol.id == db_chunk.symbol_id,
                    )
                    .first()
                )

            # Fallback lookup by qualified name if symbol_id wasn't populated on chunk
            if not symbol and item.qualified_name:
                symbol = (
                    db.query(CodeSymbol)
                    .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
                    .filter(
                        CodeFile.repository_id == repository_id,
                        CodeSymbol.qualified_name == item.qualified_name,
                    )
                    .first()
                )

            if symbol and symbol.id not in seen_symbol_ids:
                seen_symbol_ids.add(symbol.id)
                candidates.append((symbol, item.similarity))

        if not candidates:
            return None, search_res

        # 3. Select the highest-confidence relevant symbol:
        # Combine semantic retrieval similarity, callable type priority, and
        # token relevance between question and symbol name/qualified_name.
        stop_words = {
            "how", "does", "an", "the", "and", "are", "for", "with", "from",
            "that", "this", "what", "where", "when", "why", "who", "which",
            "can", "could", "would", "should", "get", "got", "all", "any"
        }
        raw_q_tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
        q_tokens = [t for t in raw_q_tokens if len(t) >= 3 and t not in stop_words]

        def calculate_confidence(sym: CodeSymbol, similarity: float | None) -> float:
            base_sim = similarity if similarity is not None else 0.0
            type_bonus = 0.5 if sym.symbol_type in {"function", "method"} else (0.2 if sym.symbol_type == "class" else 0.0)

            if not q_tokens:
                return base_sim + type_bonus

            sym_text = f"{sym.qualified_name} {sym.name}".lower()
            match_count = 0
            for tok in q_tokens:
                stem = tok
                for suffix in ("ed", "ing", "es", "s"):
                    if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                        stem = tok[: -len(suffix)]
                        break
                if tok in sym_text or stem in sym_text:
                    match_count += 1

            match_ratio = match_count / len(q_tokens)

            # Precision bonus: if symbol's short name consists primarily of query tokens (e.g. create_order)
            name_parts = set(re.findall(r"[a-zA-Z0-9]+", sym.name.lower()))
            name_precision = 0.0
            if name_parts:
                matched_name_tokens = sum(
                    1 for np in name_parts
                    if any(np.startswith(tok[:4]) or tok.startswith(np[:4]) for tok in q_tokens)
                )
                name_precision = (matched_name_tokens / len(name_parts)) * 0.4

            score = (base_sim * 0.3) + (match_ratio * 1.0) + name_precision + type_bonus
            return score, match_count

        scored_candidates = []
        for sym, sim in candidates:
            score, match_cnt = calculate_confidence(sym, sim)
            scored_candidates.append((score, match_cnt, sym))

        # Safety Guard: If question specified substantive terms but NONE of the candidates match
        # any query term (all match_cnt == 0), refuse to produce an arbitrary hallucinated trace.
        if q_tokens and all(match_cnt == 0 for _, match_cnt, _ in scored_candidates):
            logger.info("Refusing arbitrary trace: question terms '%s' matched no symbol candidates.", q_tokens)
            return None, search_res

        scored_candidates.sort(key=lambda item: item[0], reverse=True)

        return scored_candidates[0][2], search_res


start_symbol_resolver = StartSymbolResolver()
