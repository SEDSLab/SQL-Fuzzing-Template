"""Generate configurable SQL batches and optionally validate execution."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from data_structures.db_dialect import get_current_dialect, set_dialect
from generate_random_sql import (
    create_sample_functions,
    create_sample_tables,
    generate_configurable_sql,
    generate_create_table_sql,
    generate_insert_sql,
)
from sql_generation.random_sql.io_utils import generate_index_sqls, save_sql_to_file
from pipeline.preprocess_validator import execute_sql_file, validate_preprocessed_sql_file


def _load_grammar(path: str) -> Dict:
    suffix = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as file_obj:
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except Exception as exc:
                raise RuntimeError("PyYAML is required to load YAML grammar files") from exc
            return yaml.safe_load(file_obj) or {}
        return json.load(file_obj)


def _generate_primary_keys(tables, rows_per_table: int) -> Dict[str, List[int]]:
    primary_keys = {}
    for table in tables:
        values = set()
        while len(values) < rows_per_table:
            values.add(random.randint(1, 10000))
        primary_keys[table.name] = list(values)
    return primary_keys


def _table_insert_order(tables):
    table_by_name = {table.name: table for table in tables}
    visited = set()
    ordered = []

    def visit(table):
        if table.name in visited:
            return
        visited.add(table.name)
        for fk in table.foreign_keys:
            ref_table = table_by_name.get(fk["ref_table"])
            if ref_table:
                visit(ref_table)
        ordered.append(table)

    for table in tables:
        visit(table)
    return ordered


def _write_schema(tables, output_dir: str, database_name: str, rows_per_table: int) -> str:
    create_sqls = [generate_create_table_sql(table) for table in tables]
    primary_keys = _generate_primary_keys(tables, rows_per_table)
    insert_sqls = [
        generate_insert_sql(
            table,
            num_rows=rows_per_table,
            existing_primary_keys=primary_keys,
            primary_key_values=primary_keys[table.name],
        )
        for table in _table_insert_order(tables)
    ]
    index_sqls = generate_index_sqls(tables, get_current_dialect())
    schema_sql = "\n\n".join(create_sqls + insert_sqls + index_sqls)
    return save_sql_to_file(
        schema_sql,
        output_dir=output_dir,
        file_type="schema",
        database_name=database_name,
    )


def _generate_queries(tables, functions, grammar, count: int, seed: int):
    queries = []
    attempts = 0
    max_attempts = count * 20
    while len(queries) < count and attempts < max_attempts:
        attempts += 1
        try:
            ast = generate_configurable_sql(
                tables,
                functions,
                grammar_overrides=grammar,
                seed=seed + attempts,
                return_ast=True,
            )
            if hasattr(ast, "validate_all_columns"):
                valid, _ = ast.validate_all_columns()
                if not valid:
                    continue
            sql = ast.to_sql().strip()
            if sql:
                queries.append(sql)
        except Exception:
            continue
    if len(queries) < count:
        raise RuntimeError(f"Generated only {len(queries)}/{count} valid SQL statements")
    return queries


def _write_queries(queries, output_dir: str, database_name: str) -> str:
    query_sql = "\n".join(queries)
    return save_sql_to_file(
        query_sql,
        output_dir=output_dir,
        file_type="query",
        database_name=database_name,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grammar", default="grammars/with_join_aggregate.yaml")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output-dir", default="generated_sql")
    parser.add_argument("--database", default="test")
    parser.add_argument("--dialect", default="mysql")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=13306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="123456")
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument("--rows-per-table", type=int, default=20)
    parser.add_argument("--skip-execute", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    set_dialect(args.dialect)

    grammar = _load_grammar(args.grammar)
    tables = create_sample_tables()
    functions = create_sample_functions()
    os.makedirs(args.output_dir, exist_ok=True)

    schema_path = _write_schema(tables, args.output_dir, args.database, args.rows_per_table)
    queries = _generate_queries(tables, functions, grammar, args.count, args.seed)
    query_path = _write_queries(queries, args.output_dir, args.database)

    print(f"grammar={os.path.abspath(args.grammar)}")
    print(f"schema={os.path.abspath(schema_path)}")
    print(f"queries={os.path.abspath(query_path)}")
    print(f"generated={len(queries)}")

    if args.skip_execute:
        print("execution=skipped")
        return

    db_config = {
        "host": args.host,
        "port": args.port,
        "database": args.database,
        "user": args.user,
        "password": args.password,
        "dialect": args.dialect.upper(),
    }
    schema_result = execute_sql_file(
        schema_path,
        db_config=db_config,
        dialect_str=args.dialect,
        connect_database=False,
        continue_on_error=True,
    )
    print(
        "schema_execution="
        f"{schema_result.status}, total={schema_result.total}, "
        f"passed={schema_result.passed}, failed={schema_result.failed}, "
        f"message={schema_result.message}"
    )
    if schema_result.status not in {"completed", "completed_with_errors"}:
        return

    query_result = validate_preprocessed_sql_file(
        query_path,
        db_config=db_config,
        dialect_str=args.dialect,
        keep_only_passed=False,
    )
    print(
        "query_execution="
        f"{query_result.status}, total={query_result.total}, "
        f"passed={query_result.passed}, failed={query_result.failed}, "
        f"accuracy={query_result.accuracy * 100:.2f}%"
    )
    for error in query_result.error_examples:
        print(f"error={error}")


if __name__ == "__main__":
    main()
