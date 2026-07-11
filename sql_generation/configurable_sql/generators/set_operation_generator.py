"""Set operation generation for configurable SQL."""

from ast_nodes import SetOperationNode

from ..types import Generated, GenerationRequest
from .utils import rand_range


class SetOperationGenerator:
    """Generate UNION/UNION ALL/EXCEPT/INTERSECT queries."""

    def __init__(self, select_generator):
        self.select_generator = select_generator

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        operations = self._allowed_operations(ctx)
        operation = ctx.rng.choice(operations)
        node = SetOperationNode(operation)

        query_count = rand_range(ctx.rng, ctx.spec.get("set_operation.query_count", [2, 2]), 2, 2)
        projection_count = rand_range(ctx.rng, ctx.spec.get("set_operation.projection_count", [1, 3]), 1, 3)
        categories = self._projection_categories(ctx, projection_count)
        mixed_operations = bool(ctx.spec.get("set_operation.mixed_operations", False))

        for idx in range(query_count):
            generated = self.select_generator.generate(
                ctx,
                GenerationRequest(
                    {
                        "allow_cte": False,
                        "for_set_operation": True,
                        "projection_count": projection_count,
                        "projection_categories": categories,
                    }
                ),
            )
            if idx == 0 or not mixed_operations:
                node.add_query(generated.node)
            else:
                node.add_query(generated.node, ctx.rng.choice(operations))

        return Generated(node=node)

    def _allowed_operations(self, ctx):
        configured = list(ctx.spec.get("set_operation.operation_types", ["UNION", "UNION ALL"]))
        return [operation.upper() for operation in configured] or ["UNION ALL"]

    def _projection_categories(self, ctx, count: int):
        configured = ctx.spec.get("set_operation.categories", ["numeric", "string", "datetime"])
        if not configured:
            configured = ["numeric"]
        return [ctx.rng.choice(configured) for _ in range(count)]
