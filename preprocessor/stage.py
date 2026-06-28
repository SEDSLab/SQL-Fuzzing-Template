"""Preprocess generated seed SQL before downstream mutation stages."""

import os
from typing import Callable, Iterable, List, Optional, Sequence

from data_structures.db_dialect import get_current_dialect
from generateAST import Change
from rules_loader import discover_rule_functions


def _get_sqlglot_dialect_name() -> str:
    """Map the active project dialect to a sqlglot dialect name."""
    dialect = get_current_dialect()
    if dialect and dialect.name.upper() == "POSTGRESQL":
        return "postgres"
    return "mysql"


class Preprocessor:
    """Normalize generated SQL and provide a hook for future rewrite rules."""

    def __init__(
        self,
        input_path: str = "./generated_sql/seedQuery.sql",
        output_path: str = "./generated_sql/preprocessed_seedQuery.sql",
        rules_dir: Optional[str] = None,
        auto_load_rules: bool = True,
    ) -> None:
        self.input_path = input_path
        self.output_path = output_path
        self.change = Change(file_path=input_path)
        self.rules_dir = rules_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "RIFT",
            "rules",
        )
        self._rules: List[Callable] = []
        if auto_load_rules:
            self.load_rules_from_directory(self.rules_dir)

    def register_rule(self, rule) -> None:
        """Register a callable rule that transforms a parsed sqlglot expression."""
        self._rules.append(rule)

    def load_rules_from_directory(self, rules_dir: Optional[str] = None) -> int:
        """Auto-discover preprocess rules from a rules directory."""
        target_dir = rules_dir or self.rules_dir
        discovered = discover_rule_functions(target_dir)
        self._register_unique_rules(discovered)
        return len(discovered)

    def seed_query_iterator(self) -> Iterable[str]:
        """Yield non-empty SQL statements from `self.input_path`."""
        try:
            abs_path = os.path.abspath(self.input_path)
            with open(abs_path, "r", encoding="utf-8") as file_obj:
                for line in file_obj:
                    sql = line.strip()
                    if sql:
                        yield sql
        except OSError as exc:
            print(f"Error reading seed query file: {exc}")

    def preprocess(self, batch_size: int = 100, max_queries=None) -> str:
        """Normalize parseable queries and write them to `self.output_path`."""
        processed_count = 0
        normalized_queries: List[str] = []

        for query in self.seed_query_iterator():
            if max_queries is not None and processed_count >= max_queries:
                break

            processed_count += 1
            if processed_count % batch_size == 0:
                print(f"Preprocessed {processed_count} seed queries")

            try:
                parsed = self.change.ASTChange(query)
                if parsed is None:
                    continue

                rewritten = self._apply_rules(parsed)
                normalized_queries.append(
                    rewritten.sql(dialect=_get_sqlglot_dialect_name())
                )
            except Exception as exc:
                print(f"Error preprocessing query: {exc}")
                continue

        self._write_queries(normalized_queries)
        print(
            f"\nSeed query preprocessing complete, kept {len(normalized_queries)} queries"
        )
        return self.output_path

    def presolve(self, batch_size: int = 100, max_queries=None) -> str:
        """Backward-compatible alias for `preprocess`."""
        return self.preprocess(batch_size=batch_size, max_queries=max_queries)

    def _apply_rules(self, expression):
        """Apply registered preprocess rules in order."""
        current_expression = expression
        for rule in self._rules:
            current_expression = rule(current_expression)
            if current_expression is None:
                break
        return current_expression or expression

    def _register_unique_rules(self, rules: Sequence[Callable]) -> None:
        """Register rules while avoiding duplicates."""
        existing = {(rule.__module__, rule.__name__) for rule in self._rules}
        for rule in rules:
            identity = (rule.__module__, rule.__name__)
            if identity in existing:
                continue
            self._rules.append(rule)
            existing.add(identity)

    def _write_queries(self, queries: Sequence[str]) -> None:
        """Rewrite the output file with normalized statements."""
        abs_path = os.path.abspath(self.output_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as file_obj:
            for query in queries:
                file_obj.write(query)
                file_obj.write("\n")
