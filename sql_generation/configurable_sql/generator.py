"""Top-level configurable SQL generator facade."""

import random
from copy import deepcopy
from typing import Any, Mapping, Optional

from data_structures.db_dialect import get_current_dialect

from .context import GenContext
from .grammar_executor import GrammarExecutor
from .grammar_spec import GrammarSpec, default_select_spec
from .registry import GeneratorRegistry
from .resolvers import ColumnDependencyResolver, ScopeResolver
from .semantic_validator import SemanticValidator
from .generators import (
    BoolExprGenerator,
    FromGenerator,
    LimitGenerator,
    OrderByGenerator,
    ProjectionGenerator,
    SelectGenerator,
    SetOperationGenerator,
    ValueExprGenerator,
    WindowFunctionGenerator,
)


_PROFILE_META_KEYS = {"name", "weight", "description", "overrides"}


class ConfigurableSqlGenerator:
    """Generate SELECT ASTs from a structured grammar profile."""

    def __init__(self, spec: Optional[GrammarSpec] = None):
        self.spec = spec or default_select_spec()
        self.registry = self._build_registry()
        self.executor = GrammarExecutor(self.spec, self.registry)
        self.validator = SemanticValidator()

    def generate(self, ctx: GenContext):
        if ctx.scope_resolver is None:
            ctx.scope_resolver = ScopeResolver()
        if ctx.dependency_resolver is None:
            ctx.dependency_resolver = ColumnDependencyResolver()
        ctx.spec = self.spec
        generated = self.executor.generate(ctx)
        errors = self.validator.validate(generated.node, ctx)
        if errors:
            generated.node = self.validator.repair(generated.node, errors, ctx)
        return generated.node

    def _build_registry(self) -> GeneratorRegistry:
        registry = GeneratorRegistry()
        window_function = WindowFunctionGenerator()
        value_expr = ValueExprGenerator(window_function_generator=window_function)
        bool_expr = BoolExprGenerator()
        from_generator = FromGenerator(on_condition_generator=bool_expr)
        bool_expr.from_generator = from_generator
        bool_expr.value_expr_generator = value_expr
        value_expr.from_generator = from_generator
        value_expr.bool_expr_generator = bool_expr
        projection = ProjectionGenerator(value_expr)
        order_by = OrderByGenerator(value_expr)
        limit = LimitGenerator()
        select = SelectGenerator(from_generator, projection, bool_expr, order_by, limit)
        from_generator.select_generator = select
        set_operation = SetOperationGenerator(select)

        registry.register("select", select)
        registry.register("set_operation", set_operation)
        registry.register("from", from_generator)
        registry.register("projection", projection)
        registry.register("value_expr", value_expr)
        registry.register("window_function", window_function)
        registry.register("bool_expr", bool_expr)
        registry.register("order_by", order_by)
        registry.register("limit", limit)
        return registry


def generate_configurable_sql(
    tables,
    functions,
    grammar_overrides: Optional[Mapping] = None,
    seed: Optional[int] = None,
    return_ast: bool = False,
):
    """Generate SQL using the configurable SELECT framework."""

    rng = random.Random(seed)
    spec = default_select_spec()
    if grammar_overrides:
        spec = spec.merge(_resolve_profile_overrides(grammar_overrides, rng))
    ctx = GenContext(
        tables=tables,
        functions=functions,
        dialect=get_current_dialect(),
        spec=spec,
        rng=rng,
        max_depth=spec.get("query.max_depth", 3),
        scope_resolver=ScopeResolver(),
        dependency_resolver=ColumnDependencyResolver(),
    )
    node = ConfigurableSqlGenerator(spec).generate(ctx)
    return node if return_ast else node.to_sql()


def _resolve_profile_overrides(grammar_overrides: Mapping[str, Any], rng) -> Mapping[str, Any]:
    """Apply an optional weighted profile from a YAML grammar mapping."""

    base = {
        key: deepcopy(value)
        for key, value in grammar_overrides.items()
        if key not in {"profiles", "profile"}
    }
    profiles = grammar_overrides.get("profiles")
    if not profiles:
        return base

    selected_name, selected_profile = _choose_profile(
        profiles,
        rng,
        explicit_name=grammar_overrides.get("profile"),
    )
    profile_overrides = _profile_overrides(selected_profile)
    if not profile_overrides:
        return base
    return GrammarSpec(base).merge(profile_overrides).rules


def _choose_profile(profiles, rng, explicit_name=None):
    entries = _profile_entries(profiles)
    if not entries:
        raise ValueError("profiles is configured but no profile entries were found")

    if explicit_name:
        for name, profile in entries:
            if name == explicit_name:
                return name, profile
        raise ValueError(f"Unknown grammar profile: {explicit_name}")

    total = sum(max(float(_profile_weight(profile)), 0.0) for _, profile in entries)
    if total <= 0:
        return entries[0]

    pick = rng.random() * total
    running = 0.0
    for name, profile in entries:
        running += max(float(_profile_weight(profile)), 0.0)
        if pick <= running:
            return name, profile
    return entries[-1]


def _profile_entries(profiles):
    if isinstance(profiles, Mapping):
        return [(str(name), profile) for name, profile in profiles.items()]
    if isinstance(profiles, list):
        entries = []
        for index, profile in enumerate(profiles):
            if not isinstance(profile, Mapping):
                continue
            name = str(profile.get("name", f"profile_{index + 1}"))
            entries.append((name, profile))
        return entries
    return []


def _profile_weight(profile) -> float:
    if isinstance(profile, Mapping):
        return float(profile.get("weight", 1.0))
    return 1.0


def _profile_overrides(profile) -> Mapping[str, Any]:
    if not isinstance(profile, Mapping):
        return {}
    if isinstance(profile.get("overrides"), Mapping):
        return deepcopy(profile["overrides"])
    return {
        key: deepcopy(value)
        for key, value in profile.items()
        if key not in _PROFILE_META_KEYS
    }
