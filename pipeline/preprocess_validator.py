"""Execute preprocessed SQL statements and report execution success rate."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import pymysql
except Exception:  # pragma: no cover - handled at runtime
    pymysql = None

try:
    import psycopg2
except Exception:  # pragma: no cover - handled at runtime
    psycopg2 = None


MYSQL_LIKE_DIALECTS = {
    "MYSQL",
    "TIDB",
    "MARIADB",
    "OCEANBASE",
    "PERCONA",
    "POLARDB",
    "POLARDBX",
}


@dataclass
class PreprocessValidationResult:
    """Summary of preprocessed SQL execution validation."""

    status: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    accuracy: float = 0.0
    error_examples: List[str] = field(default_factory=list)
    message: str = ""
    output_path: str = ""


@dataclass
class SqlFileExecutionResult:
    """Summary of executing a SQL script file."""

    status: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    failed_statement: str = ""
    error_examples: List[str] = field(default_factory=list)
    message: str = ""


def execute_sql_file(
    file_path: str,
    db_config: Optional[Dict[str, Any]],
    dialect_str: str,
    connect_database: bool = True,
    continue_on_error: bool = False,
    max_error_examples: int = 5,
) -> SqlFileExecutionResult:
    """Execute all statements from a SQL file in order."""
    if not db_config:
        return SqlFileExecutionResult(
            status="skipped",
            message="db_config is empty; skip SQL file execution.",
        )

    try:
        statements = _read_script_statements(file_path)
    except OSError as exc:
        return SqlFileExecutionResult(
            status="failed",
            message=f"Failed to read SQL file {os.path.abspath(file_path)}: {exc}",
        )
    if not statements:
        return SqlFileExecutionResult(
            status="skipped",
            message=f"No SQL statements found in {os.path.abspath(file_path)}.",
        )

    dialect_name = _resolve_dialect_name(db_config, dialect_str)
    try:
        conn = _connect(
            db_config,
            dialect_name,
            connect_database=connect_database,
            autocommit=True,
        )
    except Exception as exc:
        return SqlFileExecutionResult(
            status="failed",
            total=len(statements),
            message=f"Database connection failed: {exc}",
        )

    passed = 0
    failed = 0
    error_examples: List[str] = []
    try:
        for index, statement in enumerate(statements, start=1):
            try:
                _execute_statement(conn, statement)
                passed += 1
            except Exception as exc:
                failed += 1
                if len(error_examples) < max_error_examples:
                    error_examples.append(
                        f"#{index}: {exc}; SQL={_compact_sql(statement)}"
                    )
                if continue_on_error:
                    continue
                return SqlFileExecutionResult(
                    status="failed",
                    total=len(statements),
                    passed=passed,
                    failed=failed,
                    failed_statement=_compact_sql(statement),
                    error_examples=error_examples,
                    message=str(exc),
                )
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return SqlFileExecutionResult(
        status="completed_with_errors" if failed else "completed",
        total=len(statements),
        passed=passed,
        failed=failed,
        error_examples=error_examples,
    )


def validate_preprocessed_sql_file(
    file_path: str,
    db_config: Optional[Dict[str, Any]],
    dialect_str: str,
    max_error_examples: int = 5,
    keep_only_passed: bool = True,
) -> PreprocessValidationResult:
    """Execute each preprocessed SQL statement and keep executable statements."""
    if not db_config:
        return PreprocessValidationResult(
            status="skipped",
            message="db_config is empty; skip preprocessed SQL validation.",
        )

    statements = _read_statements(file_path)
    if not statements:
        return PreprocessValidationResult(
            status="skipped",
            message="No preprocessed SQL statements found.",
        )

    dialect_name = _resolve_dialect_name(db_config, dialect_str)
    try:
        conn = _connect(db_config, dialect_name)
    except Exception as exc:
        return PreprocessValidationResult(
            status="failed",
            total=len(statements),
            failed=len(statements),
            message=f"Database connection failed: {exc}",
        )

    passed = 0
    failed = 0
    passed_statements: List[str] = []
    error_examples: List[str] = []
    try:
        for index, statement in enumerate(statements, start=1):
            try:
                _execute_statement(conn, statement)
                passed += 1
                passed_statements.append(statement)
            except Exception as exc:
                failed += 1
                if len(error_examples) < max_error_examples:
                    error_examples.append(
                        f"#{index}: {exc}; SQL={_compact_sql(statement)}"
                    )
            finally:
                _rollback_quietly(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    total = len(statements)
    accuracy = passed / total if total else 0.0
    abs_path = os.path.abspath(file_path)
    if keep_only_passed:
        _write_statements(abs_path, passed_statements)

    return PreprocessValidationResult(
        status="completed",
        total=total,
        passed=passed,
        failed=failed,
        accuracy=accuracy,
        error_examples=error_examples,
        output_path=abs_path,
    )


def _read_statements(file_path: str) -> List[str]:
    abs_path = os.path.abspath(file_path)
    with open(abs_path, "r", encoding="utf-8") as file_obj:
        return [line.strip() for line in file_obj if line.strip()]


def _read_script_statements(file_path: str) -> List[str]:
    abs_path = os.path.abspath(file_path)
    with open(abs_path, "r", encoding="utf-8") as file_obj:
        return _split_sql_script(file_obj.read())


def _split_sql_script(sql_script: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    quote_char = ""
    escape_next = False
    index = 0

    while index < len(sql_script):
        char = sql_script[index]
        next_char = sql_script[index + 1] if index + 1 < len(sql_script) else ""

        if not quote_char and char == "-" and next_char == "-":
            while index < len(sql_script) and sql_script[index] != "\n":
                current.append(sql_script[index])
                index += 1
            continue

        current.append(char)

        if escape_next:
            escape_next = False
        elif quote_char and char == "\\":
            escape_next = True
        elif char in ("'", '"', "`"):
            if not quote_char:
                quote_char = char
            elif quote_char == char:
                quote_char = ""
        elif char == ";" and not quote_char:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []

        index += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _write_statements(file_path: str, statements: List[str]) -> None:
    with open(file_path, "w", encoding="utf-8") as file_obj:
        for statement in statements:
            file_obj.write(statement)
            file_obj.write("\n")


def _resolve_dialect_name(db_config: Dict[str, Any], dialect_str: str) -> str:
    return str(db_config.get("dialect") or dialect_str or "").upper()


def _connect(
    db_config: Dict[str, Any],
    dialect_name: str,
    connect_database: bool = True,
    autocommit: bool = False,
):
    if dialect_name in MYSQL_LIKE_DIALECTS:
        if pymysql is None:
            raise RuntimeError("pymysql is not available.")
        connection_params = {
            "host": db_config["host"],
            "port": int(db_config["port"]),
            "user": db_config["user"],
            "password": db_config.get("password") or "",
            "charset": "utf8mb4",
            "autocommit": autocommit,
            "connect_timeout": 10,
            "read_timeout": 60,
            "write_timeout": 60,
        }
        if connect_database:
            connection_params["database"] = db_config["database"]
        return pymysql.connect(**connection_params)

    if dialect_name == "POSTGRESQL":
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not available.")
        conn = psycopg2.connect(
            host=db_config["host"],
            port=int(db_config["port"]),
            user=db_config["user"],
            password=db_config.get("password") or "",
            dbname=db_config["database"] if connect_database else "postgres",
            connect_timeout=10,
        )
        conn.autocommit = autocommit
        return conn

    raise ValueError(f"Unsupported validation dialect: {dialect_name}")


def _execute_statement(conn, statement: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(statement)
        if cursor.description:
            cursor.fetchall()


def _rollback_quietly(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _compact_sql(statement: str, max_length: int = 300) -> str:
    compacted = " ".join(statement.split())
    if len(compacted) <= max_length:
        return compacted
    return compacted[: max_length - 3] + "..."
