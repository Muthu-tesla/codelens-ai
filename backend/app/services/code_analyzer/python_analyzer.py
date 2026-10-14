import ast
import logging
from typing import Any

from app.services.code_analyzer.base import BaseCodeAnalyzer
from app.services.code_analyzer.models import (
    CallSiteInfo,
    ClassInfo,
    FunctionInfo,
    ModuleAnalysisResult,
    RelationshipInfo,
)

logger = logging.getLogger(__name__)


class PythonAnalyzer(BaseCodeAnalyzer):
    """AST-based code analyzer for Python files (.py)."""

    @property
    def supported_extensions(self) -> set[str]:
        return {".py"}

    def analyze_code(self, source_code: str, relative_path: str) -> ModuleAnalysisResult:
        """Parse Python source code with `ast` and extract metadata."""
        try:
            tree = ast.parse(source_code, filename=relative_path)
        except SyntaxError as err:
            logger.warning("Syntax error parsing %s: %s", relative_path, err)
            return ModuleAnalysisResult(
                file=relative_path,
                errors=[f"Syntax error at line {err.lineno}: {err.msg}"],
            )
        except Exception as err:
            logger.warning("Unexpected error parsing %s: %s", relative_path, err)
            return ModuleAnalysisResult(
                file=relative_path,
                errors=[f"Failed to parse: {err}"],
            )

        imports: list[str] = []
        imported_modules_set: set[str] = set()
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []
        relationships: list[RelationshipInfo] = []

        # 1. Process top-level imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
                    root_mod = alias.name.split(".")[0]
                    imported_modules_set.add(root_mod)
                    relationships.append(
                        RelationshipInfo(
                            type="module_imports_module",
                            source=relative_path,
                            target=alias.name,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                if mod_name:
                    root_mod = mod_name.split(".")[0]
                    imported_modules_set.add(root_mod)
                    relationships.append(
                        RelationshipInfo(
                            type="module_imports_module",
                            source=relative_path,
                            target=mod_name,
                        )
                    )
                for alias in node.names:
                    full_name = f"{mod_name}.{alias.name}" if mod_name else alias.name
                    imports.append(full_name)

        # 2. Process top-level module statements
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._extract_function_info(stmt)
                functions.append(func_info)
                relationships.append(
                    RelationshipInfo(
                        type="module_contains_function",
                        source=relative_path,
                        target=func_info.name,
                    )
                )

            elif isinstance(stmt, ast.ClassDef):
                class_info = self._extract_class_info(stmt)
                classes.append(class_info)

                # Relationships for inheritance
                for base in class_info.bases:
                    relationships.append(
                        RelationshipInfo(
                            type="class_inherits_class",
                            source=class_info.name,
                            target=base,
                        )
                    )

                # Relationships for methods
                for method in class_info.methods:
                    relationships.append(
                        RelationshipInfo(
                            type="class_contains_method",
                            source=class_info.name,
                            target=method.name,
                        )
                    )

        imported_modules = sorted(list(imported_modules_set))

        return ModuleAnalysisResult(
            file=relative_path,
            imports=imports,
            imported_modules=imported_modules,
            classes=classes,
            functions=functions,
            relationships=relationships,
        )

    def _extract_function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        """Extract metadata from an AST function definition node."""
        params: list[str] = []

        # Positional-only args
        for arg in getattr(node.args, "posonlyargs", []):
            params.append(arg.arg)

        # Regular args
        for arg in node.args.args:
            params.append(arg.arg)

        # Varargs (*args)
        if node.args.vararg:
            params.append(f"*{node.args.vararg.arg}")

        # Keyword-only args
        for arg in node.args.kwonlyargs:
            params.append(arg.arg)

        # Kwargs (**kwargs)
        if node.args.kwarg:
            params.append(f"**{node.args.kwarg.arg}")

        # Return annotation
        return_annot = None
        if node.returns is not None:
            try:
                return_annot = ast.unparse(node.returns)
            except Exception:
                return_annot = None

        # Decorators
        decorators: list[str] = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass

        docstring = ast.get_docstring(node)
        is_async = isinstance(node, ast.AsyncFunctionDef)
        calls, call_sites = self._extract_calls_from_body(node.body)

        return FunctionInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            parameters=params,
            return_annotation=return_annot,
            decorators=decorators,
            docstring=docstring,
            is_async=is_async,
            calls=calls,
            call_sites=call_sites,
        )

    def _extract_calls_from_body(self, body: list[ast.stmt]) -> tuple[list[str], list[CallSiteInfo]]:
        """Extract call target expressions and call sites within a function/method, ignoring nested definitions."""
        calls: list[str] = []
        call_sites: list[CallSiteInfo] = []

        def visit_node(n: ast.AST) -> None:
            if isinstance(n, ast.Call):
                try:
                    target_str = ast.unparse(n.func)
                    if target_str:
                        calls.append(target_str)
                        call_sites.append(CallSiteInfo(target=target_str, line=n.lineno))
                except Exception:
                    pass

            for child in ast.iter_child_nodes(n):
                # Avoid descending into nested functions or class definitions
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    visit_node(child)

        for stmt in body:
            visit_node(stmt)

        return calls, call_sites

    def _extract_class_info(self, node: ast.ClassDef) -> ClassInfo:
        """Extract metadata from an AST class definition node."""
        bases: list[str] = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                pass

        decorators: list[str] = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass

        docstring = ast.get_docstring(node)

        methods: list[FunctionInfo] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function_info(item))

        return ClassInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            bases=bases,
            methods=methods,
            decorators=decorators,
            docstring=docstring,
        )
