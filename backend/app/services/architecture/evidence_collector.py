import logging
from sqlalchemy.orm import Session

from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile
from app.schemas.architecture import ArchitectureTraceNode
from app.schemas.rag import EvidenceItem
from app.schemas.repository import SemanticSearchResponse

logger = logging.getLogger(__name__)


class ArchitectureEvidenceCollector:
    """
    Retrieves and bounds source code evidence supporting an architecture execution trace.
    Ensures every traced symbol has concrete source code grounding while bounding
    the total evidence set to prevent prompt bloating.
    """

    DEFAULT_MAX_EVIDENCE = 12

    def collect_evidence(
        self,
        db: Session,
        repository_id: int,
        trace_nodes: list[ArchitectureTraceNode],
        search_res: SemanticSearchResponse | None = None,
        max_items: int = DEFAULT_MAX_EVIDENCE,
    ) -> list[EvidenceItem]:
        """
        Collect source code evidence for traced nodes and optionally top search candidates,
        deduplicating and assigning sequential IDs (E1, E2, ...).
        """
        collected: list[dict] = []
        seen_qnames: set[str] = set()

        similarity_by_qname: dict[str, float] = {}
        if search_res and search_res.results:
            for item in search_res.results:
                if item.qualified_name and item.similarity is not None:
                    similarity_by_qname[item.qualified_name] = item.similarity

        # 1. Primary evidence: source chunks for traced execution nodes in trace order
        for node in trace_nodes:
            if len(collected) >= max_items:
                break

            if node.qualified_name in seen_qnames:
                continue

            chunk = (
                db.query(CodeChunk)
                .join(CodeFile, CodeChunk.file_id == CodeFile.id)
                .filter(
                    CodeFile.repository_id == repository_id,
                    CodeChunk.qualified_name == node.qualified_name,
                )
                .first()
            )

            content = chunk.content if chunk else f"Symbol: {node.qualified_name}\nFile: {node.file}"
            sim = similarity_by_qname.get(node.qualified_name)

            seen_qnames.add(node.qualified_name)
            collected.append({
                "file": node.file,
                "qualified_name": node.qualified_name,
                "symbol_type": node.symbol_type,
                "line_start": node.line_start,
                "line_end": node.line_end,
                "content": content,
                "similarity": sim,
            })

        # 2. Secondary evidence: supplementary top semantic search results if capacity remains
        if search_res and search_res.results and len(collected) < max_items:
            for item in search_res.results:
                if len(collected) >= max_items:
                    break

                if not item.qualified_name or item.qualified_name in seen_qnames:
                    continue

                seen_qnames.add(item.qualified_name)
                collected.append({
                    "file": item.file,
                    "qualified_name": item.qualified_name,
                    "symbol_type": item.chunk_type,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "content": item.content,
                    "similarity": item.similarity,
                })

        # 3. Cap strictly at max_items and assign deterministic IDs (E1, E2, ...)
        bounded_items = collected[:max_items]
        evidence_items: list[EvidenceItem] = []
        for idx, item in enumerate(bounded_items, start=1):
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


architecture_evidence_collector = ArchitectureEvidenceCollector()
