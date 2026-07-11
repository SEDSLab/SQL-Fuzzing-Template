"""Query scope and visible column management."""

from typing import List, Optional

from data_structures.column import Column
from data_structures.table import Table

from ..types import ColumnSymbol, QueryScope, RelationRef


class ScopeResolver:
    """Manage nested SELECT scopes and visible relation columns."""

    def __init__(self):
        self._stack: List[QueryScope] = []

    def push_scope(self, allow_outer_refs: bool = False) -> QueryScope:
        parent = self._stack[-1] if self._stack else None
        scope = QueryScope(
            level=len(self._stack),
            parent=parent,
            allow_outer_refs=allow_outer_refs,
        )
        self._stack.append(scope)
        return scope

    def pop_scope(self) -> QueryScope:
        if not self._stack:
            raise RuntimeError("Cannot pop an empty SQL generation scope stack")
        return self._stack.pop()

    def current_scope(self) -> QueryScope:
        if not self._stack:
            return self.push_scope()
        return self._stack[-1]

    def register_table(self, table: Table, alias: str) -> RelationRef:
        relation = RelationRef(
            alias=alias,
            source_name=table.name,
            relation_type="table",
            source=table,
            columns=[
                ColumnSymbol(
                    name=col.name,
                    table_alias=alias,
                    data_type=col.data_type,
                    category=col.category,
                    nullable=getattr(col, "is_nullable", True),
                )
                for col in table.columns
            ],
        )
        self.register_relation(relation)
        return relation

    def register_derived(self, alias: str, source_name: str, source: object, columns: List[ColumnSymbol]) -> RelationRef:
        relation = RelationRef(
            alias=alias,
            source_name=source_name,
            relation_type="derived",
            source=source,
            columns=[ColumnSymbol(col.name, alias, col.data_type, col.category, col.nullable, col.source_expr) for col in columns],
        )
        self.register_relation(relation)
        return relation

    def register_relation(self, relation: RelationRef) -> None:
        self.current_scope().relations[relation.alias] = relation

    def register_select_alias(self, alias: str, column: ColumnSymbol) -> None:
        self.current_scope().select_aliases[alias] = column
        self.current_scope().output_columns[alias] = column

    def visible_columns(
        self,
        category: Optional[str] = None,
        include_outer: bool = False,
        include_select_aliases: bool = False,
    ) -> List[ColumnSymbol]:
        columns: List[ColumnSymbol] = []
        scope: Optional[QueryScope] = self.current_scope()
        while scope:
            for relation in scope.relations.values():
                for col in relation.columns:
                    if category is None or col.category == category:
                        columns.append(col)
            if include_select_aliases:
                for col in scope.select_aliases.values():
                    if category is None or col.category == category:
                        columns.append(col)
            if not include_outer:
                break
            scope = scope.parent
        return columns

    def resolve_column(self, table_alias: str, column_name: str, include_outer: bool = False) -> Optional[ColumnSymbol]:
        scope: Optional[QueryScope] = self.current_scope()
        while scope:
            relation = scope.relations.get(table_alias)
            if relation:
                for col in relation.columns:
                    if col.name == column_name:
                        return col
            if not include_outer:
                break
            scope = scope.parent
        return None


def column_symbol_to_column(symbol: ColumnSymbol) -> Column:
    """Convert a visible column symbol to the legacy Column class."""

    return Column(
        name=symbol.name,
        data_type=symbol.data_type,
        category=symbol.category,
        is_nullable=symbol.nullable,
        table_name=symbol.table_alias or "",
    )
