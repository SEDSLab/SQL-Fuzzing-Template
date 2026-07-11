"""Generation context shared by configurable SQL modules."""

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from data_structures.db_dialect import DBDialect
from data_structures.function import Function
from data_structures.table import Table

from .grammar_spec import GrammarSpec, default_select_spec


@dataclass
class GenContext:
    """Mutable generation context for a single SQL generation run."""

    tables: List[Table]
    functions: List[Function]
    dialect: Optional[DBDialect] = None
    spec: GrammarSpec = field(default_factory=default_select_spec)
    rng: random.Random = field(default_factory=random.Random)
    depth: int = 0
    max_depth: int = 3
    flags: Dict[str, Any] = field(default_factory=dict)
    scope_resolver: Any = None
    dependency_resolver: Any = None

    def fork(self, *, depth: Optional[int] = None, allow_outer_refs: bool = False) -> "GenContext":
        child = GenContext(
            tables=self.tables,
            functions=self.functions,
            dialect=self.dialect,
            spec=self.spec,
            rng=self.rng,
            depth=self.depth + 1 if depth is None else depth,
            max_depth=self.max_depth,
            flags=self.flags,
            scope_resolver=self.scope_resolver,
            dependency_resolver=self.dependency_resolver,
        )
        return child

    def should(self, path: str, default_prob: float = 0.0) -> bool:
        probability = self.spec.get(path, default_prob)
        return self.rng.random() < probability

