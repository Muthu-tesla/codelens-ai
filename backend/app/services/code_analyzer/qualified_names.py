from pathlib import Path


def file_path_to_module_name(relative_path: str) -> str:
    """
    Convert a source file relative path to a Python module path.
    Examples:
        'app/services/order_service.py' -> 'app.services.order_service'
        'app/core/__init__.py' -> 'app.core'
        'service.py' -> 'service'
        'src/main.py' -> 'src.main'
    """
    # Normalize path separators
    normalized = relative_path.replace("\\", "/").strip("/")

    # Strip .py extension if present
    if normalized.endswith(".py"):
        normalized = normalized[:-3]

    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return "root"

    # Handle __init__ package convention
    if parts[-1] == "__init__" and len(parts) > 1:
        parts.pop()

    return ".".join(parts)


def build_module_qualified_name(relative_path: str) -> str:
    """Generate qualified name for a module symbol."""
    return file_path_to_module_name(relative_path)


def build_class_qualified_name(module_name: str, class_name: str) -> str:
    """Generate qualified name for a class symbol."""
    return f"{module_name}.{class_name}"


def build_method_qualified_name(class_qualified_name: str, method_name: str) -> str:
    """Generate qualified name for a class method symbol."""
    return f"{class_qualified_name}.{method_name}"


def build_function_qualified_name(module_name: str, function_name: str) -> str:
    """Generate qualified name for a top-level function symbol."""
    return f"{module_name}.{function_name}"


def build_function_signature(
    name: str,
    parameters: list[str],
    return_annotation: str | None = None,
    is_async: bool = False,
) -> str:
    """Build a human-readable signature for functions and methods."""
    prefix = "async def " if is_async else "def "
    params_str = ", ".join(parameters)
    ret_str = f" -> {return_annotation}" if return_annotation else ""
    return f"{prefix}{name}({params_str}){ret_str}"
