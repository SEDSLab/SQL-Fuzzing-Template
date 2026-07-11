"""Value expression generation for configurable SQL."""

from ast_nodes import ArithmeticNode, ColumnReferenceNode, FromNode, FunctionCallNode, LimitNode, LiteralNode, OrderByNode, SelectNode, SubqueryNode

from ..resolvers.scope_resolver import column_symbol_to_column
from ..types import ColumnRequest, Generated, GenerationRequest
from .utils import literal_for_category, next_alias, weighted_choice


class ValueExprGenerator:
    """Generate scalar value expressions."""

    def __init__(self, from_generator=None, bool_expr_generator=None, window_function_generator=None):
        self.from_generator = from_generator
        self.bool_expr_generator = bool_expr_generator
        self.window_function_generator = window_function_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        request = request or GenerationRequest()
        expected_category = request.options.get("expected_category")
        allowed_kinds = request.options.get("allowed_kinds")

        weights = ctx.spec.get("select.projection.expr_kinds", {"column": 1.0})
        if allowed_kinds:
            weights = {key: value for key, value in weights.items() if key in allowed_kinds}
        kind = weighted_choice(ctx.rng, weights, "column")

        if kind == "literal":
            return self._literal(ctx, expected_category)
        if kind == "bool_expr":
            generated = self._bool_expr(ctx)
            if generated:
                return generated
        if kind == "subquery":
            generated = self._scalar_subquery(ctx, expected_category)
            if generated:
                return generated
        if kind == "function":
            generated = self._function(ctx, expected_category)
            if generated:
                return generated
        if kind == "window_function" and self.window_function_generator:
            generated = self.window_function_generator.generate(ctx, request)
            if generated:
                return generated
        if kind == "arithmetic":
            generated = self._arithmetic(ctx)
            if generated:
                return generated
        if expected_category == "boolean":
            generated = self._bool_expr(ctx)
            if generated:
                return generated
        return self._column(ctx, expected_category, request.options.get("clause", "select"))

    def _column(self, ctx, expected_category=None, clause="select") -> Generated:
        symbol = ctx.dependency_resolver.choose_column(
            ctx,
            ColumnRequest(category=expected_category, clause=clause, orderable_only=clause == "order_by"),
        )
        node = ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias)
        return Generated(
            node=node,
            type_category=symbol.category,
            data_type=symbol.data_type,
            referenced_columns={symbol.qualified_name},
        )

    def _literal(self, ctx, expected_category=None) -> Generated:
        category = expected_category or ctx.rng.choice(["numeric", "string", "datetime", "boolean"])
        value, data_type = literal_for_category(ctx.rng, category)
        node = LiteralNode(value, data_type)
        node.metadata["category"] = category
        return Generated(node=node, type_category=category, data_type=data_type)

    def _arithmetic(self, ctx) -> Generated | None:
        try:
            left = self._column(ctx, "numeric")
            right_kind = ctx.rng.choice(["column", "literal"])
            right = self._column(ctx, "numeric") if right_kind == "column" else self._numeric_literal(ctx)
        except Exception:
            return None

        node = ArithmeticNode(ctx.rng.choice(ctx.spec.get("arithmetic.operators", ["+", "-", "*", "/", "%"])))
        node.add_child(left.node)
        node.add_child(right.node)
        node.metadata["category"] = "numeric"
        node.metadata["data_type"] = "numeric"
        return Generated(
            node=node,
            type_category="numeric",
            data_type="numeric",
            referenced_columns=set(left.referenced_columns) | set(right.referenced_columns),
        )

    def _numeric_literal(self, ctx) -> Generated:
        value = ctx.rng.randint(1, 100)
        node = LiteralNode(value, "INT")
        node.metadata["category"] = "numeric"
        return Generated(node=node, type_category="numeric", data_type="INT")

    def _bool_expr(self, ctx) -> Generated | None:
        if not self.bool_expr_generator:
            return None
        generated = self.bool_expr_generator.generate(
            ctx,
            GenerationRequest(
                {
                    "clause": "select",
                    "max_depth": ctx.spec.get("select.projection.bool_expr.max_depth", ctx.spec.get("bool_expr.max_depth", 2)),
                }
            ),
        )
        return Generated(
            node=generated.node,
            type_category="boolean",
            data_type="BOOLEAN",
            referenced_columns=generated.referenced_columns,
        )

    def _scalar_subquery(self, ctx, expected_category=None) -> Generated | None:
        if ctx.depth >= int(ctx.spec.get("subquery.max_depth", ctx.max_depth) or ctx.max_depth):
            return None
        if not ctx.tables:
            return None

        child_ctx = ctx.fork(depth=ctx.depth + 1)
        child_ctx.scope_resolver.push_scope()
        try:
            if self.from_generator:
                from_node = self.from_generator.generate(child_ctx).node
            else:
                table = child_ctx.rng.choice(child_ctx.tables)
                alias = next_alias(child_ctx)
                from_node = FromNode()
                from_node.add_table(table, alias)
                child_ctx.scope_resolver.register_table(table, alias)

            select_node = SelectNode()
            select_node.tables = child_ctx.tables
            select_node.functions = child_ctx.functions
            select_node.set_from_clause(from_node)
            projection = self._scalar_subquery_projection(child_ctx, expected_category)
            select_node.add_select_expression(projection.node, "col_1")
            if projection.used_aggregate:
                select_node.metadata["scalar_subquery_has_aggregate"] = True
            if self.bool_expr_generator and child_ctx.rng.random() < float(
                child_ctx.spec.get("subquery.scalar_subquery.where.enabled_prob", 0.0)
            ):
                where_generated = self.bool_expr_generator.generate(
                    child_ctx,
                    GenerationRequest(
                        {
                            "clause": "where",
                            "max_depth": child_ctx.spec.get("subquery.scalar_subquery.where.max_depth", 1),
                        }
                    ),
                )
                select_node.set_where_clause(where_generated.node)
            if (
                not projection.used_aggregate
                and child_ctx.rng.random() < float(child_ctx.spec.get("subquery.scalar_subquery.order_by.enabled_prob", 0.0))
            ):
                order_by = self._scalar_subquery_order_by(child_ctx)
                if order_by:
                    select_node.set_order_by_clause(order_by)
            select_node.set_limit_clause(LimitNode(1))
            subquery_node = SubqueryNode(select_node, "")
            return Generated(
                node=subquery_node,
                type_category=projection.type_category,
                data_type=projection.data_type,
                referenced_columns=set(),
            )
        finally:
            child_ctx.scope_resolver.pop_scope()

    def _scalar_subquery_projection(self, ctx, expected_category=None) -> Generated:
        allowed_kinds = ctx.spec.get(
            "subquery.scalar_subquery.projection.expr_kinds",
            ["column", "function", "arithmetic", "literal"],
        )
        if isinstance(allowed_kinds, dict):
            allowed_kinds = list(allowed_kinds.keys())
        if expected_category == "boolean" and "bool_expr" not in allowed_kinds:
            allowed_kinds = list(allowed_kinds) + ["bool_expr"]
        return self.generate(
            ctx,
            GenerationRequest(
                {
                    "expected_category": expected_category,
                    "allowed_kinds": allowed_kinds,
                    "clause": "select",
                }
            ),
        )

    def _scalar_subquery_order_by(self, ctx):
        try:
            symbol = ctx.dependency_resolver.choose_column(
                ctx,
                ColumnRequest(clause="order_by", orderable_only=True),
            )
        except Exception:
            return None
        order_by = OrderByNode()
        order_by.add_expression(
            ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias),
            ctx.rng.choice(["ASC", "DESC"]),
        )
        return order_by

    def _function(self, ctx, expected_category=None) -> Generated | None:
        functions = [
            func
            for func in ctx.functions
            if getattr(func, "func_type", "") in {"scalar", "aggregate"}
            and getattr(func, "max_params", 0) is not None
            and getattr(func, "max_params", 0) <= 2
            and not getattr(func, "name", "").upper().startswith("JSON_")
            and not self._is_spatial_function(func)
            and getattr(func, "name", "").upper() not in {"POWER", "EXP"}
        ]
        function_type_weights = ctx.spec.get("select.projection.function_types", None)
        if function_type_weights:
            preferred_type = weighted_choice(ctx.rng, function_type_weights, "scalar")
            preferred_functions = [
                func for func in functions
                if getattr(func, "func_type", "") == preferred_type
            ]
            if preferred_functions:
                functions = preferred_functions
        if expected_category:
            functions = [
                func for func in functions
                if self._category_from_type(getattr(func, "return_type", "")) == expected_category
            ] or functions
        if not functions:
            return None

        for _ in range(5):
            func = ctx.rng.choice(functions)
            node = FunctionCallNode(func)
            param_count = ctx.rng.randint(func.min_params, func.max_params)
            ok = True
            for idx in range(param_count):
                if func.name.upper() in {"CAST", "CONVERT"} and idx == 1:
                    node.add_child(LiteralNode(ctx.rng.choice(["SIGNED", "CHAR", "DATE", "DATETIME", "DECIMAL(10,2)"]), "STRING"))
                    continue
                param_type = func.param_types[min(idx, len(func.param_types) - 1)] if func.param_types else "any"
                category = self._category_from_type(param_type)
                arg = self._column(ctx, None if category == "any" else category).node
                if not node.add_child(arg):
                    ok = False
                    break
            if ok:
                return_type = getattr(func, "return_type", "unknown")
                return Generated(
                    node=node,
                    type_category=self._category_from_type(return_type),
                    data_type=return_type,
                    used_aggregate=getattr(func, "func_type", "") == "aggregate",
                )
        return None

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

    def _is_spatial_function(self, func) -> bool:
        name = getattr(func, "name", "").upper()
        return (
            name == "POINT"
            or name.startswith("ST_")
            or "GEOM" in name
            or "GEOMETRY" in name
            or "LINESTRING" in name
            or "POLYGON" in name
            or "WKB" in name
            or "WKT" in name
            or "GEOHASH" in name
        )
