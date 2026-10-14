import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Dedicated service for managing the local SentenceTransformer embedding model,
    generating individual and batch vector representations.
    """

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL_NAME,
        dimension: int = settings.EMBEDDING_DIMENSION,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._model: Any = None

    def get_model(self) -> Any:
        """Load the model once per application process."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading local sentence-transformer model: %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                logger.error("Error loading embedding model %s: %s", self.model_name, exc)
                raise RuntimeError(
                    f"Could not initialize embedding model '{self.model_name}': {exc}"
                ) from exc
        return self._model

    def set_model(self, model: Any) -> None:
        """Allow injecting a model instance for testing."""
        self._model = model

    def embed_text(self, text: str) -> list[float]:
        """Generate a single normalized vector embedding."""
        res = self.embed_batch([text])
        if not res:
            return [0.0] * self.dimension
        return res[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate normalized embeddings for a batch of strings.
        Normalizing embeddings ensures that inner product / cosine distance
        computations in pgvector are directly comparable.
        """
        if not texts:
            return []

        model = self.get_model()
        try:
            embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embeddings.tolist()
        except Exception as exc:
            logger.error("Error generating batch embeddings: %s", exc)
            raise RuntimeError(f"Embedding generation failed: {exc}") from exc


embedding_service = EmbeddingService()
