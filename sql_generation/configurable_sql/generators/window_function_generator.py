"""Window function expression generation for configurable SQL."""

from ast_nodes import ColumnReferenceNode, FunctionCallNode, LiteralNode

from ..resolvers.scope_resolver import column_symbol_to_column
from ..types import ColumnRequest, Generated
from .utils import weighted_choice


class WindowFunctionGenerator:
    """Generate window functions with their OVER clause metadata."""

    ORDER_REQUIRED = {
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "NTILE",
        "CUME_DIST",
        "PERCENT_RANK",
        "LAG",
        "LEAD",
        "NTH_VALUE",
        "FIRST_VALUE",
        "LAST_VALUE",
    }
    VALUE_RETURN_FROM_ARG = {"LAG", "LEAD", "NTH_VALUE", "FIRST_VALUE", "LAST_VALUE"}

    def generate(self, ctx, request=None) -> Generated | None:
        function_weights = ctx.spec.get("window_function.functions", {})
        functions = [
            func
            for func in ctx.functions
            if getattr(func, "func_type", "") == "window"
            and getattr(func, "name", "").upper() in function_weights
        ]
        if not functions:
            return None

        func_by_name = {func.name.upper(): func for func in functions}
        available_weights = {
            name.upper(): weight
            for name, weight in function_weights.items()
            if name.upper() in func_by_name
        }
        if not available_weights:
            return None

        func_name = weighted_choice(ctx.rng, available_weights, next(iter(available_weights)))
        func = func_by_name[func_name]
        node = FunctionCallNode(func)

        dependency_columns = []
        value_arg = self._add_function_args(ctx, node)
        if value_arg is not None:
            dependency_columns.append(self._column_node(value_arg))
        partition_by = self._window_columns(
            ctx,
            enabled_path="window_function.partition_by.enabled_prob",
            max_path="window_function.partition_by.max_columns",
            default_enabled=0.0,
            dependency_columns=dependency_columns,
        )
        order_by = self._window_columns(
            ctx,
            enabled_path="window_function.order_by.enabled_prob",
            max_path="window_function.order_by.max_columns",
            default_enabled=1.0 if func_name in self.ORDER_REQUIRED else 0.0,
            with_direction=True,
            force=func_name in self.ORDER_REQUIRED,
            dependency_columns=dependency_columns,
        )
        if func_name in self.ORDER_REQUIRED and not order_by:
            order_by = ["(0 + 1) ASC"]

        node.metadata["partition_by"] = partition_by
        node.metadata["order_by"] = order_by
        node.metadata["dependency_columns"] = dependency_columns
        frame_clause = self._frame_clause(ctx)
        if frame_clause:
            node.metadata["frame_clause"] = frame_clause

        data_type = getattr(func, "return_type", "unknown")
        category = self._category_from_type(data_type)
        if func_name in self.VALUE_RETURN_FROM_ARG and value_arg is not None:
            data_type = value_arg.data_type
            category = value_arg.category
            node.metadata["return_type"] = data_type
            node.metadata["category"] = category
        else:
            node.metadata["category"] = category

        return Generated(
            node=node,
            type_category=category,
            data_type=data_type,
            used_window=True,
        )

    def _add_function_args(self, ctx, node: FunctionCallNode):
        name = node.function.name.upper()
        value_arg = None
        if name in {"ROW_NUMBER", "RANK", "DENSE_RANK", "CUME_DIST", "PERCENT_RANK"}:
            return None
        if name == "NTILE":
            node.add_child(LiteralNode(ctx.rng.randint(2, 10), "INT"))
            return None

        value_arg = self._choose_value_column(ctx)
        node.add_child(ColumnReferenceNode(column_symbol_to_column(value_arg), value_arg.table_alias))
        if name == "NTH_VALUE":
            node.add_child(LiteralNode(ctx.rng.randint(1, 5), "INT"))
        return value_arg

    def _choose_value_column(self, ctx):
        return ctx.dependency_resolver.choose_column(
            ctx,
            ColumnRequest(clause="select", orderable_only=True),
        )

    def _column_node(self, symbol):
        return ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias)

    def _window_columns(
        self,
        ctx,
        enabled_path: str,
        max_path: str,
        default_enabled: float,
        with_direction: bool = False,
        force: bool = False,
        dependency_columns: list | None = None,
    ) -> list[str]:
        if not force and ctx.rng.random() >= float(ctx.spec.get(enabled_path, default_enabled)):
            return []

        max_columns = int(ctx.spec.get(max_path, 1) or 1)
        candidates = self._orderable_visible_columns(ctx)
        if not candidates:
            return []
        count = min(ctx.rng.randint(1, max(1, max_columns)), len(candidates))
        selected = ctx.rng.sample(candidates, count)
        columns = []
        for symbol in selected:
            node = self._column_node(symbol)
            sql = node.to_sql()
            if dependency_columns is not None:
                dependency_columns.append(self._column_node(symbol))
            if with_direction:
                sql = f"{sql} {ctx.rng.choice(['ASC', 'DESC'])}"
            columns.append(sql)
        return columns

    def _orderable_visible_columns(self, ctx):
        symbols = ctx.scope_resolver.visible_columns(include_select_aliases=False)
        columns = []
        seen = set()
        for symbol in symbols:
            if symbol.category not in ctx.dependency_resolver.ORDERABLE_CATEGORIES:
                continue
            if not symbol.table_alias:
                continue
            sql = self._column_node(symbol).to_sql()
            if sql in seen:
                continue
            seen.add(sql)
            columns.append(symbol)
        return columns

    def _frame_clause(self, ctx) -> str | None:
        if ctx.rng.random() >= float(ctx.spec.get("window_function.frame.enabled_prob", 0.0)):
            return None
        return ctx.rng.choice(
            ctx.spec.get(
                "window_function.frame.clauses",
                ["ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"],
            )
        )

    def _category_from_type(self, data_type: str) -> str:
        normalized = (data_type or "").lower()
        if normalized in {"int", "integer", "bigint", "smallint", "tinyint", "float", "double", "decimal", "numeric"}:
            return "numeric"
        if normalized in {"string", "varchar", "char", "text"}:
            return "string"
        if normalized in {"date", "datetime", "timestamp", "time"}:
            return "datetime"
        if normalized in {"bool", "boolean"}:
            return "boolean"
        return "any"
