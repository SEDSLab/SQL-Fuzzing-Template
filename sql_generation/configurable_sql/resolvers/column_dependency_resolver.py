"""Column selection and lightweight semantic dependency handling."""

from typing import Optional, Tuple

from ast_nodes import ASTNode

from ..types import ColumnRequest, ColumnSymbol, Generated, QueryScope, RelationRef


class ColumnDependencyResolver:
    """Choose columns and record generated output column metadata."""

    ORDERABLE_CATEGORIES = {"numeric", "string", "datetime", "boolean"}

    def choose_column(self, ctx, request: ColumnRequest) -> ColumnSymbol:
        columns = ctx.scope_resolver.visible_columns(
            category=request.category,
            include_outer=request.include_outer,
            include_select_aliases=request.clause == "order_by",
        )
        if request.orderable_only:
            columns = [col for col in columns if col.category in self.ORDERABLE_CATEGORIES]
        if not request.nullable_allowed:
            columns = [col for col in columns if not col.nullable]
        if request.data_type:
            columns = [col for col in columns if col.data_type.lower() == request.data_type.lower()]
        if not columns:
            fallback = ctx.scope_resolver.visible_columns(include_outer=request.include_outer)
            if request.orderable_only:
                fallback = [col for col in fallback if col.category in self.ORDERABLE_CATEGORIES]
            if not fallback:
                raise ValueError("No visible columns available for configurable SQL generation")
            columns = fallback
        return ctx.rng.choice(columns)

    def choose_compatible_pair(
        self,
        ctx,
        left_scope: Optional[QueryScope] = None,
        right_scope: Optional[QueryScope] = None,
        category: Optional[str] = None,
    ) -> Tuple[ColumnSymbol, ColumnSymbol]:
        left = self.choose_column(ctx, ColumnRequest(category=category, clause="join"))
        right = self.choose_column(ctx, ColumnRequest(category=left.category, clause="join"))
        return left, right

    def register_select_expr(self, ctx, expr: ASTNode, alias: str, generated: Generated) -> ColumnSymbol:
        symbol = ColumnSymbol(
            name=alias,
            table_alias=None,
            data_type=generated.data_type or getattr(expr, "metadata", {}).get("data_type", "unknown"),
            category=generated.type_category or getattr(expr, "metadata", {}).get("category", "any"),
            nullable=True,
            source_expr=expr,
        )
        ctx.scope_resolver.register_select_alias(alias, symbol)
        return symbol

    def build_derived_relation(self, ctx, subquery_node, alias: str) -> RelationRef:
        columns = []
        for col_alias, (_, data_type, category) in subquery_node.column_alias_map.items():
            columns.append(
                ColumnSymbol(
                    name=col_alias,
                    table_alias=alias,
                    data_type=data_type,
                    category=category,
                    nullable=True,
                )
            )
        return ctx.scope_resolver.register_derived(alias, alias, subquery_node, columns)
