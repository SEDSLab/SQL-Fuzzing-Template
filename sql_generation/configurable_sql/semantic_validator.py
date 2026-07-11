"""Lightweight semantic validation facade for generated ASTs."""


class SemanticValidator:
    """Run existing AST validation hooks as a compatibility layer."""

    def validate(self, node, ctx=None):
        if hasattr(node, "validate_all_columns"):
            valid, errors = node.validate_all_columns()
            return [] if valid else errors
        return []

    def repair(self, node, errors=None, ctx=None):
        if errors and hasattr(node, "repair_invalid_columns"):
            node.repair_invalid_columns()
        return node

