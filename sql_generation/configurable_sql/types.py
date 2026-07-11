"""Shared request and result types for configurable SQL generators."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set

from ast_nodes import ASTNode


@dataclass(frozen=True)
class ColumnSymbol:
    """A column visible in a query scope."""

    name: str
    table_alias: Optional[str]
    data_type: str
    category: str
    nullable: bool = True
    source_expr: Optional[ASTNode] = None

    @property
    def qualified_name(self) -> str:
        if self.table_alias:
            return f"{self.table_alias}.{self.name}"
        return self.name


@dataclass
class RelationRef:
    """A table-like source visible through an alias."""

    alias: str
    source_name: str
    relation_type: Literal["table", "cte", "derived"]
    source: Any
    columns: List[ColumnSymbol]


@dataclass
class QueryScope:
    """Visibility scope for one SELECT block."""

    level: int
    parent: Optional["QueryScope"] = None
    allow_outer_refs: bool = False
    relations: Dict[str, RelationRef] = field(default_factory=dict)
    select_aliases: Dict[str, ColumnSymbol] = field(default_factory=dict)
    output_columns: Dict[str, ColumnSymbol] = field(default_factory=dict)


@dataclass
class Generated:
    """Generator output plus semantic metadata."""

    node: ASTNode
    type_category: Optional[str] = None
    data_type: Optional[str] = None
    output_columns: List[ColumnSymbol] = field(default_factory=list)
    used_aggregate: bool = False
    used_window: bool = False
    referenced_columns: Set[str] = field(default_factory=set)


@dataclass
class GenerationRequest:
    """Base request passed to a module generator."""

    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ColumnRequest:
    """Column selection constraints."""

    category: Optional[str] = None
    data_type: Optional[str] = None
    clause: Literal["select", "where", "join", "group_by", "having", "order_by"] = "select"
    include_outer: bool = False
    allow_reuse: bool = True
    orderable_only: bool = False
    nullable_allowed: bool = True

