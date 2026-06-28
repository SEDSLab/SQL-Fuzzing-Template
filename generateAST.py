"""Utilities for loading SQL text and converting it to sqlglot AST nodes."""

import os

import sqlglot

from data_structures.db_dialect import get_current_dialect


def _get_sqlglot_dialect_name() -> str:
    """Map the active project dialect to a sqlglot dialect name."""
    dialect = get_current_dialect()
    if dialect and dialect.name.upper() == "POSTGRESQL":
        return "postgres"
    return "mysql"


class Change:
    """Read SQL statements from file and parse individual statements into AST."""

    def __init__(self, file_path: str = "./generated_sql/seedQuery.sql"):
        self.file_path = file_path
        self.seedqueries = self.get_queries()

    def get_queries(self):
        """Load non-empty SQL lines from `self.file_path`."""
        queries = []
        try:
            abs_path = os.path.abspath(self.file_path)
            with open(abs_path, "r", encoding="utf-8") as f:
                for line in f:
                    sql = line.strip()
                    if sql:
                        queries.append(sql)
            return queries
        except Exception as e:
            print(f"Error reading SQL file: {e}")
            return []

    def getAST(self, query):
        """Parse a SQL string into a sqlglot AST node."""
        try:
            ast = sqlglot.parse_one(query, read=_get_sqlglot_dialect_name())
            print(ast)
            return ast
        except Exception as e:
            print(f"Failed to parse query: {e}")
            return None

    def ASTChange(self, query):
        """Compatibility wrapper kept for existing call sites."""
        return self.getAST(query)
