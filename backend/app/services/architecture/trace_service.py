import collections
import logging
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.schemas.architecture import (
    ArchitectureTraceEdge,
    ArchitectureTraceNode,
    ArchitectureTraceRequest,
    ArchitectureTraceResponse,
)
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)


class ArchitectureTraceService:
    """
    Deterministic architecture call-graph tracer.
    Reconstructs call flows using only the PostgreSQL code knowledge graph (CALLS relationships).
    Purely graph-driven with no LLM, semantic search, or embeddings.
    """

    def __init__(
        self,
        max_depth: int = settings.ARCHITECTURE_TRACE_MAX_DEPTH,
        max_nodes: int = settings.ARCHITECTURE_TRACE_MAX_NODES,
    ) -> None:
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def trace_architecture(
        self,
        db: Session,
        repository_id: int,
        request: ArchitectureTraceRequest,
        max_depth: int | None = None,
        max_nodes: int | None = None,
    ) -> ArchitectureTraceResponse:
        """
        Execute deterministic, bounded breadth-first traversal of outgoing CALLS relationships
        starting from start_symbol.
        """
        # 1. Validate repository existence
        repository_service.get_repository(db, repository_id)

        clean_start = request.start_symbol.strip()
        if not clean_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_symbol cannot be empty.",
            )

        # 2. Resolve start symbol in repository (exact match, no fuzzy / semantic fallback)
        start_row = (
            db.query(CodeSymbol, CodeFile.relative_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .filter(
                CodeFile.repository_id == repository_id,
                CodeSymbol.qualified_name == clean_start,
            )
            .first()
        )

        if not start_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Start symbol '{clean_start}' not found in repository {repository_id}.",
            )

        start_sym, start_file = start_row

        req_depth = getattr(request, "max_depth", None)
        effective_max_depth = max_depth if max_depth is not None else (req_depth if req_depth is not None else self.max_depth)

        req_nodes = getattr(request, "max_nodes", None)
        effective_max_nodes = max_nodes if max_nodes is not None else (req_nodes if req_nodes is not None else self.max_nodes)

        # 3. Bounded deterministic graph traversal (DFS following source call-site order)
        nodes: list[ArchitectureTraceNode] = []
        edges: list[ArchitectureTraceEdge] = []
        visited_ids: set[int] = {start_sym.id}
        seen_edges: set[tuple[str, str]] = set()

        # Step 1: Start node
        nodes.append(
            ArchitectureTraceNode(
                step=1,
                qualified_name=start_sym.qualified_name,
                name=start_sym.name,
                symbol_type=start_sym.symbol_type,
                file=start_file,
                line_start=start_sym.line_start,
                line_end=start_sym.line_end,
                signature=start_sym.signature,
            )
        )

        def dfs(curr_sym: CodeSymbol, curr_depth: int) -> None:
            if curr_depth >= effective_max_depth:
                return

            # Query outgoing CALLS relationships strictly for this repository
            # Primary ordering: source_line ascending (nulls last)
            # Secondary ordering: target qualified_name ascending
            outgoing_calls = (
                db.query(CodeRelationship, CodeSymbol, CodeFile.relative_path)
                .join(CodeSymbol, CodeRelationship.target_symbol_id == CodeSymbol.id)
                .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
                .filter(
                    CodeRelationship.repository_id == repository_id,
                    CodeRelationship.source_symbol_id == curr_sym.id,
                    CodeRelationship.relationship_type == "calls",
                )
                .order_by(
                    CodeRelationship.source_line.asc().nulls_last(),
                    CodeSymbol.qualified_name.asc(),
                )
                .all()
            )

            # Secondary deterministic sorting in Python as safeguard across dialect differences
            outgoing_calls.sort(
                key=lambda item: (
                    item[0].source_line if item[0].source_line is not None else float("inf"),
                    item[1].qualified_name,
                )
            )

            for rel, target_sym, target_file in outgoing_calls:
                edge_key = (curr_sym.qualified_name, target_sym.qualified_name)

                if target_sym.id in visited_ids:
                    # Node already exists in trace; record edge if not yet seen (e.g. cycle or reconvergence)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append(
                            ArchitectureTraceEdge(
                                from_symbol=curr_sym.qualified_name,
                                to_symbol=target_sym.qualified_name,
                                relationship="calls",
                                source_line=rel.source_line,
                            )
                        )
                else:
                    # New node: check node limit
                    if len(nodes) < effective_max_nodes:
                        visited_ids.add(target_sym.id)
                        nodes.append(
                            ArchitectureTraceNode(
                                step=len(nodes) + 1,
                                qualified_name=target_sym.qualified_name,
                                name=target_sym.name,
                                symbol_type=target_sym.symbol_type,
                                file=target_file,
                                line_start=target_sym.line_start,
                                line_end=target_sym.line_end,
                                signature=target_sym.signature,
                            )
                        )
                        if edge_key not in seen_edges:
                            seen_edges.add(edge_key)
                            edges.append(
                                ArchitectureTraceEdge(
                                    from_symbol=curr_sym.qualified_name,
                                    to_symbol=target_sym.qualified_name,
                                    relationship="calls",
                                    source_line=rel.source_line,
                                )
                            )
                        dfs(target_sym, curr_depth + 1)

        dfs(start_sym, 0)

        # 4. Generate deterministic summary
        unique_files = len({n.file for n in nodes})
        if not edges:
            summary = (
                f"Architecture trace for '{clean_start}' contains 1 symbol with no outgoing calls."
            )
        else:
            summary = (
                f"Deterministic architecture trace starting from '{clean_start}' "
                f"discovered {len(nodes)} symbols connected by {len(edges)} calls "
                f"across {unique_files} file(s)."
            )

        return ArchitectureTraceResponse(
            start_symbol=clean_start,
            nodes=nodes,
            edges=edges,
            summary=summary,
        )


trace_service = ArchitectureTraceService()
