"""LIMIT generation."""

from ast_nodes import LimitNode

from ..types import Generated, GenerationRequest
from .utils import rand_range


class LimitGenerator:
    """Generate a LIMIT clause."""

    def generate(self, ctx, request: GenerationRequest | None = None) -> Generated:
        limit_range = ctx.spec.get("select.limit.range", [1, 100])
        return Generated(node=LimitNode(rand_range(ctx.rng, limit_range, 1, 100)))
