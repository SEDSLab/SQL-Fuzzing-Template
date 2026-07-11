"""Generator registry for grammar symbols."""

from typing import Dict


class GeneratorRegistry:
    """Map grammar/module names to generator instances."""

    def __init__(self):
        self._generators: Dict[str, object] = {}

    def register(self, name: str, generator: object) -> None:
        self._generators[name] = generator

    def resolve(self, name: str) -> object:
        if name not in self._generators:
            raise KeyError(f"No configurable SQL generator registered for {name!r}")
        return self._generators[name]

