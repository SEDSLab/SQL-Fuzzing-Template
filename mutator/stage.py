"""Mutate preprocessed SQL by applying one mutation rule at a time."""

import copy
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


class MutatorStage:
    """Generate one mutated query per registered rule."""

    def __init__(
        self,
        input_path: str = "./generated_sql/preprocessed_seedQuery.sql",
        output_path: str = "./generated_sql/mutated_queries.sql",
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
        """Register a callable mutation rule."""
        self._rules.append(rule)

    def has_rules(self) -> bool:
        """Return whether any mutation rules were registered."""
        return bool(self._rules)

    def load_rules_from_directory(self, rules_dir: Optional[str] = None) -> int:
        """Auto-discover mutation rules from a rules directory."""
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
            print(f"Error reading preprocessed query file: {exc}")

    def mutate(self, batch_size: int = 100, max_queries=None) -> str:
        """Apply each mutation rule independently and write all mutated queries."""
        processed_count = 0
        mutated_queries: List[str] = []

        for query in self.seed_query_iterator():
            if max_queries is not None and processed_count >= max_queries:
                break

            processed_count += 1
            if processed_count % batch_size == 0:
                print(f"Mutated {processed_count} queries")

            try:
                parsed = self.change.ASTChange(query)
                if parsed is None:
                    continue

                for rule in self._rules:
                    mutated = self._apply_rule(parsed, rule)
                    if mutated is None:
                        continue
                    mutated_queries.append(
                        mutated.sql(dialect=_get_sqlglot_dialect_name())
                    )
            except Exception as exc:
                print(f"Error mutating query: {exc}")
                continue

        self._write_queries(mutated_queries)
        print(f"\nMutation complete, kept {len(mutated_queries)} mutated queries")
        return self.output_path

    def _apply_rule(self, expression, rule):
        """Apply a single rule to a deep copy of the parsed expression."""
        expression_copy = copy.deepcopy(expression)
        original_sql = expression_copy.sql(dialect=_get_sqlglot_dialect_name())
        mutated_expression = rule(expression_copy)
        candidate_expression = mutated_expression or expression_copy
        candidate_sql = candidate_expression.sql(dialect=_get_sqlglot_dialect_name())
        if candidate_sql == original_sql:
            return None
        return candidate_expression

    def _write_queries(self, queries: Sequence[str]) -> None:
        """Rewrite the output file with mutated statements."""
        abs_path = os.path.abspath(self.output_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as file_obj:
            for query in queries:
                file_obj.write(query)
                file_obj.write("\n")

    def _register_unique_rules(self, rules: Sequence[Callable]) -> None:
        """Register rules while avoiding duplicates."""
        existing = {(rule.__module__, rule.__name__) for rule in self._rules}
        for rule in rules:
            identity = (rule.__module__, rule.__name__)
            if identity in existing:
                continue
            self._rules.append(rule)
            existing.add(identity)
