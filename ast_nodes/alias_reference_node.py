"""AST node for unqualified SELECT alias references."""

from typing import Set

from data_structures.node_type import NodeType

from .ast_node import ASTNode


class AliasReferenceNode(ASTNode):
    """Reference a SELECT-list alias in clauses such as HAVING."""

    def __init__(self, alias: str, data_type: str = "unknown", category: str = "any"):
        super().__init__(NodeType.COLUMN_REFERENCE)
        self.alias = alias
        self.metadata = {
            "column_name": alias,
            "data_type": data_type,
            "category": category,
            "is_aggregate": False,
        }

    def to_sql(self) -> str:
        return self.alias

    def collect_table_aliases(self) -> Set[str]:
        return set()

    def collect_column_aliases(self) -> Set[str]:
        return {self.alias}
