"""SELECT generation driven by GrammarSpec."""

from ast_nodes import AliasReferenceNode, ColumnReferenceNode, FunctionCallNode, GroupByNode, LiteralNode, OrderByNode, SelectNode, SubqueryNode, WithNode, WithSelectNode
from data_structures.column import Column
from data_structures.table import Table

from ..types import Generated, GenerationRequest
from .utils import rand_range


class SelectGenerator:
    """Generate a SELECT AST using configurable modules."""

    def __init__(
        self,
        from_generator,
        projection_generator,
        bool_expr_generator,
        order_by_generator,
        limit_generator,
    ):
        self.from_generator = from_generator
        self.projection_generator = projection_generator
        self.bool_expr_generator = bool_expr_generator
        self.order_by_generator = order_by_generator
        self.limit_generator = limit_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        request = request or GenerationRequest()
        ctx.scope_resolver.push_scope(allow_outer_refs=bool(request.options.get("allow_outer_refs", False)))
        previous_cte_tables = ctx.flags.get("cte_tables")
        try:
            with_node = self._maybe_generate_ctes(ctx, request)
            select_node = SelectNode()
            select_node.tables = ctx.tables
            select_node.functions = ctx.functions
            select_node.distinct = ctx.should("select.distinct_prob", 0.0)

            from_generated = self.from_generator.generate(ctx)
            select_node.set_from_clause(from_generated.node)

            projection_generated = self.projection_generator.generate(
                ctx,
                GenerationRequest(
                    {
                        "count": request.options.get("projection_count"),
                        "categories": request.options.get("projection_categories"),
                    }
                ),
            )
            for expr, alias in projection_generated.node:
                select_node.add_select_expression(expr, alias)

            has_aggregate = self._apply_aggregate_dependencies(select_node)

            if self._should_clause(ctx, request, "where", "select.where.enabled_prob", 0.0):
                where_generated = self.bool_expr_generator.generate(ctx)
                select_node.set_where_clause(where_generated.node)

            if (
                has_aggregate
                and select_node.group_by_clause
                and self._should_clause(ctx, request, "having", "select.having.enabled_prob", 0.0)
            ):
                having_generated = self.bool_expr_generator.generate(
                    ctx,
                    GenerationRequest(
                        {
                            "clause": "having",
                            "select_node": select_node,
                            "max_depth": ctx.spec.get("having_bool.max_depth", 2),
                        }
                    ),
                )
                select_node.set_having_clause(having_generated.node)

            if self._should_clause(ctx, request, "order_by", "select.order_by.enabled_prob", 0.0):
                order_by_node = self._generate_order_by(ctx, select_node, has_aggregate)
                if order_by_node:
                    select_node.set_order_by_clause(order_by_node)

            if self._should_clause(ctx, request, "limit", "select.limit.enabled_prob", 0.0):
                limit_generated = self.limit_generator.generate(ctx)
                select_node.set_limit_clause(limit_generated.node)

            if hasattr(select_node, "validate_all_columns"):
                valid, _ = select_node.validate_all_columns()
                if not valid and hasattr(select_node, "repair_invalid_columns"):
                    select_node.repair_invalid_columns()

            node = WithSelectNode(with_node, select_node) if with_node else select_node
            return Generated(node=node, output_columns=projection_generated.output_columns)
        finally:
            if previous_cte_tables is None:
                ctx.flags.pop("cte_tables", None)
            else:
                ctx.flags["cte_tables"] = previous_cte_tables
            ctx.scope_resolver.pop_scope()

    def _maybe_generate_ctes(self, ctx, request: GenerationRequest):
        allow_cte = request.options.get(
            "allow_cte",
            ctx.depth == 0
            and not request.options.get("as_subquery")
            and not request.options.get("for_set_operation"),
        )
        if not allow_cte or not ctx.should("select.cte.enabled_prob", 0.0):
            return None

        cte_count = rand_range(ctx.rng, ctx.spec.get("select.cte.count", [1, 1]), 1, 1)
        projection_count_cfg = ctx.spec.get("select.cte.projection_count", [1, 3])
        with_node = WithNode()
        cte_tables = list(ctx.flags.get("cte_tables", []))

        for _ in range(cte_count):
            cte_name = self._next_cte_name(ctx)
            projection_count = rand_range(ctx.rng, projection_count_cfg, 1, 3)
            child_ctx = ctx.fork(depth=ctx.depth + 1)
            generated = self.generate(
                child_ctx,
                GenerationRequest(
                    {
                        "allow_cte": False,
                        "projection_count": projection_count,
                        "clause_probabilities": {
                            "where": ctx.spec.get("select.cte.where.enabled_prob", ctx.spec.get("select.where.enabled_prob", 0.0)),
                            "having": ctx.spec.get("select.cte.having.enabled_prob", ctx.spec.get("select.having.enabled_prob", 0.0)),
                            "order_by": ctx.spec.get("select.cte.order_by.enabled_prob", ctx.spec.get("select.order_by.enabled_prob", 0.0)),
                            "limit": ctx.spec.get("select.cte.limit.enabled_prob", ctx.spec.get("select.limit.enabled_prob", 0.0)),
                        },
                    }
                ),
            )
            cte_select = generated.node
            columns = [
                Column(
                    name=col.name,
                    data_type=col.data_type,
                    category=col.category,
                    is_nullable=col.nullable,
                    table_name=cte_name,
                )
                for col in generated.output_columns
            ]
            if not columns:
                columns = [Column("col_1", "INT", "numeric", True, cte_name)]
            cte_table = Table(
                name=cte_name,
                columns=columns,
                primary_key=columns[0].name,
                foreign_keys=[],
            )
            with_node.add_cte(cte_name, cte_select, len(columns))
            cte_tables.append(cte_table)

        ctx.flags["cte_tables"] = cte_tables
        return with_node

    def _next_cte_name(self, ctx) -> str:
        counter = int(ctx.flags.get("cte_counter", 0)) + 1
        ctx.flags["cte_counter"] = counter
        return f"cte_{counter}"

    def _should_clause(self, ctx, request: GenerationRequest, name: str, path: str, default_prob: float) -> bool:
        clause_probabilities = request.options.get("clause_probabilities") or {}
        if name in clause_probabilities:
            return ctx.rng.random() < float(clause_probabilities[name])
        return ctx.should(path, default_prob)

    def _generate_order_by(self, ctx, select_node: SelectNode, has_aggregate: bool):
        if has_aggregate or select_node.distinct:
            return self._order_by_select_aliases(ctx, select_node)
        generated = self.order_by_generator.generate(ctx)
        return generated.node

    def _order_by_select_aliases(self, ctx, select_node: SelectNode):
        candidates = [
            (expr, alias)
            for expr, alias in select_node.select_expressions
            if alias and self._is_orderable_expr(expr)
        ]
        if not candidates:
            return None

        max_columns = int(ctx.spec.get("select.order_by.max_columns", 2) or 1)
        count = min(ctx.rng.randint(1, max(1, max_columns)), len(candidates))
        selected = ctx.rng.sample(candidates, count)
        order_by = OrderByNode()
        for expr, alias in selected:
            order_by.add_expression(
                AliasReferenceNode(alias, self._expr_data_type(expr), self._expr_category(expr)),
                ctx.rng.choice(["ASC", "DESC"]),
            )
        return order_by

    def _is_orderable_expr(self, expr) -> bool:
        if isinstance(expr, SubqueryNode):
            return False
        category = self._expr_category(expr)
        return category in {"numeric", "string", "datetime", "boolean", "any"}

    def _expr_category(self, expr) -> str:
        metadata = getattr(expr, "metadata", {}) or {}
        category = metadata.get("category")
        if category:
            return category
        data_type = self._expr_data_type(expr).lower()
        if data_type in {"int", "integer", "bigint", "smallint", "tinyint", "float", "double", "decimal", "numeric"}:
            return "numeric"
        if data_type in {"string", "varchar", "char", "text"}:
            return "string"
        if data_type in {"date", "datetime", "timestamp", "time"}:
            return "datetime"
        if data_type in {"bool", "boolean"}:
            return "boolean"
        return "any"

    def _expr_data_type(self, expr) -> str:
        metadata = getattr(expr, "metadata", {}) or {}
        return metadata.get("return_type") or metadata.get("data_type") or getattr(expr, "data_type", "unknown")

    def _apply_aggregate_dependencies(self, select_node: SelectNode) -> bool:
        """Automatically add GROUP BY expressions required by aggregate SELECT lists."""

        has_aggregate = any(
            self._contains_outer_aggregate(expr)
            for expr, _ in select_node.select_expressions
        )
        if not has_aggregate:
            return False

        group_by = GroupByNode()
        seen_sql = set()
        for expr, _ in select_node.select_expressions:
            if self._contains_window_function(expr):
                for dependency in getattr(expr, "metadata", {}).get("dependency_columns", []):
                    expr_sql = dependency.to_sql()
                    if expr_sql in seen_sql:
                        continue
                    seen_sql.add(expr_sql)
                    group_by.add_expression(dependency)
                continue
            if not self._requires_group_by(expr):
                continue
            dependencies = self._group_by_dependencies(expr)
            for dependency in dependencies:
                expr_sql = dependency.to_sql()
                if expr_sql in seen_sql:
                    continue
                seen_sql.add(expr_sql)
                group_by.add_expression(dependency)

        if group_by.expressions:
            select_node.set_group_by_clause(group_by)
        return True

    def _contains_outer_aggregate(self, expr) -> bool:
        if isinstance(expr, SubqueryNode):
            return False
        if isinstance(expr, FunctionCallNode):
            return getattr(getattr(expr, "function", None), "func_type", "") == "aggregate"
        return any(self._contains_outer_aggregate(child) for child in getattr(expr, "children", []) or [])

    def _contains_window_function(self, expr) -> bool:
        return bool(hasattr(expr, "contains_window_function") and expr.contains_window_function())

    def _requires_group_by(self, expr) -> bool:
        if isinstance(expr, (LiteralNode, SubqueryNode)):
            return False
        if self._contains_window_function(expr):
            return False
        if self._contains_outer_aggregate(expr):
            return False
        if not hasattr(expr, "collect_table_aliases"):
            return False
        return bool(expr.collect_table_aliases())

    def _group_by_dependencies(self, expr):
        if isinstance(expr, ColumnReferenceNode):
            return [expr]
        columns = self._collect_column_references(expr)
        return [expr] + columns

    def _collect_column_references(self, expr):
        if isinstance(expr, SubqueryNode):
            return []
        if isinstance(expr, ColumnReferenceNode):
            return [expr]
        columns = []
        for child in getattr(expr, "children", []) or []:
            columns.extend(self._collect_column_references(child))
        return columns
