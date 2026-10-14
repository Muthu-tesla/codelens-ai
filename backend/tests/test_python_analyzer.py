from app.services.code_analyzer.python_analyzer import PythonAnalyzer


def test_python_function_extraction():
    """Test 5: Python function extraction including parameters, lines, annotations, docstrings."""
    code = '''
def calculate_total(price: float, quantity: int = 1, *args, discount: float = 0.0, **kwargs) -> float:
    """Calculate the order total after discounts."""
    return (price * quantity) - discount
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "test_func.py")

    assert len(res.errors) == 0
    assert len(res.functions) == 1
    func = res.functions[0]
    assert func.name == "calculate_total"
    assert func.line_start == 2
    assert func.line_end == 4
    assert func.parameters == ["price", "quantity", "*args", "discount", "**kwargs"]
    assert func.return_annotation == "float"
    assert func.docstring == "Calculate the order total after discounts."
    assert func.is_async is False


def test_python_class_extraction():
    """Test 6: Python class extraction including bases, methods, and docstrings."""
    code = '''
class BaseRepository:
    """Base repository class."""
    pass

class UserRepository(BaseRepository, CacheMixin):
    """User repository for DB queries."""

    def get_by_id(self, user_id: int):
        """Fetch user by id."""
        return None
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "test_class.py")

    assert len(res.errors) == 0
    assert len(res.classes) == 2

    user_repo = next(c for c in res.classes if c.name == "UserRepository")
    assert user_repo.bases == ["BaseRepository", "CacheMixin"]
    assert user_repo.docstring == "User repository for DB queries."
    assert len(user_repo.methods) == 1
    method = user_repo.methods[0]
    assert method.name == "get_by_id"
    assert method.parameters == ["self", "user_id"]
    assert method.docstring == "Fetch user by id."

    # Check relationships
    relationships = res.relationships
    types_and_targets = [(r.type, r.source, r.target) for r in relationships]
    assert ("class_inherits_class", "UserRepository", "BaseRepository") in types_and_targets
    assert ("class_inherits_class", "UserRepository", "CacheMixin") in types_and_targets
    assert ("class_contains_method", "UserRepository", "get_by_id") in types_and_targets


def test_import_extraction():
    """Test 7: Import extraction of module and member imports."""
    code = '''
import os
import sys as system
from pathlib import Path
from app.models.repository import Repository, Base
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "test_imports.py")

    assert len(res.errors) == 0
    assert "os" in res.imports
    assert "sys" in res.imports
    assert "pathlib.Path" in res.imports
    assert "app.models.repository.Repository" in res.imports
    assert "app.models.repository.Base" in res.imports

    assert "os" in res.imported_modules
    assert "sys" in res.imported_modules
    assert "pathlib" in res.imported_modules
    assert "app" in res.imported_modules

    import_rel = [r for r in res.relationships if r.type == "module_imports_module"]
    targets = [r.target for r in import_rel]
    assert "os" in targets
    assert "pathlib" in targets
    assert "app.models.repository" in targets


def test_async_function_detection():
    """Test 8: Async function detection for both top-level functions and class methods."""
    code = '''
async def fetch_remote_data(url: str) -> dict:
    """Async request handler."""
    return {}

class Client:
    async def send_event(self, event_name: str) -> None:
        """Async method."""
        pass

    def synchronous_method(self) -> None:
        pass
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "test_async.py")

    assert len(res.functions) == 1
    assert res.functions[0].name == "fetch_remote_data"
    assert res.functions[0].is_async is True

    assert len(res.classes) == 1
    methods = res.classes[0].methods
    async_method = next(m for m in methods if m.name == "send_event")
    sync_method = next(m for m in methods if m.name == "synchronous_method")
    assert async_method.is_async is True
    assert sync_method.is_async is False


def test_decorator_extraction():
    """Test 9: Extraction of decorators on functions and classes."""
    code = '''
@app.get("/items/{item_id}", response_model=Item)
@require_auth
def read_item(item_id: int):
    return item_id

@dataclass(frozen=True)
class ItemConfig:
    retries: int = 3
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "test_decorators.py")

    assert len(res.functions) == 1
    func = res.functions[0]
    assert len(func.decorators) == 2
    assert any("require_auth" in d for d in func.decorators)
    assert any("app.get" in d for d in func.decorators)

    assert len(res.classes) == 1
    cls_item = res.classes[0]
    assert len(cls_item.decorators) == 1
    assert "dataclass(frozen=True)" in cls_item.decorators[0]


def test_malformed_python_file():
    """Test 10: Graceful error handling for malformed Python files with syntax errors."""
    code = '''
def broken_syntax(:
    this is invalid python syntax %%%
'''
    analyzer = PythonAnalyzer()
    res = analyzer.analyze_code(code, "broken.py")

    # Analyzer must NOT raise an unhandled exception and must report the error cleanly
    assert len(res.errors) == 1
    assert "Syntax error" in res.errors[0]
    assert res.file == "broken.py"
    assert res.classes == []
    assert res.functions == []
