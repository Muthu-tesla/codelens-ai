from pydantic import BaseModel, Field


class CallSiteInfo(BaseModel):
    """Details of an extracted call site with target expression and line number."""
    target: str
    line: int


class FunctionInfo(BaseModel):
    """Details of an extracted function or method."""
    name: str
    line_start: int
    line_end: int
    parameters: list[str] = Field(default_factory=list)
    return_annotation: str | None = None
    decorators: list[str] = Field(default_factory=list)
    docstring: str | None = None
    is_async: bool = False
    calls: list[str] = Field(default_factory=list)
    call_sites: list[CallSiteInfo] = Field(default_factory=list)


class ClassInfo(BaseModel):
    """Details of an extracted class."""
    name: str
    line_start: int
    line_end: int
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionInfo] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    docstring: str | None = None


class RelationshipInfo(BaseModel):
    """Structural relationship between code entities."""
    type: str = Field(
        ...,
        description="Relationship type: module_imports_module, module_contains_function, class_contains_method, class_inherits_class",
    )
    source: str
    target: str


class ModuleAnalysisResult(BaseModel):
    """Full analysis result for a single code file/module."""
    file: str
    imports: list[str] = Field(default_factory=list)
    imported_modules: list[str] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    relationships: list[RelationshipInfo] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
