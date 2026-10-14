import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.schemas.rag import EvidenceItem
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)


class EvidenceBuilder:
    """
    Constructs a bounded, deduplicated, and deterministic set of code evidence
    combining semantic search retrieval and 1-hop knowledge graph relationships.
    """

    def __init__(
        self,
        top_k_semantic: int = settings.RAG_TOP_K_SEMANTIC,
        max_evidence_items: int = settings.RAG_MAX_EVIDENCE_ITEMS,
    ) -> None:
        self.top_k_semantic = top_k_semantic
        self.max_evidence_items = max_evidence_items

    def build_evidence(
        self,
        db: Session,
        repository_id: int,
        question: str,
    ) -> list[EvidenceItem]:
        """
        Execute semantic search, enrich with 1-hop graph relationships,
        deduplicate, and assign deterministic IDs (E1, E2, ...).
        """
        # 1. Semantic retrieval with repository isolation
        search_res = repository_service.semantic_search(
            db=db,
            repository_id=repository_id,
            query=question,
            limit=self.top_k_semantic,
        )

        if not search_res.results:
            return []

        # Track collected chunks and deduplication by chunk ID
        # Preserve retrieval order: semantic first
        collected_chunks: list[dict] = []
        seen_chunk_ids: set[int] = set()
        seen_signatures: set[tuple[str, str | None, int | None, int | None]] = set()

        # Collect chunk IDs to look up their symbols for 1-hop expansion
        chunk_ids = [item.chunk_id for item in search_res.results]
        db_chunks = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repository_id,
                CodeChunk.id.in_(chunk_ids),
            )
            .all()
        )
        chunk_by_id = {c.id: c for c in db_chunks}

        top_symbol_ids: set[int] = set()

        for item in search_res.results:
            db_chunk = chunk_by_id.get(item.chunk_id)
            if not db_chunk:
                continue

            sig = (item.file, item.qualified_name, item.line_start, item.line_end)
            if item.chunk_id not in seen_chunk_ids and sig not in seen_signatures:
                seen_chunk_ids.add(item.chunk_id)
                seen_signatures.add(sig)
                collected_chunks.append({
                    "chunk_id": item.chunk_id,
                    "file": item.file,
                    "qualified_name": item.qualified_name,
                    "symbol_type": item.chunk_type,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "content": item.content,
                    "similarity": item.similarity,
                })

            if db_chunk.symbol_id:
                top_symbol_ids.add(db_chunk.symbol_id)

        # 2. 1-hop Knowledge Graph Expansion for top symbols
        # Only query if we have room under max_evidence_items
        if top_symbol_ids and len(collected_chunks) < self.max_evidence_items:
            allowed_rels = {"calls", "contains", "imports", "inherits"}
            outgoing_rels = (
                db.query(CodeRelationship)
                .filter(
                    CodeRelationship.repository_id == repository_id,
                    CodeRelationship.source_symbol_id.in_(top_symbol_ids),
                    CodeRelationship.relationship_type.in_(allowed_rels),
                )
                .all()
            )
            incoming_rels = (
                db.query(CodeRelationship)
                .filter(
                    CodeRelationship.repository_id == repository_id,
                    CodeRelationship.target_symbol_id.in_(top_symbol_ids),
                    CodeRelationship.relationship_type.in_(allowed_rels),
                )
                .all()
            )

            related_symbol_ids: set[int] = set()
            for rel in outgoing_rels:
                related_symbol_ids.add(rel.target_symbol_id)
            for rel in incoming_rels:
                related_symbol_ids.add(rel.source_symbol_id)

            # Exclude already processed symbols
            related_symbol_ids -= top_symbol_ids

            if related_symbol_ids:
                # Retrieve chunks for related symbols
                related_chunks = (
                    db.query(CodeChunk, CodeFile.relative_path)
                    .join(CodeFile, CodeChunk.file_id == CodeFile.id)
                    .filter(
                        CodeChunk.repository_id == repository_id,
                        CodeChunk.symbol_id.in_(related_symbol_ids),
                    )
                    .order_by(CodeChunk.id.asc())
                    .all()
                )

                for r_chunk, rel_path in related_chunks:
                    if len(collected_chunks) >= self.max_evidence_items:
                        break

                    sig = (rel_path, r_chunk.qualified_name, r_chunk.line_start, r_chunk.line_end)
                    if r_chunk.id not in seen_chunk_ids and sig not in seen_signatures:
                        seen_chunk_ids.add(r_chunk.id)
                        seen_signatures.add(sig)
                        collected_chunks.append({
                            "chunk_id": r_chunk.id,
                            "file": rel_path,
                            "qualified_name": r_chunk.qualified_name,
                            "symbol_type": r_chunk.chunk_type,
                            "line_start": r_chunk.line_start,
                            "line_end": r_chunk.line_end,
                            "content": r_chunk.content,
                            "similarity": None,
                        })

        # 3. Cap strictly at max_evidence_items
        bounded_chunks = collected_chunks[: self.max_evidence_items]

        # 4. Assign deterministic IDs E1, E2, ...
        evidence_items: list[EvidenceItem] = []
        for idx, item in enumerate(bounded_chunks, start=1):
            evidence_items.append(
                EvidenceItem(
                    id=f"E{idx}",
                    file=item["file"],
                    qualified_name=item["qualified_name"],
                    symbol_type=item["symbol_type"],
                    line_start=item["line_start"],
                    line_end=item["line_end"],
                    content=item["content"],
                    similarity=item["similarity"],
                )
            )

        return evidence_items


evidence_builder = EvidenceBuilder()
