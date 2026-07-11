"""SELECT projection generation."""

from ..types import Generated, GenerationRequest
from .utils import rand_range


class ProjectionGenerator:
    """Generate SELECT list expressions and register output columns."""

    def __init__(self, value_expr_generator):
        self.value_expr_generator = value_expr_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        request = request or GenerationRequest()
        requested_count = request.options.get("count")
        count_cfg = ctx.spec.get("select.projection.count", [1, 4])
        count = int(requested_count) if requested_count is not None else rand_range(ctx.rng, count_cfg, 1, 4)
        categories = request.options.get("categories") or []
        output_columns = []
        nodes = []
        for idx in range(count):
            expected_category = categories[idx] if idx < len(categories) else None
            generated = self.value_expr_generator.generate(
                ctx,
                GenerationRequest(
                    {
                        "clause": "select",
                        "expected_category": expected_category,
                    }
                ),
            )
            alias = f"col_{idx + 1}"
            symbol = ctx.dependency_resolver.register_select_expr(ctx, generated.node, alias, generated)
            output_columns.append(symbol)
            nodes.append((generated.node, alias))
            if generated.used_aggregate:
                ctx.flags["aggregate_used"] = True
            if generated.used_window:
                ctx.flags["window_used"] = True
        return Generated(node=nodes, output_columns=output_columns)
