"""Wraps a WITH clause and its main SELECT query."""

from typing import List, Tuple

from data_structures.node_type import NodeType

from .ast_node import ASTNode
from .select_node import SelectNode
from .with_node import WithNode


class WithSelectNode(ASTNode):
    """Complete query node for WITH ... SELECT ... statements."""

    def __init__(self, with_node: WithNode, select_node: SelectNode):
        super().__init__(NodeType.WITH)
        self.with_node = with_node
        self.select_node = select_node
        self.add_child(with_node)
        self.add_child(select_node)

    def to_sql(self) -> str:
        with_sql = self.with_node.to_sql()
        select_sql = self.select_node.to_sql()
        return f"{with_sql} {select_sql}".strip()

    def validate_all_columns(self) -> Tuple[bool, List[str]]:
        errors = []
        for _, cte_select, _ in self.with_node.ctes:
            if hasattr(cte_select, "validate_all_columns"):
                valid, cte_errors = cte_select.validate_all_columns()
                if not valid:
                    errors.extend(cte_errors)
        if hasattr(self.select_node, "validate_all_columns"):
            valid, main_errors = self.select_node.validate_all_columns()
            if not valid:
                errors.extend(main_errors)
        return len(errors) == 0, errors

    def repair_invalid_columns(self) -> None:
        for _, cte_select, _ in self.with_node.ctes:
            if hasattr(cte_select, "repair_invalid_columns"):
                cte_select.repair_invalid_columns()
        if hasattr(self.select_node, "repair_invalid_columns"):
            self.select_node.repair_invalid_columns()

    def contains_window_function(self) -> bool:
        return any(child.contains_window_function() for child in self.children)

    def contains_aggregate_function(self) -> bool:
        return any(child.contains_aggregate_function() for child in self.children)
