"""Grammar execution facade for configurable SQL generation."""

from .types import GenerationRequest


class GrammarExecutor:
    """Resolve a root grammar symbol and invoke its registered generator."""

    def __init__(self, spec, registry):
        self.spec = spec
        self.registry = registry

    def generate(self, ctx, symbol: str | None = None):
        root = symbol or self.spec.get("query.root", "select")
        generator = self.registry.resolve(root)
        return generator.generate(ctx, GenerationRequest())

