"""FROM clause generation for configurable SQL."""

from ast_nodes import FromNode, SubqueryNode
from data_structures.table import Table

from ..types import Generated, GenerationRequest
from .utils import next_alias, weighted_choice


class FromGenerator:
    """Generate table sources and simple joins."""

    def __init__(self, select_generator=None, on_condition_generator=None):
        self.select_generator = select_generator
        self.on_condition_generator = on_condition_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        if not ctx.tables:
            raise ValueError("No tables available for configurable SQL generation")

        from_node = FromNode()
        prefix = (request.options.get("config_prefix") if request else None) or "select.from"
        source_kinds = self._cfg(ctx, prefix, "source_kinds", {"table": 1.0})
        source_kind = weighted_choice(ctx.rng, source_kinds, "table")

        if source_kind == "cte" and self._has_ctes(ctx):
            first_table = ctx.rng.choice(self._cte_tables(ctx))
            first_alias = next_alias(ctx)
            from_node.add_table(first_table, first_alias)
            first_relation = ctx.scope_resolver.register_table(first_table, first_alias)
        elif source_kind == "derived_table" and self._can_generate_derived(ctx):
            first_alias = next_alias(ctx, "sq")
            subquery_node, first_relation = self._derived_table(ctx, first_alias)
            from_node.add_table(subquery_node, first_alias)
            first_table = None
        else:
            first_table = ctx.rng.choice(self._base_tables(ctx))
            first_alias = next_alias(ctx)
            from_node.add_table(first_table, first_alias)
            first_relation = ctx.scope_resolver.register_table(first_table, first_alias)

        max_joins = int(self._cfg(ctx, prefix, "max_joins", 1) or 0)

        if source_kind == "join" and max_joins > 0:
            join_types = self._cfg(ctx, prefix, "join_types", ["INNER"])
            join_count = ctx.rng.randint(1, max_joins)
            used_base_tables = {id(first_table)} if isinstance(first_table, Table) else set()
            joined_relations = [first_relation]
            for _ in range(join_count):
                join_source, join_alias, join_relation = self._join_source(ctx, used_base_tables, prefix)
                left_relation = ctx.rng.choice(joined_relations)
                condition = self._join_condition(ctx, left_relation, join_relation)
                join_type = ctx.rng.choice(join_types) if join_types else "INNER"
                from_node.add_join(join_type, join_source, join_alias, condition)
                joined_relations.append(join_relation)
                if isinstance(join_source, Table):
                    used_base_tables.add(id(join_source))

        return Generated(node=from_node)

    def _can_generate_derived(self, ctx) -> bool:
        max_depth = int(ctx.spec.get("subquery.max_depth", ctx.max_depth) or ctx.max_depth)
        return self.select_generator is not None and ctx.depth < max_depth

    def _derived_table(self, ctx, alias: str):
        child_ctx = ctx.fork(depth=ctx.depth + 1)
        generated = self.select_generator.generate(child_ctx, GenerationRequest({"as_subquery": True}))
        subquery_node = SubqueryNode(generated.node, alias)
        relation = ctx.scope_resolver.register_derived(
            alias=alias,
            source_name=alias,
            source=subquery_node,
            columns=generated.output_columns,
        )
        return subquery_node, relation

    def _join_source(self, ctx, used_base_tables, prefix: str):
        join_source_kinds = self._cfg(ctx, prefix, "join_source_kinds", {"table": 1.0})
        join_source_kind = weighted_choice(ctx.rng, join_source_kinds, "table")
        if join_source_kind == "cte" and self._has_ctes(ctx):
            join_table = ctx.rng.choice(self._cte_tables(ctx))
            join_alias = next_alias(ctx)
            join_relation = ctx.scope_resolver.register_table(join_table, join_alias)
            return join_table, join_alias, join_relation
        if join_source_kind == "derived_table" and self._can_generate_derived(ctx):
            join_alias = next_alias(ctx, "sq")
            join_source, join_relation = self._derived_table(ctx, join_alias)
            return join_source, join_alias, join_relation

        candidates = self._base_tables(ctx)
        unused_candidates = [table for table in candidates if id(table) not in used_base_tables]
        if unused_candidates:
            candidates = unused_candidates
        join_table = ctx.rng.choice(candidates)
        join_alias = next_alias(ctx)
        join_relation = ctx.scope_resolver.register_table(join_table, join_alias)
        return join_table, join_alias, join_relation

    def _join_condition(self, ctx, left_relation, right_relation):
        if not self.on_condition_generator:
            raise ValueError("FromGenerator requires an ON condition generator for JOIN generation")
        return self.on_condition_generator.generate(
            ctx,
            GenerationRequest(
                {
                    "clause": "join_on",
                    "left_relation": left_relation,
                    "right_relation": right_relation,
                    "max_depth": ctx.spec.get("join_on.max_depth", 2),
                }
            ),
        ).node

    def _base_tables(self, ctx):
        return list(ctx.tables)

    def _cte_tables(self, ctx):
        return list(ctx.flags.get("cte_tables", []))

    def _has_ctes(self, ctx) -> bool:
        return bool(self._cte_tables(ctx))

    def _cfg(self, ctx, prefix: str, name: str, default):
        configured = ctx.spec.get(f"{prefix}.{name}", None)
        if configured is not None:
            return configured
        return ctx.spec.get(f"select.from.{name}", default)
