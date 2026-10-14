from abc import ABC, abstractmethod
from pathlib import Path

from app.services.code_analyzer.models import ModuleAnalysisResult


class BaseCodeAnalyzer(ABC):
    """Abstract base class for programming language code analyzers."""

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Return the set of file extensions this analyzer supports (e.g., {'.py'})."""
        pass

    def can_analyze(self, file_extension: str) -> bool:
        """Check if this analyzer handles the given file extension."""
        return file_extension.lower() in self.supported_extensions

    @abstractmethod
    def analyze_code(self, source_code: str, relative_path: str) -> ModuleAnalysisResult:
        """Analyze source code string and return structured findings."""
        pass

    def analyze_file(self, file_path: Path, relative_path: str) -> ModuleAnalysisResult:
        """Read and analyze a source code file from disk."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as exc:
            return ModuleAnalysisResult(
                file=relative_path,
                errors=[f"Failed to read file: {exc}"],
            )

        return self.analyze_code(content, relative_path)
