"""Defines pipeline configuration/data models used by runtime orchestration."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RunSettings:
    dialect_str: str
    oracle: str = "RIFT"
    run_hours: int = 24
    use_database_tables: bool = False
    db_config: Optional[Dict[str, Any]] = None
    generator_mode: str = "random"
    grammar_path: Optional[str] = None
