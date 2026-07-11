"""ORDER BY generation."""

from ast_nodes import OrderByNode

from ..types import GenerationRequest, Generated


class OrderByGenerator:
    """Generate ORDER BY from visible orderable columns."""

    def __init__(self, value_expr_generator):
        self.value_expr_generator = value_expr_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        max_columns = int(ctx.spec.get("select.order_by.max_columns", 2) or 1)
        count = ctx.rng.randint(1, max(1, max_columns))
        node = OrderByNode()
        for _ in range(count):
            generated = self.value_expr_generator.generate(
                ctx,
                GenerationRequest({"clause": "order_by", "allowed_kinds": ["column"]}),
            )
            node.add_expression(generated.node, ctx.rng.choice(["ASC", "DESC"]))
        return Generated(node=node)
