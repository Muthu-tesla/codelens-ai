from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    """Schema for an individual evaluation test case."""
    id: str = Field(..., description="Unique identifier for evaluation case (e.g. Q01)")
    query: str = Field(..., min_length=1, description="Realistic developer search query")
    expected_symbols: list[str] = Field(..., min_length=1, description="List of expected symbol qualified names")
    description: str | None = Field(default=None, description="Optional explanation of evaluation goal")
    category: str | None = Field(default=None, description="Domain category, e.g. payments, auth, inventory")


class QueryEvaluationResult(BaseModel):
    """Evaluation output for a single search query."""
    case_id: str
    query: str
    expected_symbols: list[str]
    retrieved_symbols: list[str] = Field(default_factory=list)
    retrieved_scores: list[float] = Field(default_factory=list)
    first_relevant_rank: int | None = None
    hits_at_k: dict[int, bool] = Field(default_factory=dict)
    reciprocal_rank: float = 0.0


class EvaluationSummary(BaseModel):
    """Aggregated evaluation metrics across all dataset queries."""
    total_queries: int
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    mrr: float = 0.0
    query_results: list[QueryEvaluationResult] = Field(default_factory=list)
