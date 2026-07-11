"""Boolean expression generation for configurable SQL."""

from ast_nodes import AliasReferenceNode, ColumnReferenceNode, ComparisonNode, FromNode, LimitNode, LiteralNode, LogicalNode, OrderByNode, SelectNode, SubqueryNode

from ..types import ColumnRequest, Generated, GenerationRequest
from .utils import literal_for_category, next_alias, weighted_choice
from ..resolvers.scope_resolver import column_symbol_to_column


class BoolExprGenerator:
    """Generate boolean expressions suitable for WHERE/HAVING."""

    NUMERIC_TYPES = {"INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL"}
    STRING_TYPES = {"VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT", "TINYTEXT", "STRING"}
    DATETIME_TYPES = {"DATE", "DATETIME", "TIMESTAMP", "TIME"}
    BOOLEAN_TYPES = {"BOOLEAN", "BOOL"}

    def __init__(self, from_generator=None, value_expr_generator=None):
        self.from_generator = from_generator
        self.value_expr_generator = value_expr_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        request = request or GenerationRequest()
        clause = request.options.get("clause", "where")
        depth = int(request.options.get("depth", 0))
        max_depth_key = self._config_key(clause, "max_depth")
        max_depth = int(request.options.get("max_depth", ctx.spec.get(max_depth_key, 2)))

        atom_prob = float(ctx.spec.get(self._config_key(clause, "atom_prob"), 0.65))
        if depth >= max_depth or ctx.rng.random() < atom_prob:
            return self._atom(ctx, request)

        connectors_key = self._config_key(clause, "connectors")
        connectors = ctx.spec.get(connectors_key, {"and": 0.5, "or": 0.5})
        connector = weighted_choice(ctx.rng, connectors, "and")
        child_options = dict(request.options)
        child_options.update({"depth": depth + 1, "max_depth": max_depth})
        operand_specs = self._connector_operand_specs(ctx, clause, connector)
        if connector == "not":
            node = LogicalNode("NOT")
            child = self._generate_logical_operand(
                ctx,
                child_options,
                operand_specs.get("operand") or operand_specs.get("child"),
            )
            node.add_child(child.node)
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

        node = LogicalNode(connector.upper())
        left = self._generate_logical_operand(ctx, child_options, operand_specs.get("left"))
        right = self._generate_logical_operand(ctx, child_options, operand_specs.get("right"))
        node.add_child(left.node)
        node.add_child(right.node)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

    def _atom(self, ctx, request: GenerationRequest) -> Generated:
        clause = request.options.get("clause", "where")
        atoms_key = self._config_key(clause, "atoms")
        atoms = ctx.spec.get(atoms_key, {"comparison": 1.0})
        atom = request.options.get("force_atom") or weighted_choice(ctx.rng, atoms, "comparison")
        if atom == "aggregate_comparison":
            return self._having_aggregate_comparison(ctx, request)
        if atom == "group_expression_comparison":
            return self._having_group_expression_comparison(ctx, request)
        if atom == "column_comparison":
            return self._column_comparison(ctx, request)
        if atom == "in_subquery":
            return self._in_subquery(ctx, request)
        if atom == "not_in_subquery":
            return self._in_subquery(ctx, request, negate=True)
        if atom == "any_all_subquery":
            return self._any_all_subquery(ctx, request)
        if atom == "exists_subquery":
            return self._exists_subquery(ctx, request)
        if atom == "not_exists_subquery":
            return self._exists_subquery(ctx, request, negate=True)
        if atom == "between":
            return self._between(ctx, request)
        if atom == "like":
            return self._like(ctx, request)
        if atom == "regexp":
            return self._regexp(ctx, request)
        if atom == "is_null":
            return self._is_null(ctx, request)
        return self._comparison(ctx, request)

    def _config_key(self, clause: str, name: str) -> str:
        if clause == "join_on":
            return f"join_on.{name}"
        if clause == "having":
            return f"having_bool.{name}"
        return f"bool_expr.{name}"

    def _connector_operand_specs(self, ctx, clause: str, connector: str) -> dict:
        specs = ctx.spec.get(self._config_key(clause, "connector_operands"), {}) or {}
        return (
            specs.get(connector)
            or specs.get(connector.lower())
            or specs.get(connector.upper())
            or {}
        )

    def _generate_logical_operand(self, ctx, child_options: dict, spec) -> Generated:
        if spec is None:
            return self.generate(ctx, GenerationRequest(child_options))
        if isinstance(spec, str):
            spec = {"kind": spec}

        kind = str(spec.get("kind", "bool_expr")).lower()
        if kind == "bool_expr":
            options = dict(child_options)
            if "max_depth" in spec:
                options["max_depth"] = spec["max_depth"]
            return self.generate(ctx, GenerationRequest(options))
        if kind in {"atom", "random_atom"}:
            options = dict(child_options)
            if spec.get("atom"):
                options["force_atom"] = spec["atom"]
            return self._atom(ctx, GenerationRequest(options))
        if kind in {"literal", "bool_literal", "boolean_literal"}:
            value = bool(spec.get("value", True))
            node = LiteralNode(value, "BOOLEAN")
            node.metadata["category"] = "boolean"
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")
        if kind in {"true", "bool_true"}:
            node = LiteralNode(True, "BOOLEAN")
            node.metadata["category"] = "boolean"
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")
        if kind in {"false", "bool_false"}:
            node = LiteralNode(False, "BOOLEAN")
            node.metadata["category"] = "boolean"
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")
        return self.generate(ctx, GenerationRequest(child_options))

    def _comparison(self, ctx, request: GenerationRequest) -> Generated:
        clause = request.options.get("clause", "where")
        left = None
        for _ in range(10):
            candidate = self._choose_column(ctx, request, orderable_only=True)
            if self._is_literal_safe(candidate):
                left = candidate
                break
        if left is None:
            return self._is_null(ctx, request)
        operators = ["=", "<>", ">", "<", ">=", "<="] if left.category == "numeric" else ["=", "<>"]
        node = ComparisonNode(ctx.rng.choice(operators))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(left), left.table_alias))
        value, data_type = literal_for_category(ctx.rng, left.category)
        literal = LiteralNode(value, data_type)
        literal.metadata["category"] = left.category
        node.add_child(literal)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={left.qualified_name})

    def _column_comparison(self, ctx, request: GenerationRequest) -> Generated:
        left_relation = request.options.get("left_relation")
        right_relation = request.options.get("right_relation")
        if not left_relation or not right_relation:
            return self._comparison(ctx, request)

        compatible_pairs = []
        for left_col in left_relation.columns:
            for right_col in right_relation.columns:
                if self._is_type_compatible(left_col.data_type, right_col.data_type):
                    compatible_pairs.append((left_col, right_col))
        if compatible_pairs:
            left, right = ctx.rng.choice(compatible_pairs)
        else:
            return self._comparison(ctx, request)

        operators = ["=", "<>"]
        if left.category == right.category == "numeric":
            operators.extend([">", "<", ">=", "<="])
        node = ComparisonNode(ctx.rng.choice(operators))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(left), left.table_alias))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(right), right.table_alias))
        return Generated(
            node=node,
            type_category="boolean",
            data_type="BOOLEAN",
            referenced_columns={left.qualified_name, right.qualified_name},
        )

    def _having_aggregate_comparison(self, ctx, request: GenerationRequest) -> Generated:
        select_node = request.options.get("select_node")
        if not select_node:
            return self._comparison(ctx, request)

        aggregate_exprs = [
            (expr, alias)
            for expr, alias in select_node.select_expressions
            if hasattr(expr, "contains_aggregate_function") and expr.contains_aggregate_function()
        ]
        if not aggregate_exprs:
            group_generated = self._having_group_expression_comparison(ctx, request, allow_fallback=False)
            return group_generated or self._comparison(ctx, request)

        expr, alias = ctx.rng.choice(aggregate_exprs)
        category = self._expr_category(expr)
        comparison_type = self._comparison_data_type(expr, category)
        alias_node = AliasReferenceNode(alias, comparison_type, category)
        if category == "any":
            node = ComparisonNode(ctx.rng.choice(["IS NULL", "IS NOT NULL"]))
            node.add_child(alias_node)
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

        operators = ["=", "<>", ">", "<", ">=", "<="] if category == "numeric" else ["=", "<>"]
        node = ComparisonNode(ctx.rng.choice(operators))
        node.add_child(alias_node)
        value, data_type = literal_for_category(ctx.rng, category, comparison_type)
        literal = LiteralNode(value, data_type)
        literal.metadata["category"] = category
        node.add_child(literal)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

    def _having_group_expression_comparison(self, ctx, request: GenerationRequest, allow_fallback: bool = True) -> Generated | None:
        select_node = request.options.get("select_node")
        group_by = getattr(select_node, "group_by_clause", None) if select_node else None
        group_expressions = list(getattr(group_by, "expressions", []) or [])
        if not group_expressions:
            return self._having_aggregate_comparison(ctx, request) if allow_fallback else None

        group_sqls = {expr.to_sql() for expr in group_expressions}
        candidates = [
            (expr, alias)
            for expr, alias in select_node.select_expressions
            if expr.to_sql() in group_sqls
        ]
        if not candidates:
            return self._having_aggregate_comparison(ctx, request) if allow_fallback else None

        expr, alias = ctx.rng.choice(candidates)
        category = self._expr_category(expr)
        comparison_type = self._comparison_data_type(expr, category)
        alias_node = AliasReferenceNode(alias, comparison_type, category)
        if category == "any":
            node = ComparisonNode(ctx.rng.choice(["IS NULL", "IS NOT NULL"]))
            node.add_child(alias_node)
            return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

        operators = ["=", "<>", ">", "<", ">=", "<="] if category == "numeric" else ["=", "<>"]
        node = ComparisonNode(ctx.rng.choice(operators))
        node.add_child(alias_node)
        value, data_type = literal_for_category(ctx.rng, category, comparison_type)
        literal = LiteralNode(value, data_type)
        literal.metadata["category"] = category
        node.add_child(literal)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

    def _is_null(self, ctx, request: GenerationRequest) -> Generated:
        symbol = self._choose_column(ctx, request)
        node = ComparisonNode(ctx.rng.choice(["IS NULL", "IS NOT NULL"]))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias))
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={symbol.qualified_name})

    def _in_subquery(self, ctx, request: GenerationRequest, negate: bool = False) -> Generated:
        if ctx.depth >= int(ctx.spec.get("subquery.max_depth", ctx.max_depth) or ctx.max_depth):
            return self._comparison(ctx, request)

        left = self._choose_column(ctx, request, orderable_only=True)
        subquery = self._single_column_subquery(ctx, left.category)
        node = ComparisonNode("NOT IN" if negate else "IN")
        node.add_child(ColumnReferenceNode(column_symbol_to_column(left), left.table_alias))
        node.add_child(SubqueryNode(subquery, ""))
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={left.qualified_name})

    def _any_all_subquery(self, ctx, request: GenerationRequest) -> Generated:
        if ctx.depth >= int(ctx.spec.get("subquery.max_depth", ctx.max_depth) or ctx.max_depth):
            return self._comparison(ctx, request)

        left = self._choose_column(ctx, request, orderable_only=True)
        subquery = self._single_column_subquery(ctx, left.category)
        operators = ["=", "<>"]
        if left.category == "numeric":
            operators.extend([">", "<", ">=", "<="])
        node = ComparisonNode(f"{ctx.rng.choice(operators)} {ctx.rng.choice(['ANY', 'ALL'])}")
        node.add_child(ColumnReferenceNode(column_symbol_to_column(left), left.table_alias))
        node.add_child(SubqueryNode(subquery, ""))
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={left.qualified_name})

    def _exists_subquery(self, ctx, request: GenerationRequest, negate: bool = False) -> Generated:
        if ctx.depth >= int(ctx.spec.get("subquery.max_depth", ctx.max_depth) or ctx.max_depth):
            return self._comparison(ctx, request)

        subquery = self._exists_select_subquery(ctx)
        node = ComparisonNode("NOT EXISTS" if negate else "EXISTS")
        node.add_child(SubqueryNode(subquery, ""))
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN")

    def _single_column_subquery(self, ctx, category: str) -> SelectNode:
        child_ctx = ctx.fork(depth=ctx.depth + 1)
        child_ctx.scope_resolver.push_scope()
        try:
            if self.from_generator:
                from_node = self.from_generator.generate(
                    child_ctx,
                    GenerationRequest({"config_prefix": "subquery.in_subquery.from"}),
                ).node
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
            projection = self._subquery_projection(child_ctx, "in_subquery", category)
            select_node.add_select_expression(projection.node, "col_1")
            if child_ctx.rng.random() < float(child_ctx.spec.get("subquery.in_subquery.where.enabled_prob", 0.0)):
                where_generated = self.generate(
                    child_ctx,
                    GenerationRequest(
                        {
                            "clause": "where",
                            "max_depth": child_ctx.spec.get("subquery.in_subquery.where.max_depth", 1),
                        }
                    ),
                )
                select_node.set_where_clause(where_generated.node)
            if (
                not projection.used_aggregate
                and child_ctx.rng.random() < float(child_ctx.spec.get("subquery.in_subquery.order_by.enabled_prob", 0.0))
            ):
                order_by = self._subquery_order_by(child_ctx)
                if order_by:
                    select_node.set_order_by_clause(order_by)
            if child_ctx.rng.random() < float(child_ctx.spec.get("subquery.in_subquery.limit.enabled_prob", 0.0)):
                limit_range = child_ctx.spec.get("subquery.in_subquery.limit.range", [1, 50])
                low, high = int(limit_range[0]), int(limit_range[1])
                select_node.set_limit_clause(LimitNode(child_ctx.rng.randint(low, high)))
            return select_node
        finally:
            child_ctx.scope_resolver.pop_scope()

    def _between(self, ctx, request: GenerationRequest) -> Generated:
        candidates = []
        for _ in range(10):
            symbol = self._choose_column(ctx, request, orderable_only=True)
            if symbol.category in {"numeric", "datetime"}:
                candidates.append(symbol)
        symbol = candidates[0] if candidates else self._choose_column(ctx, request, orderable_only=True)
        category = symbol.category if symbol.category in {"numeric", "datetime"} else "numeric"

        node = ComparisonNode(ctx.rng.choice(["BETWEEN", "NOT BETWEEN"]))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias))
        if category == "datetime":
            first = LiteralNode("2023-01-01 00:00:00", "DATETIME")
            second = LiteralNode("2023-12-31 23:59:59", "DATETIME")
        else:
            low = ctx.rng.randint(0, 50)
            high = low + ctx.rng.randint(1, 50)
            first = LiteralNode(low, "INT")
            second = LiteralNode(high, "INT")
        first.metadata["category"] = category
        second.metadata["category"] = category
        node.add_child(first)
        node.add_child(second)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={symbol.qualified_name})

    def _like(self, ctx, request: GenerationRequest) -> Generated:
        symbol = self._choose_string_column(ctx, request)
        node = ComparisonNode(ctx.rng.choice(["LIKE", "NOT LIKE"]))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias))
        pattern = ctx.rng.choice([
            f"sample_{ctx.rng.randint(1, 100)}",
            f"%sample_{ctx.rng.randint(1, 100)}",
            f"sample_{ctx.rng.randint(1, 100)}%",
            f"%sample_{ctx.rng.randint(1, 100)}%",
        ])
        literal = LiteralNode(pattern, "STRING")
        literal.metadata["category"] = "string"
        node.add_child(literal)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={symbol.qualified_name})

    def _regexp(self, ctx, request: GenerationRequest) -> Generated:
        symbol = self._choose_string_column(ctx, request)
        node = ComparisonNode(ctx.rng.choice(["REGEXP", "NOT REGEXP", "RLIKE"]))
        node.add_child(ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias))
        pattern = ctx.rng.choice([
            r"^sample_[0-9]+$",
            r"[a-zA-Z0-9]{3,12}",
            r".*[0-9]{2}.*",
        ])
        literal = LiteralNode(pattern, "STRING")
        literal.metadata["category"] = "string"
        node.add_child(literal)
        return Generated(node=node, type_category="boolean", data_type="BOOLEAN", referenced_columns={symbol.qualified_name})

    def _choose_string_column(self, ctx, request: GenerationRequest):
        try:
            return ctx.dependency_resolver.choose_column(
                ctx,
                ColumnRequest(category="string", clause=request.options.get("clause", "where"), orderable_only=True),
            )
        except Exception:
            return self._choose_column(ctx, request, orderable_only=True)

    def _exists_select_subquery(self, ctx) -> SelectNode:
        child_ctx = ctx.fork(depth=ctx.depth + 1)
        child_ctx.scope_resolver.push_scope()
        try:
            if self.from_generator:
                from_node = self.from_generator.generate(
                    child_ctx,
                    GenerationRequest({"config_prefix": "subquery.exists_subquery.from"}),
                ).node
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
            projection = self._subquery_projection(child_ctx, "exists_subquery", None)
            select_node.add_select_expression(projection.node, "col_1")
            if child_ctx.rng.random() < float(child_ctx.spec.get("subquery.exists_subquery.where.enabled_prob", 0.0)):
                where_generated = self.generate(
                    child_ctx,
                    GenerationRequest(
                        {
                            "clause": "where",
                            "max_depth": child_ctx.spec.get("subquery.exists_subquery.where.max_depth", 1),
                        }
                    ),
                )
                select_node.set_where_clause(where_generated.node)
            if child_ctx.rng.random() < float(child_ctx.spec.get("subquery.exists_subquery.order_by.enabled_prob", 0.0)):
                order_by = self._subquery_order_by(child_ctx)
                if order_by:
                    select_node.set_order_by_clause(order_by)
            if child_ctx.rng.random() < float(child_ctx.spec.get("subquery.exists_subquery.limit.enabled_prob", 0.0)):
                limit_range = child_ctx.spec.get("subquery.exists_subquery.limit.range", [1, 50])
                low, high = int(limit_range[0]), int(limit_range[1])
                select_node.set_limit_clause(LimitNode(child_ctx.rng.randint(low, high)))
            return select_node
        finally:
            child_ctx.scope_resolver.pop_scope()

    def _subquery_projection(self, ctx, subquery_kind: str, expected_category=None) -> Generated:
        projection_kinds = ctx.spec.get(
            f"subquery.{subquery_kind}.projection.expr_kinds",
            ["literal"] if subquery_kind == "exists_subquery" else ["column"],
        )
        if isinstance(projection_kinds, dict):
            projection_kinds = list(projection_kinds.keys())
        if self.value_expr_generator:
            try:
                return self.value_expr_generator.generate(
                    ctx,
                    GenerationRequest(
                        {
                            "expected_category": expected_category,
                            "allowed_kinds": projection_kinds,
                            "clause": "select",
                        }
                    ),
                )
            except Exception:
                pass
        if "column" in projection_kinds:
            try:
                symbol = ctx.dependency_resolver.choose_column(
                    ctx,
                    ColumnRequest(category=expected_category, clause="select", orderable_only=expected_category is not None),
                )
                return Generated(
                    node=ColumnReferenceNode(column_symbol_to_column(symbol), symbol.table_alias),
                    type_category=symbol.category,
                    data_type=symbol.data_type,
                    referenced_columns={symbol.qualified_name},
                )
            except Exception:
                pass
        literal = LiteralNode(1, "INT")
        literal.metadata["category"] = "numeric"
        return Generated(node=literal, type_category="numeric", data_type="INT")

    def _subquery_order_by(self, ctx):
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

    def _choose_column(self, ctx, request: GenerationRequest, orderable_only: bool = False):
        relations = [
            relation for relation in (
                request.options.get("left_relation"),
                request.options.get("right_relation"),
            )
            if relation is not None
        ]
        if relations:
            columns = []
            for relation in relations:
                columns.extend(relation.columns)
            if orderable_only:
                columns = [
                    col for col in columns
                    if col.category in ctx.dependency_resolver.ORDERABLE_CATEGORIES
                ]
            if columns:
                return ctx.rng.choice(columns)
        return ctx.dependency_resolver.choose_column(
            ctx,
            ColumnRequest(
                clause=request.options.get("clause", "where"),
                orderable_only=orderable_only,
            ),
        )

    def _base_type(self, data_type: str) -> str:
        return (data_type or "").split("(", 1)[0].upper()

    def _is_type_compatible(self, left_type: str, right_type: str) -> bool:
        left = self._base_type(left_type)
        right = self._base_type(right_type)
        if left == right:
            return True
        if left in self.NUMERIC_TYPES and right in self.NUMERIC_TYPES:
            return True
        if left in self.STRING_TYPES and right in self.STRING_TYPES:
            return True
        if left in self.DATETIME_TYPES and right in self.DATETIME_TYPES:
            return True
        if left in self.BOOLEAN_TYPES and right in self.BOOLEAN_TYPES:
            return True
        return False

    def _is_literal_safe(self, symbol) -> bool:
        base = self._base_type(symbol.data_type)
        return (
            base in self.NUMERIC_TYPES
            or base in self.STRING_TYPES
            or base in self.DATETIME_TYPES
            or base in self.BOOLEAN_TYPES
        )

    def _expr_category(self, expr) -> str:
        metadata = getattr(expr, "metadata", {}) or {}
        category = metadata.get("category")
        if category:
            return category
        data_type = self._expr_data_type(expr)
        base = self._base_type(data_type)
        if base in self.NUMERIC_TYPES:
            return "numeric"
        if base in self.STRING_TYPES:
            return "string"
        if base in self.DATETIME_TYPES:
            return "datetime"
        if base in self.BOOLEAN_TYPES:
            return "boolean"
        return "any"

    def _expr_data_type(self, expr) -> str:
        metadata = getattr(expr, "metadata", {}) or {}
        return metadata.get("return_type") or metadata.get("data_type") or getattr(expr, "data_type", "")

    def _comparison_data_type(self, expr, category: str) -> str:
        if category == "string":
            return "STRING"
        if category == "numeric":
            data_type = self._expr_data_type(expr)
            return data_type if self._base_type(data_type) in self.NUMERIC_TYPES else "INT"
        if category == "datetime":
            data_type = self._expr_data_type(expr)
            return data_type if self._base_type(data_type) in self.DATETIME_TYPES else "DATE"
        if category == "boolean":
            return "BOOLEAN"
        return self._expr_data_type(expr)
