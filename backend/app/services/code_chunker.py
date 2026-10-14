from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from app.models.code_graph import CodeFile, CodeSymbol, SymbolType
from app.services.code_analyzer.qualified_names import file_path_to_module_name


class ChunkData(BaseModel):
    """Structured representation of an extracted code chunk."""
    chunk_type: str
    qualified_name: str
    symbol_name: str
    symbol_qualified_name: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    content: str


class CodeChunker:
    """
    Semantic code chunker that constructs contextual, structured
    chunks using AST CodeSymbol metadata and original source ranges.
    """

    def chunk_python_file(
        self,
        relative_path: str,
        source_text: str | None = None,
        ast_result: Any = None,
        file_path: Path | None = None,
        symbols_by_qname: dict[str, Any] | None = None,
    ) -> list[ChunkData]:
        """Generate semantic chunks for a single Python file from text or path."""
        symbols_map = symbols_by_qname or {}
        chunks: list[ChunkData] = []
        module_name = file_path_to_module_name(relative_path)

        if source_text is not None:
            source_lines = source_text.splitlines(keepends=True)
        elif file_path is not None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    source_lines = f.readlines()
            except OSError:
                source_lines = []
        else:
            source_lines = []

        total_lines = len(source_lines)

        # 1. Module chunk
        mod_sym = symbols_map.get(module_name)
        imports_summary = "\n".join(f"- {imp}" for imp in ast_result.imports[:20]) if (ast_result and ast_result.imports) else "None"
        mod_content = (
            f"File: {relative_path}\n"
            f"Symbol: {module_name}\n"
            f"Type: module\n"
            f"Lines: 1-{max(total_lines, 1)}\n\n"
            f"Imports:\n{imports_summary}"
        )
        chunks.append(
            ChunkData(
                chunk_type=SymbolType.MODULE.value,
                qualified_name=module_name,
                symbol_name=getattr(mod_sym, "name", module_name.split(".")[-1]),
                symbol_qualified_name=module_name,
                line_start=1,
                line_end=max(total_lines, 1),
                content=mod_content,
            )
        )

        # 2. Class chunks
        if ast_result:
            for c in ast_result.classes:
                class_qname = f"{module_name}.{c.name}"
                methods_summary = (
                    "\n".join(f"- {m.name}({', '.join(m.parameters)})" for m in c.methods)
                    if c.methods
                    else "None"
                )
                bases_str = f"({', '.join(c.bases)})" if c.bases else ""
                docstring_part = f"\n\nDocstring:\n{c.docstring}" if c.docstring else ""

                class_content = (
                    f"File: {relative_path}\n"
                    f"Symbol: {class_qname}\n"
                    f"Type: class\n"
                    f"Lines: {c.line_start}-{c.line_end}\n\n"
                    f"Declaration:\nclass {c.name}{bases_str}"
                    f"{docstring_part}\n\n"
                    f"Methods:\n{methods_summary}"
                )

                chunks.append(
                    ChunkData(
                        chunk_type=SymbolType.CLASS.value,
                        qualified_name=class_qname,
                        symbol_name=c.name,
                        symbol_qualified_name=class_qname,
                        line_start=c.line_start,
                        line_end=c.line_end,
                        content=class_content,
                    )
                )

                # 3. Method chunks
                for m in c.methods:
                    method_qname = f"{class_qname}.{m.name}"
                    method_source = self._extract_source_slice(source_lines, m.line_start, m.line_end)
                    ret_str = f" -> {m.return_annotation}" if m.return_annotation else ""
                    sig_prefix = "async def " if m.is_async else "def "
                    sig_str = f"{sig_prefix}{m.name}({', '.join(m.parameters)}){ret_str}"
                    m_doc = f"\n\nDocstring:\n{m.docstring}" if m.docstring else ""

                    method_content = (
                        f"File: {relative_path}\n"
                        f"Class: {class_qname}\n"
                        f"Symbol: {method_qname}\n"
                        f"Type: method\n"
                        f"Lines: {m.line_start}-{m.line_end}\n\n"
                        f"Signature:\n{sig_str}"
                        f"{m_doc}\n\n"
                        f"Source:\n{method_source}"
                    )

                    chunks.append(
                        ChunkData(
                            chunk_type=SymbolType.METHOD.value,
                            qualified_name=method_qname,
                            symbol_name=m.name,
                            symbol_qualified_name=method_qname,
                            line_start=m.line_start,
                            line_end=m.line_end,
                            content=method_content,
                        )
                    )

            # 4. Top-level Function chunks
            for f in ast_result.functions:
                func_qname = f"{module_name}.{f.name}"
                func_source = self._extract_source_slice(source_lines, f.line_start, f.line_end)
                ret_str = f" -> {f.return_annotation}" if f.return_annotation else ""
                sig_prefix = "async def " if f.is_async else "def "
                sig_str = f"{sig_prefix}{f.name}({', '.join(f.parameters)}){ret_str}"
                f_doc = f"\n\nDocstring:\n{f.docstring}" if f.docstring else ""

                func_content = (
                    f"File: {relative_path}\n"
                    f"Symbol: {func_qname}\n"
                    f"Type: function\n"
                    f"Lines: {f.line_start}-{f.line_end}\n\n"
                    f"Signature:\n{sig_str}"
                    f"{f_doc}\n\n"
                    f"Source:\n{func_source}"
                )

                chunks.append(
                    ChunkData(
                        chunk_type=SymbolType.FUNCTION.value,
                        qualified_name=func_qname,
                        symbol_name=f.name,
                        symbol_qualified_name=func_qname,
                        line_start=f.line_start,
                        line_end=f.line_end,
                        content=func_content,
                    )
                )

        return chunks

    def chunk_file(
        self,
        file_path: Path,
        relative_path: str,
        ast_res: Any,
        symbols_by_qname: dict[str, Any] | None = None,
    ) -> list[ChunkData]:
        """Convenience method accepting file_path."""
        return self.chunk_python_file(
            relative_path=relative_path,
            file_path=file_path,
            ast_result=ast_res,
            symbols_by_qname=symbols_by_qname,
        )

    def _extract_source_slice(self, lines: list[str], start_line: int, end_line: int) -> str:
        """Extract verbatim source code lines (1-indexed inclusive)."""
        if not lines or start_line < 1:
            return ""
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return "".join(lines[start_idx:end_idx]).strip()


code_chunker = CodeChunker()
