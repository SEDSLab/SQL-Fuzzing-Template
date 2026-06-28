"""RIFT comparison stage implementation."""

from typing import Any, Dict, Optional

from comparison.stage import ComparisonStage


class RiftComparisonStage(ComparisonStage):
    """Default comparison implementation used by the RIFT pipeline."""

    def compare(
        self,
        original_sql: str,
        mutated_sql: str,
        db_config: Optional[Dict[str, Any]] = None,
        **context: Any,
    ) -> Dict[str, Any]:
        active_db_config = db_config if db_config is not None else self.db_config
        return {
            "status": "comparison_interface_only",
            "implementation": "RIFT",
            "original_sql": original_sql,
            "mutated_sql": mutated_sql,
            "db_config": active_db_config,
            "context": context,
        }
