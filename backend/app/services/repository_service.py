from collections import defaultdict
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.code_graph import (
    CodeFile,
    CodeRelationship,
    CodeSymbol,
    RelationshipType,
    SymbolType,
)
from app.models.repository import Repository
from app.schemas.repository import (
    CodeRelationshipResponse,
    CodeSymbolBrief,
    CodeSymbolDetailResponse,
    CodeSymbolResponse,
    FileMetadata,
    RepositoryAnalysisSummary,
    RepositoryCreate,
    SearchResultItem,
    SemanticSearchResponse,
)
from app.services.code_analyzer.python_analyzer import PythonAnalyzer
from app.services.code_analyzer.qualified_names import (
    build_class_qualified_name,
    build_function_qualified_name,
    build_function_signature,
    build_method_qualified_name,
    build_module_qualified_name,
    file_path_to_module_name,
)
from app.services.code_chunker import ChunkData, code_chunker
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class RepositoryService:
    def __init__(self) -> None:
        self.python_analyzer = PythonAnalyzer()

    def validate_repository_path(self, path_str: str) -> Path:
        """Validate that the provided path exists, is a directory, and is readable."""
        try:
            path = Path(path_str).resolve()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid repository path format: {exc}",
            )

        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository path does not exist: {path_str}",
            )

        if not path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository path is not a directory: {path_str}",
            )

        if not os.access(path, os.R_OK):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permission denied reading repository path: {path_str}",
            )

        # Enforce authorized repository root boundaries if configured
        if settings.ALLOWED_REPO_ROOTS:
            allowed = False
            for root_dir in settings.ALLOWED_REPO_ROOTS:
                try:
                    resolved_root = Path(root_dir).resolve()
                    if path.is_relative_to(resolved_root):
                        allowed = True
                        break
                except Exception:
                    continue
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Repository path is outside authorized repository roots.",
                )

        return path

    def create_repository(self, db: Session, repo_in: RepositoryCreate) -> Repository:
        """Register a new repository after validating its local path."""
        valid_path = self.validate_repository_path(repo_in.path)

        repo = Repository(
            name=repo_in.name.strip(),
            path=str(valid_path),
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo

    def get_repository(self, db: Session, repository_id: int) -> Repository:
        """Retrieve repository by ID or raise 404."""
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with ID {repository_id} not found",
            )
        return repo

    def list_repositories(self, db: Session) -> list[Repository]:
        """List all registered repositories."""
        return db.query(Repository).order_by(Repository.id.desc()).all()

    def discover_files(self, repo_path: Path) -> list[FileMetadata]:
        """Recursively discover supported source files in the repository."""
        discovered: list[FileMetadata] = []

        if not repo_path.exists() or not repo_path.is_dir():
            return discovered

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d
                for d in dirs
                if d not in settings.IGNORED_DIRS and not d.startswith(".git")
            ]

            for file_name in files:
                file_path = Path(root) / file_name
                ext = file_path.suffix.lower()

                if ext not in settings.SUPPORTED_EXTENSIONS:
                    continue

                try:
                    stat_res = file_path.stat()
                except OSError as exc:
                    logger.warning("Could not stat file %s: %s", file_path, exc)
                    continue

                if stat_res.st_size > settings.MAX_FILE_SIZE_BYTES:
                    logger.info("Skipping large file %s (%d bytes)", file_path, stat_res.st_size)
                    continue

                # Guard against symlinks pointing outside authorized repository directory
                try:
                    resolved_file = file_path.resolve()
                    if not resolved_file.is_relative_to(repo_path.resolve()):
                        logger.warning("Skipping symlink pointing outside repository root: %s -> %s", file_path, resolved_file)
                        continue
                except Exception:
                    continue

                line_count = self._count_lines(file_path)
                try:
                    rel_path = file_path.relative_to(repo_path).as_posix()
                except ValueError:
                    rel_path = file_path.as_posix()

                discovered.append(
                    FileMetadata(
                        relative_path=rel_path,
                        extension=ext,
                        size_bytes=stat_res.st_size,
                        line_count=line_count,
                    )
                )

                if len(discovered) >= settings.MAX_FILES_PER_REPO:
                    logger.warning("Reached maximum file limit (%d) for repository %s", settings.MAX_FILES_PER_REPO, repo_path)
                    break

        discovered.sort(key=lambda item: item.relative_path)
        return discovered

    def analyze_repository(self, db: Session, repository_id: int) -> RepositoryAnalysisSummary:
        """
        Analyze all supported files, persist CodeFiles, CodeSymbols, and
        resolved CodeRelationships idempotently into the database.
        """
        repo = self.get_repository(db, repository_id)
        repo_path = Path(repo.path)

        if not repo_path.exists() or not repo_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository path is no longer accessible on disk: {repo.path}",
            )

        discovered = self.discover_files(repo_path)

        # 1. Synchronize CodeFiles (upsert)
        existing_files = {
            cf.relative_path: cf
            for cf in db.query(CodeFile).filter(CodeFile.repository_id == repository_id).all()
        }
        discovered_rel_paths = set()
        file_records: dict[str, CodeFile] = {}

        for f_meta in discovered:
            rel = f_meta.relative_path
            discovered_rel_paths.add(rel)

            if rel in existing_files:
                cf = existing_files[rel]
                cf.extension = f_meta.extension
                cf.size_bytes = f_meta.size_bytes
                cf.line_count = f_meta.line_count
                file_records[rel] = cf
            else:
                cf = CodeFile(
                    repository_id=repository_id,
                    relative_path=rel,
                    extension=f_meta.extension,
                    size_bytes=f_meta.size_bytes,
                    line_count=f_meta.line_count,
                )
                db.add(cf)
                file_records[rel] = cf

        # Remove deleted files
        for rel, cf in existing_files.items():
            if rel not in discovered_rel_paths:
                db.delete(cf)

        db.flush()

        # 2. Analyze Python files and extract symbols
        python_files_count = 0
        classes_count = 0
        methods_count = 0
        functions_count = 0
        imports_count = 0
        errors: list[str] = []

        # Store analysis results per file for relationship resolution
        file_ast_results: dict[str, Any] = {}

        for f_meta in discovered:
            if f_meta.extension != ".py":
                continue

            python_files_count += 1
            full_file_path = (repo_path / Path(f_meta.relative_path)).resolve()
            if not full_file_path.is_relative_to(repo_path.resolve()):
                logger.warning("Path traversal attempt ignored: %s", f_meta.relative_path)
                continue

            res = self.python_analyzer.analyze_file(
                full_file_path,
                relative_path=f_meta.relative_path,
            )

            if res.errors:
                errors.extend([f"{f_meta.relative_path}: {err}" for err in res.errors])

            classes_count += len(res.classes)
            file_methods = sum(len(c.methods) for c in res.classes)
            methods_count += file_methods
            functions_count += len(res.functions)
            imports_count += len(res.imports)

            file_ast_results[f_meta.relative_path] = res

            # Persist symbols for this python file
            code_file = file_records[f_meta.relative_path]
            self._sync_file_symbols(db, code_file, res)

        db.flush()

        # 3. Resolve and persist CodeRelationships (structural and call relationships)
        relationships_count, call_relationships_count = self._sync_repository_relationships(
            db,
            repository_id=repository_id,
            file_ast_results=file_ast_results,
        )

        # 4. Create/update CodeChunks and generate embeddings
        chunks_count, embeddings_count = self._sync_repository_chunks(
            db,
            repository_id=repository_id,
            repo_path=repo_path,
            file_ast_results=file_ast_results,
            file_records=file_records,
        )

        db.commit()

        # Compatibility note: Phase 1 returned functions as top-level + methods.
        # We preserve that compatibility in `functions` and supply detailed `methods`.
        return RepositoryAnalysisSummary(
            repository_id=repository_id,
            files_analyzed=len(discovered),
            python_files=python_files_count,
            classes=classes_count,
            functions=functions_count + methods_count,
            methods=methods_count,
            imports=imports_count,
            relationships=relationships_count,
            call_relationships=call_relationships_count,
            chunks_created=chunks_count,
            embeddings_generated=embeddings_count,
            errors=errors,
        )

    def _sync_file_symbols(self, db: Session, code_file: CodeFile, res: Any) -> None:
        """Upsert CodeSymbols for a Python file."""
        module_name = file_path_to_module_name(code_file.relative_path)
        existing_symbols = {
            s.qualified_name: s
            for s in db.query(CodeSymbol).filter(CodeSymbol.file_id == code_file.id).all()
        }

        generated_symbols: dict[str, dict[str, Any]] = {}

        # 1. Module Symbol
        mod_qname = build_module_qualified_name(code_file.relative_path)
        mod_short_name = mod_qname.split(".")[-1]
        generated_symbols[mod_qname] = {
            "name": mod_short_name,
            "qualified_name": mod_qname,
            "symbol_type": SymbolType.MODULE.value,
            "line_start": 1,
            "line_end": max(code_file.line_count, 1),
            "signature": None,
            "docstring": None,
        }

        # 2. Classes and Methods
        for c in res.classes:
            class_qname = build_class_qualified_name(module_name, c.name)
            sig = f"class {c.name}({', '.join(c.bases)})" if c.bases else f"class {c.name}"
            generated_symbols[class_qname] = {
                "name": c.name,
                "qualified_name": class_qname,
                "symbol_type": SymbolType.CLASS.value,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "signature": sig,
                "docstring": c.docstring,
            }

            for m in c.methods:
                method_qname = build_method_qualified_name(class_qname, m.name)
                m_sig = build_function_signature(
                    name=m.name,
                    parameters=m.parameters,
                    return_annotation=m.return_annotation,
                    is_async=m.is_async,
                )
                generated_symbols[method_qname] = {
                    "name": m.name,
                    "qualified_name": method_qname,
                    "symbol_type": SymbolType.METHOD.value,
                    "line_start": m.line_start,
                    "line_end": m.line_end,
                    "signature": m_sig,
                    "docstring": m.docstring,
                }

        # 3. Top-level Functions
        for f in res.functions:
            func_qname = build_function_qualified_name(module_name, f.name)
            f_sig = build_function_signature(
                name=f.name,
                parameters=f.parameters,
                return_annotation=f.return_annotation,
                is_async=f.is_async,
            )
            generated_symbols[func_qname] = {
                "name": f.name,
                "qualified_name": func_qname,
                "symbol_type": SymbolType.FUNCTION.value,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "signature": f_sig,
                "docstring": f.docstring,
            }

        # Apply upsert
        for qname, data in generated_symbols.items():
            if qname in existing_symbols:
                sym = existing_symbols[qname]
                sym.name = data["name"]
                sym.symbol_type = data["symbol_type"]
                sym.line_start = data["line_start"]
                sym.line_end = data["line_end"]
                sym.signature = data["signature"]
                sym.docstring = data["docstring"]
            else:
                sym = CodeSymbol(
                    file_id=code_file.id,
                    qualified_name=qname,
                    name=data["name"],
                    symbol_type=data["symbol_type"],
                    line_start=data["line_start"],
                    line_end=data["line_end"],
                    signature=data["signature"],
                    docstring=data["docstring"],
                )
                db.add(sym)

        # Delete any symbol no longer present in AST
        for qname, sym in existing_symbols.items():
            if qname not in generated_symbols:
                db.delete(sym)

    def _sync_repository_relationships(
        self,
        db: Session,
        repository_id: int,
        file_ast_results: dict[str, Any],
    ) -> tuple[int, int]:
        """Resolve and synchronize code relationships (contains, inherits, imports, calls) for the repository."""
        # Query all current symbols in this repository
        symbols = (
            db.query(CodeSymbol)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .filter(CodeFile.repository_id == repository_id)
            .all()
        )

        symbols_by_qname = {s.qualified_name: s for s in symbols}
        modules_by_name = {
            s.qualified_name: s for s in symbols if s.symbol_type == SymbolType.MODULE.value
        }
        classes_by_short_name: dict[str, list[CodeSymbol]] = defaultdict(list)
        functions_by_short_name: dict[str, list[CodeSymbol]] = defaultdict(list)
        symbols_by_mod: dict[str, dict[str, CodeSymbol]] = defaultdict(dict)
        methods_by_class: dict[str, dict[str, CodeSymbol]] = defaultdict(dict)

        for s in symbols:
            if s.symbol_type == SymbolType.CLASS.value:
                classes_by_short_name[s.name].append(s)
                if "." in s.qualified_name:
                    mod_part = s.qualified_name.rsplit(".", 1)[0]
                    symbols_by_mod[mod_part][s.name] = s
            elif s.symbol_type == SymbolType.FUNCTION.value:
                functions_by_short_name[s.name].append(s)
                if "." in s.qualified_name:
                    mod_part = s.qualified_name.rsplit(".", 1)[0]
                    symbols_by_mod[mod_part][s.name] = s
            elif s.symbol_type == SymbolType.METHOD.value:
                if "." in s.qualified_name:
                    cls_part = s.qualified_name.rsplit(".", 1)[0]
                    methods_by_class[cls_part][s.name] = s

        desired_edges: dict[tuple[int, int, str], int | None] = {}

        for rel_path, ast_res in file_ast_results.items():
            mod_name = file_path_to_module_name(rel_path)
            mod_symbol = symbols_by_qname.get(mod_name)
            if not mod_symbol:
                continue

            # 1. Contains: module contains functions
            for f in ast_res.functions:
                func_qname = build_function_qualified_name(mod_name, f.name)
                func_symbol = symbols_by_qname.get(func_qname)
                if func_symbol:
                    desired_edges[(mod_symbol.id, func_symbol.id, RelationshipType.CONTAINS.value)] = None

                    # 1b. Calls from top-level function body
                    calls_data = (
                        [(cs.target, cs.line) for cs in f.call_sites]
                        if getattr(f, "call_sites", None)
                        else [(c, None) for c in getattr(f, "calls", [])]
                    )
                    for call_expr, call_line in calls_data:
                        target_sym = self._resolve_call_target(
                            call_expr=call_expr,
                            caller_mod=mod_name,
                            caller_class=None,
                            ast_res=ast_res,
                            symbols_by_qname=symbols_by_qname,
                            modules_by_name=modules_by_name,
                            symbols_by_mod=symbols_by_mod,
                            methods_by_class=methods_by_class,
                            classes_by_short_name=classes_by_short_name,
                            functions_by_short_name=functions_by_short_name,
                        )
                        if target_sym:
                            key = (func_symbol.id, target_sym.id, RelationshipType.CALLS.value)
                            if key in desired_edges:
                                prev = desired_edges[key]
                                if prev is None or (call_line is not None and call_line < prev):
                                    desired_edges[key] = call_line
                            else:
                                desired_edges[key] = call_line

            # 2. Contains: module contains classes, and class contains methods
            for c in ast_res.classes:
                class_qname = build_class_qualified_name(mod_name, c.name)
                class_symbol = symbols_by_qname.get(class_qname)
                if class_symbol:
                    desired_edges[(mod_symbol.id, class_symbol.id, RelationshipType.CONTAINS.value)] = None

                    for m in c.methods:
                        method_qname = build_method_qualified_name(class_qname, m.name)
                        method_symbol = symbols_by_qname.get(method_qname)
                        if method_symbol:
                            desired_edges[(class_symbol.id, method_symbol.id, RelationshipType.CONTAINS.value)] = None

                            # 2b. Calls from class method body
                            calls_data = (
                                [(cs.target, cs.line) for cs in m.call_sites]
                                if getattr(m, "call_sites", None)
                                else [(c, None) for c in getattr(m, "calls", [])]
                            )
                            for call_expr, call_line in calls_data:
                                target_sym = self._resolve_call_target(
                                    call_expr=call_expr,
                                    caller_mod=mod_name,
                                    caller_class=class_qname,
                                    ast_res=ast_res,
                                    symbols_by_qname=symbols_by_qname,
                                    modules_by_name=modules_by_name,
                                    symbols_by_mod=symbols_by_mod,
                                    methods_by_class=methods_by_class,
                                    classes_by_short_name=classes_by_short_name,
                                    functions_by_short_name=functions_by_short_name,
                                )
                                if target_sym:
                                    key = (method_symbol.id, target_sym.id, RelationshipType.CALLS.value)
                                    if key in desired_edges:
                                        prev = desired_edges[key]
                                        if prev is None or (call_line is not None and call_line < prev):
                                            desired_edges[key] = call_line
                                    else:
                                        desired_edges[key] = call_line

                # 3. Inherits: class inherits parent class
                if class_symbol:
                    for base in c.bases:
                        parent_symbol = self._resolve_parent_class(
                            base=base,
                            mod_name=mod_name,
                            ast_res=ast_res,
                            symbols_by_qname=symbols_by_qname,
                            classes_by_short_name=classes_by_short_name,
                        )
                        if parent_symbol and parent_symbol.id != class_symbol.id:
                            desired_edges[(class_symbol.id, parent_symbol.id, RelationshipType.INHERITS.value)] = None

            # 4. Imports: module imports module or symbol in repository
            for imp in ast_res.imports:
                target_symbol = self._resolve_imported_symbol(
                    imp=imp,
                    current_module=mod_name,
                    symbols_by_qname=symbols_by_qname,
                    modules_by_name=modules_by_name,
                )
                if target_symbol and target_symbol.id != mod_symbol.id:
                    desired_edges[(mod_symbol.id, target_symbol.id, RelationshipType.IMPORTS.value)] = None

        # Query existing relationships in the repository
        existing_rels = {
            (r.source_symbol_id, r.target_symbol_id, r.relationship_type): r
            for r in db.query(CodeRelationship)
            .filter(CodeRelationship.repository_id == repository_id)
            .all()
        }

        # Delete stale relationships and update modified source_line
        for key, rel in existing_rels.items():
            if key not in desired_edges:
                db.delete(rel)
            else:
                target_source_line = desired_edges[key]
                if rel.source_line != target_source_line:
                    rel.source_line = target_source_line

        # Insert new relationships
        for (src_id, tgt_id, rel_type), src_line in desired_edges.items():
            if (src_id, tgt_id, rel_type) not in existing_rels:
                new_rel = CodeRelationship(
                    repository_id=repository_id,
                    source_symbol_id=src_id,
                    target_symbol_id=tgt_id,
                    relationship_type=rel_type,
                    source_line=src_line,
                )
                db.add(new_rel)

        db.flush()
        call_edges_count = sum(1 for (_, _, r_type) in desired_edges if r_type == RelationshipType.CALLS.value)
        return len(desired_edges), call_edges_count

    def _resolve_call_target(
        self,
        call_expr: str,
        caller_mod: str,
        caller_class: str | None,
        ast_res: Any,
        symbols_by_qname: dict[str, CodeSymbol],
        modules_by_name: dict[str, CodeSymbol],
        symbols_by_mod: dict[str, dict[str, CodeSymbol]],
        methods_by_class: dict[str, dict[str, CodeSymbol]],
        classes_by_short_name: dict[str, list[CodeSymbol]],
        functions_by_short_name: dict[str, list[CodeSymbol]],
    ) -> CodeSymbol | None:
        """
        Deterministically resolve an AST call expression to a repository CodeSymbol.
        Returns None for built-ins, external libraries, or unresolved calls.
        """
        # A. Self / Cls method call within a class
        if caller_class and (call_expr.startswith("self.") or call_expr.startswith("cls.")):
            method_name = call_expr.split(".", 1)[1]
            if method_name in methods_by_class.get(caller_class, {}):
                return methods_by_class[caller_class][method_name]

            # Check base classes if resolvable
            cls_short = caller_class.split(".")[-1]
            for cls_sym in classes_by_short_name.get(cls_short, []):
                if cls_sym.qualified_name == caller_class:
                    for rel in getattr(cls_sym, "outgoing_relationships", []):
                        if rel.relationship_type == RelationshipType.INHERITS.value:
                            parent_qname = rel.target_symbol.qualified_name
                            if method_name in methods_by_class.get(parent_qname, {}):
                                return methods_by_class[parent_qname][method_name]

        # B. Direct unqualified call (e.g., validate(), User(), factorial())
        if "." not in call_expr:
            # 1. Same-module function or class
            if call_expr in symbols_by_mod.get(caller_mod, {}):
                target = symbols_by_mod[caller_mod][call_expr]
                if target.symbol_type in (SymbolType.FUNCTION.value, SymbolType.CLASS.value):
                    return target

            # 2. Directly imported symbol
            for imp in ast_res.imports:
                if imp.endswith(f".{call_expr}") or imp == call_expr:
                    if imp in symbols_by_qname and symbols_by_qname[imp].symbol_type in (
                        SymbolType.FUNCTION.value,
                        SymbolType.CLASS.value,
                    ):
                        return symbols_by_qname[imp]

            # 3. Class constructor (unique class in repository)
            if call_expr in classes_by_short_name and len(classes_by_short_name[call_expr]) == 1:
                return classes_by_short_name[call_expr][0]

            # 4. Top-level function (unique function in repository)
            if call_expr in functions_by_short_name and len(functions_by_short_name[call_expr]) == 1:
                return functions_by_short_name[call_expr][0]

            return None

        # C. Qualified call with dot (e.g., validation.validate, pricing.calculate_total)
        # 1. Exact match in repository symbols
        if call_expr in symbols_by_qname:
            return symbols_by_qname[call_expr]

        # 2. Module-qualified call via import prefix
        prefix, member_name = call_expr.rsplit(".", 1)
        for imp in ast_res.imports:
            if imp.endswith(f".{prefix}") or imp == prefix:
                cand = f"{imp}.{member_name}"
                if cand in symbols_by_qname:
                    return symbols_by_qname[cand]

        for mod_qname in modules_by_name:
            if mod_qname == prefix or mod_qname.endswith(f".{prefix}"):
                cand = f"{mod_qname}.{member_name}"
                if cand in symbols_by_qname:
                    return symbols_by_qname[cand]

        # 3. Class-qualified method call (e.g., OrderService.validate)
        if prefix in symbols_by_mod.get(caller_mod, {}):
            cls_qname = f"{caller_mod}.{prefix}"
            if member_name in methods_by_class.get(cls_qname, {}):
                return methods_by_class[cls_qname][member_name]

        if prefix in classes_by_short_name and len(classes_by_short_name[prefix]) == 1:
            cls_sym = classes_by_short_name[prefix][0]
            if member_name in methods_by_class.get(cls_sym.qualified_name, {}):
                return methods_by_class[cls_sym.qualified_name][member_name]

        return None

    def _resolve_parent_class(
        self,
        base: str,
        mod_name: str,
        ast_res: Any,
        symbols_by_qname: dict[str, CodeSymbol],
        classes_by_short_name: dict[str, list[CodeSymbol]],
    ) -> CodeSymbol | None:
        """Resolve a parent class name to a repository CodeSymbol."""
        # 1. Base defined in the same module
        same_mod_qname = f"{mod_name}.{base}"
        if same_mod_qname in symbols_by_qname:
            return symbols_by_qname[same_mod_qname]

        # 2. Base specified as an exact qualified name
        if base in symbols_by_qname:
            return symbols_by_qname[base]

        # 3. Base was imported via 'from x import BaseClass'
        for imp in ast_res.imports:
            if imp.endswith(f".{base}"):
                if imp in symbols_by_qname:
                    return symbols_by_qname[imp]
            elif imp == base and imp in symbols_by_qname:
                return symbols_by_qname[imp]

        # 4. Fallback to unique class in repository with matching short name
        candidates = classes_by_short_name.get(base, [])
        if len(candidates) == 1:
            return candidates[0]

        return None

    def _resolve_imported_symbol(
        self,
        imp: str,
        current_module: str,
        symbols_by_qname: dict[str, CodeSymbol],
        modules_by_name: dict[str, CodeSymbol],
    ) -> CodeSymbol | None:
        """
        Resolve an imported string to a repository CodeSymbol.
        Returns None for external/unresolved dependencies (e.g., fastapi, sqlalchemy).
        """
        # Exact module match
        if imp in modules_by_name:
            return modules_by_name[imp]

        # Exact symbol match
        if imp in symbols_by_qname:
            return symbols_by_qname[imp]

        # Check if importing a module prefix (e.g., 'app.services.order_service.Order' -> 'app.services.order_service')
        if "." in imp:
            prefix = imp.rsplit(".", 1)[0]
            if prefix in modules_by_name:
                return modules_by_name[prefix]

        # Check suffix match for relative/internal packages
        for mod_qname, mod_sym in modules_by_name.items():
            if mod_qname.endswith(f".{imp}") or imp.endswith(f".{mod_qname}"):
                return mod_sym

        return None

    def list_symbols(
        self,
        db: Session,
        repository_id: int,
        symbol_type: str | None = None,
        search: str | None = None,
    ) -> list[CodeSymbolResponse]:
        """List symbols in a repository with optional type filtering and search."""
        self.get_repository(db, repository_id)

        query = (
            db.query(CodeSymbol, CodeFile.relative_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .filter(CodeFile.repository_id == repository_id)
        )

        if symbol_type:
            query = query.filter(CodeSymbol.symbol_type == symbol_type.lower())

        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    CodeSymbol.name.ilike(search_pattern),
                    CodeSymbol.qualified_name.ilike(search_pattern),
                )
            )

        results = query.order_by(CodeSymbol.qualified_name.asc()).all()

        output: list[CodeSymbolResponse] = []
        for sym, rel_path in results:
            item = CodeSymbolResponse.model_validate(sym)
            item.relative_path = rel_path
            output.append(item)
        return output

    def get_symbol(
        self,
        db: Session,
        repository_id: int,
        symbol_id: int,
    ) -> CodeSymbolDetailResponse:
        """Get detailed information about a single code symbol."""
        self.get_repository(db, repository_id)

        res = (
            db.query(CodeSymbol, CodeFile.relative_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .filter(CodeSymbol.id == symbol_id, CodeFile.repository_id == repository_id)
            .first()
        )
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol with ID {symbol_id} not found in repository {repository_id}",
            )

        sym, rel_path = res

        # Outgoing relationships
        outgoing = (
            db.query(CodeRelationship)
            .options(
                joinedload(CodeRelationship.source_symbol),
                joinedload(CodeRelationship.target_symbol),
            )
            .filter(CodeRelationship.source_symbol_id == symbol_id)
            .all()
        )

        # Incoming relationships
        incoming = (
            db.query(CodeRelationship)
            .options(
                joinedload(CodeRelationship.source_symbol),
                joinedload(CodeRelationship.target_symbol),
            )
            .filter(CodeRelationship.target_symbol_id == symbol_id)
            .all()
        )

        def map_rel(r: CodeRelationship) -> CodeRelationshipResponse:
            return CodeRelationshipResponse(
                id=r.id,
                repository_id=r.repository_id,
                relationship_type=r.relationship_type,
                source_symbol=CodeSymbolBrief(
                    id=r.source_symbol.id,
                    name=r.source_symbol.name,
                    qualified_name=r.source_symbol.qualified_name,
                    symbol_type=r.source_symbol.symbol_type,
                ),
                target_symbol=CodeSymbolBrief(
                    id=r.target_symbol.id,
                    name=r.target_symbol.name,
                    qualified_name=r.target_symbol.qualified_name,
                    symbol_type=r.target_symbol.symbol_type,
                ),
                source_line=r.source_line,
                created_at=r.created_at,
            )

        detail = CodeSymbolDetailResponse(
            id=sym.id,
            file_id=sym.file_id,
            relative_path=rel_path,
            qualified_name=sym.qualified_name,
            name=sym.name,
            symbol_type=sym.symbol_type,
            line_start=sym.line_start,
            line_end=sym.line_end,
            signature=sym.signature,
            docstring=sym.docstring,
            created_at=sym.created_at,
            outgoing_relationships=[map_rel(r) for r in outgoing],
            incoming_relationships=[map_rel(r) for r in incoming],
        )
        return detail

    def list_relationships(
        self,
        db: Session,
        repository_id: int,
        relationship_type: str | None = None,
    ) -> list[CodeRelationshipResponse]:
        """List code relationships for a repository."""
        self.get_repository(db, repository_id)

        query = (
            db.query(CodeRelationship)
            .options(
                joinedload(CodeRelationship.source_symbol),
                joinedload(CodeRelationship.target_symbol),
            )
            .filter(CodeRelationship.repository_id == repository_id)
        )

        if relationship_type:
            query = query.filter(CodeRelationship.relationship_type == relationship_type.lower())

        relationships = query.order_by(CodeRelationship.id.asc()).all()

        output: list[CodeRelationshipResponse] = []
        for r in relationships:
            output.append(
                CodeRelationshipResponse(
                    id=r.id,
                    repository_id=r.repository_id,
                    relationship_type=r.relationship_type,
                    source_symbol=CodeSymbolBrief(
                        id=r.source_symbol.id,
                        name=r.source_symbol.name,
                        qualified_name=r.source_symbol.qualified_name,
                        symbol_type=r.source_symbol.symbol_type,
                    ),
                    target_symbol=CodeSymbolBrief(
                        id=r.target_symbol.id,
                        name=r.target_symbol.name,
                        qualified_name=r.target_symbol.qualified_name,
                        symbol_type=r.target_symbol.symbol_type,
                    ),
                    source_line=r.source_line,
                    created_at=r.created_at,
                )
            )
        return output

    def _sync_repository_chunks(
        self,
        db: Session,
        repository_id: int,
        repo_path: Path,
        file_ast_results: dict[str, Any],
        file_records: dict[str, CodeFile],
    ) -> tuple[int, int]:
        """
        Generate or update CodeChunks and their embeddings for a repository.
        Deterministic identity based on (repository_id, file_id, chunk_type, qualified_name).
        Updates chunk if content changed, recomputing embedding.
        Removes stale chunks if files/symbols were deleted.
        Returns (total_chunks_count, embeddings_generated_count).
        """
        symbols = (
            db.query(CodeSymbol)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .filter(CodeFile.repository_id == repository_id)
            .all()
        )
        symbols_by_file_and_qname: dict[tuple[int, str], CodeSymbol] = {
            (s.file_id, s.qualified_name): s for s in symbols
        }

        existing_chunks = (
            db.query(CodeChunk)
            .filter(CodeChunk.repository_id == repository_id)
            .all()
        )
        existing_chunks_map: dict[tuple[int, str, str | None], CodeChunk] = {
            (c.file_id, c.chunk_type, c.qualified_name): c for c in existing_chunks
        }

        current_chunk_keys: set[tuple[int, str, str | None]] = set()
        chunks_to_embed: list[tuple[CodeChunk, str]] = []

        for rel_path, ast_res in file_ast_results.items():
            code_file = file_records.get(rel_path)
            if not code_file:
                continue

            full_file_path = (repo_path / Path(rel_path)).resolve()
            if not full_file_path.is_relative_to(repo_path.resolve()):
                logger.warning("Path traversal attempt ignored in chunking: %s", rel_path)
                continue

            try:
                with open(full_file_path, "r", encoding="utf-8", errors="replace") as f:
                    source_text = f.read()
            except Exception as exc:
                logger.warning(f"Failed to read file {full_file_path} for chunking: {exc}")
                continue

            generated_chunks = code_chunker.chunk_python_file(
                relative_path=rel_path,
                source_text=source_text,
                ast_result=ast_res,
            )

            for chunk_data in generated_chunks:
                sym_id: int | None = None
                if chunk_data.symbol_qualified_name:
                    sym = symbols_by_file_and_qname.get((code_file.id, chunk_data.symbol_qualified_name))
                    if sym:
                        sym_id = sym.id

                key = (code_file.id, chunk_data.chunk_type, chunk_data.qualified_name)
                current_chunk_keys.add(key)

                if key in existing_chunks_map:
                    chunk_obj = existing_chunks_map[key]
                    chunk_obj.symbol_id = sym_id
                    chunk_obj.line_start = chunk_data.line_start
                    chunk_obj.line_end = chunk_data.line_end

                    if chunk_obj.content != chunk_data.content or chunk_obj.embedding is None:
                        chunk_obj.content = chunk_data.content
                        chunks_to_embed.append((chunk_obj, chunk_data.content))
                else:
                    new_chunk = CodeChunk(
                        repository_id=repository_id,
                        file_id=code_file.id,
                        symbol_id=sym_id,
                        content=chunk_data.content,
                        chunk_type=chunk_data.chunk_type,
                        qualified_name=chunk_data.qualified_name,
                        line_start=chunk_data.line_start,
                        line_end=chunk_data.line_end,
                        embedding=None,
                    )
                    db.add(new_chunk)
                    existing_chunks_map[key] = new_chunk
                    chunks_to_embed.append((new_chunk, chunk_data.content))

        # Remove stale chunks
        for key, old_chunk in list(existing_chunks_map.items()):
            if key not in current_chunk_keys and old_chunk.id is not None:
                db.delete(old_chunk)

        db.flush()

        if chunks_to_embed:
            texts = [c[1] for c in chunks_to_embed]
            vectors = embedding_service.embed_batch(texts)
            for (chunk_obj, _), vec in zip(chunks_to_embed, vectors):
                chunk_obj.embedding = vec
            db.flush()

        total_embedded = (
            db.query(CodeChunk)
            .filter(
                CodeChunk.repository_id == repository_id,
                CodeChunk.embedding.isnot(None),
            )
            .count()
        )

        return len(current_chunk_keys), total_embedded

    def semantic_search(
        self,
        db: Session,
        repository_id: int,
        query: str,
        limit: int = 5,
    ) -> SemanticSearchResponse:
        """
        Execute vector similarity search across repository code chunks.
        Validates repository existence, non-empty query, and limit boundaries.
        Uses pgvector cosine distance on PostgreSQL, or cosine similarity on SQLite.
        """
        # 1. Validate repository
        self.get_repository(db, repository_id)

        # 2. Validate query
        if not query or not query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query cannot be empty",
            )
        clean_query = query.strip()

        # 3. Validate limit
        if limit < 1 or limit > settings.SEARCH_MAX_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limit must be between 1 and {settings.SEARCH_MAX_LIMIT}",
            )

        # 4. Generate query embedding
        query_vector = embedding_service.embed_text(clean_query)

        # 5. Execute similarity search in database
        bind = db.get_bind()
        is_postgres = (bind.dialect.name == "postgresql") if bind else False

        if is_postgres:
            dist_expr = CodeChunk.embedding.cosine_distance(query_vector)
            rows = (
                db.query(CodeChunk, CodeFile.relative_path, dist_expr.label("distance"))
                .join(CodeFile, CodeChunk.file_id == CodeFile.id)
                .filter(
                    CodeChunk.repository_id == repository_id,
                    CodeChunk.embedding.isnot(None),
                )
                .order_by(dist_expr.asc())
                .limit(limit)
                .all()
            )

            results: list[SearchResultItem] = []
            for chunk, rel_path, dist in rows:
                sim = max(0.0, min(1.0, 1.0 - float(dist)))
                results.append(
                    SearchResultItem(
                        chunk_id=chunk.id,
                        file=rel_path,
                        qualified_name=chunk.qualified_name,
                        chunk_type=chunk.chunk_type,
                        line_start=chunk.line_start,
                        line_end=chunk.line_end,
                        similarity=round(sim, 4),
                        content=chunk.content,
                    )
                )
        else:
            # Fallback for SQLite test environment (vectors stored as JSON)
            import math

            chunks = (
                db.query(CodeChunk, CodeFile.relative_path)
                .join(CodeFile, CodeChunk.file_id == CodeFile.id)
                .filter(
                    CodeChunk.repository_id == repository_id,
                    CodeChunk.embedding.isnot(None),
                )
                .all()
            )

            def dot_product(v1: list[float], v2: list[float]) -> float:
                return sum(a * b for a, b in zip(v1, v2))

            def norm(v: list[float]) -> float:
                return math.sqrt(sum(a * a for a in v)) or 1.0

            q_norm = norm(query_vector)
            scored: list[tuple[float, CodeChunk, str]] = []

            for chunk, rel_path in chunks:
                if not chunk.embedding:
                    continue
                c_norm = norm(chunk.embedding)
                sim = dot_product(query_vector, chunk.embedding) / (q_norm * c_norm)
                sim = max(0.0, min(1.0, float(sim)))
                scored.append((sim, chunk, rel_path))

            scored.sort(key=lambda x: x[0], reverse=True)

            results = [
                SearchResultItem(
                    chunk_id=chunk.id,
                    file=rel_path,
                    qualified_name=chunk.qualified_name,
                    chunk_type=chunk.chunk_type,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    similarity=round(sim, 4),
                    content=chunk.content,
                )
                for sim, chunk, rel_path in scored[:limit]
            ]

        return SemanticSearchResponse(
            query=clean_query,
            results=results,
        )

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in file safely, replacing invalid characters."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0


repository_service = RepositoryService()
