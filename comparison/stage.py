"""Abstract comparison stage for original and mutated SQL pairs."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ComparisonStage(ABC):
    """Abstract base class for result comparison implementations."""

    def __init__(self, db_config: Optional[Dict[str, Any]] = None) -> None:
        self.db_config = db_config or {}

    @abstractmethod
    def compare(
        self,
        original_sql: str,
        mutated_sql: str,
        db_config: Optional[Dict[str, Any]] = None,
        **context: Any,
    ) -> Dict[str, Any]:
        """Compare two SQL variants and return structured comparison data."""
