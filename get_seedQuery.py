"""Seed query extraction and execution helpers.

This module reads generated SQL statements, executes them against the currently
selected dialect, and writes executable SELECT statements into
`generated_sql/seedQuery.sql` for downstream normalization.
"""

import os
import pymysql
import psycopg2
from data_structures.db_dialect import get_current_dialect

class SeedQueryGenerator:
    """Load, execute, and filter SQL statements into a seed query file."""

    def __init__(
        self,
        file_path='generated_sql/queries.sql',
        db_config=None,
        output_path='generated_sql/seedQuery.sql',
    ):
        self.file_path = file_path
        # Connection defaults are filled later in `connect_db` based on dialect.
        self.db_config = db_config or {}
        self.output_path = output_path
        self.last_error = None
        self.execution_stats = {}

    def query_iterator(self):
        """Yield non-empty SQL statements from `self.file_path`."""
        try:
            abs_path = os.path.abspath(self.file_path)

            with open(abs_path, 'r', encoding='utf-8') as f:
                for line in f:
                    sql = line.strip()
                    if sql:
                        yield sql
        except Exception as e:
            print(f"readers. SQLError in file: {e}")

    def get_queries_count(self):
        """Count available SQL statements without loading them all into memory."""
        count = 0
        for _ in self.query_iterator():
            count += 1
        return count

    def connect_db(self):
        """Create a DB connection using dialect-specific defaults when needed."""
        try:
            dialect = get_current_dialect()
            dialect_name = dialect.name.upper()
            
            #print (f "Connecting to {dialect_name} database...")
            
            if dialect_name in ["MYSQL", "MARIADB", "TIDB", "OCEANBASE","PERCONA", "POLARDB"]:
                # Fill missing fields with safe local defaults per dialect.
                if dialect_name == "MYSQL":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'root',
                        'password': '123456',
                        'database': 'test',
                        'port': 13306
                    }
                elif dialect_name == "MARIADB":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'root',
                        'password': '123456',
                        'database': 'test',
                        'port': 9901
                    }
                elif dialect_name == "TIDB":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'root',
                        'password': '123456',
                        'database': 'test',
                        'port': 4000
                    }
                elif dialect_name == "OCEANBASE":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'root',
                        'password': '',
                        'database': 'test',
                        'port': 2881
                    }
                elif dialect_name == "PERCONA":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'root',
                        'password': '123456',
                        'database': 'test',
                        'port': 23306
                    }
                elif dialect_name == "POLARDB":
                    defaults = {
                        'host': '127.0.0.1',
                        'user': 'polardbx_root',
                        'password': '123456',
                        'database': 'test',
                        'port': 8527
                    }
                else:
                    defaults = {}

                for key, value in defaults.items():
                    if self.db_config.get(key) in [None, ""]:
                        self.db_config[key] = value

                connection_params = {
                    'host': self.db_config['host'],
                    'user': self.db_config['user'],
                    'password': self.db_config['password'],
                    'database': self.db_config['database'],
                    'port': self.db_config['port'],
                    'charset': 'utf8mb4'
                }
                
                conn = pymysql.connect(**connection_params)
            elif dialect_name == "POSTGRESQL":
                # PostgreSQL has independent defaults and default port.
                if not self.db_config.get('host'):
                    self.db_config['host'] = '127.0.0.1'
                if not self.db_config.get('user'):
                    self.db_config['user'] = 'postgres'
                if self.db_config.get('password') is None:
                    self.db_config['password'] = 'postgres'
                if not self.db_config.get('database'):
                    self.db_config['database'] = 'test'
                # Avoid carrying MySQL default port into Postgres connections
                if not self.db_config.get('port') or self.db_config.get('port') == 13306:
                    self.db_config['port'] = 5432
                
                conn = psycopg2.connect(
                    host=self.db_config['host'],
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    dbname=self.db_config['database'],
                    port=self.db_config['port']
                )
            else:
                raise ValueError(f"Unsupported database dialect: {dialect_name}")
            
            #print (f "Successfully connected to {dialect_name} database")
            return conn
        except Exception as e:
            self.last_error = e
            print(f"Database connection failed.: {e}")
            return None

    def execute_query_with_connection(self, query, conn, dialect_name=None):
        """Execute a SQL statement using an existing DB connection.

        Returns:
            tuple[list, list[str]] for SELECT/WITH queries,
            int for non-SELECT queries.
        """
        if not query or query.strip() == '':
            print("Empty Query，Skip Execution")
            return None
        if conn is None:
            return None
        if not dialect_name:
            dialect = get_current_dialect()
            dialect_name = dialect.name.upper()
        try:
            with conn.cursor() as cursor:
                if dialect_name == "POSTGRESQL":
                    import re
                    # Ensure TO_CHAR date literals are typed explicitly in Postgres.
                    pattern = r"TO_CHAR\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
                    def add_type_cast(match):
                        date_str = match.group(1)
                        format_str = match.group(2)
                        return f"TO_CHAR('{date_str}'::DATE, '{format_str}')"
                    query = re.sub(pattern, add_type_cast, query)
                elif dialect_name == "MYSQL":
                    import re
                    from data_structures.db_dialect import MySQLDialect
                    # Map canonical function names to current MySQL dialect names.
                    mysql_dialect = MySQLDialect()
                    function_pattern = r"\b([A-Z][A-Z_]+)\s*\("
                    def apply_function_mapping(match):
                        function_name = match.group(1)
                        mapped_name = mysql_dialect.get_function_name(function_name)
                        return f"{mapped_name}("
                    query = re.sub(function_pattern, apply_function_mapping, query)

                cursor.execute(query)
                processed_query = query.strip().upper()
                while processed_query.startswith('('):
                    processed_query = processed_query[1:].strip()
                is_select_query = processed_query.startswith('SELECT') or processed_query.startswith('WITH')
                if is_select_query:
                    result = cursor.fetchall()
                    column_names = [desc[0] for desc in cursor.description] if cursor.description else []
                    return (result, column_names)
                else:
                    conn.commit()
                    return cursor.rowcount
        except Exception as e:
            self.last_error = e
            print(f"Executing query failed.: {e}")
            raise

    def execute_query(self, query):
        """Execute one query with a short-lived connection."""
        self.last_error = None
        conn = self.connect_db()
        if conn is None:
            return None
        try:
            return self.execute_query_with_connection(query, conn)
        except Exception as exc:
            self.last_error = exc
            return None
        finally:
            if conn:
                conn.close()

    def execute_queries(self):
        """Execute all SQL statements from the configured input file."""
        for query in self.query_iterator():
            self.execute_query(query)

    def get_seedQuery(self, batch_size=500):
        """Execute statements and persist successful SELECTs to seedQuery.sql."""
        # Resolve dialect once for header generation and execution behavior.
        dialect = get_current_dialect()
        dialect_name = dialect.name.upper()
        
        # Create/overwrite output file and write dialect-specific header.
        seed_file_path = self.output_path
        os.makedirs(os.path.dirname(os.path.abspath(seed_file_path)), exist_ok=True)
        with open(seed_file_path, "w", encoding="utf-8") as f:
            if dialect_name != "POSTGRESQL":
                target_db = self.db_config.get("database") or "test"
                f.write(f"USE {target_db};\n")
                f.write(dialect.get_session_settings_sql())
                if not dialect.get_session_settings_sql().endswith("\n"):
                    f.write("\n")
            elif dialect_name == "POSTGRESQL":
                f.write("-- PostgreSQLThere are no use statements in，Connection database specified by connection parameters\n")
            else:
                f.write(f"-- Current dialect: {dialect_name}\n")

        # Stats used for progress reporting.
        total_queries = self.get_queries_count()
        print(f"Found {total_queries} pcsSQLInquiries:")

        #Count the number of successful select queries
        success_count = 0
        execution_success_count = 0
        execution_failed_count = 0
        error_stats = {}
        error_examples = []
        
        # Batch buffer to avoid frequent tiny file writes.
        batch = []
        batch_count = 0
        
        # Execute and filter statements one by one.
        for i, sql in enumerate(self.query_iterator(), 1):
            if i % 1000 == 0:  #Print progress once per 1000 queries processed
                print(f"Processed {i}/{total_queries} queries")
            
            print(f"Inquiries {i}:")
            result = self.execute_query(sql)
            
            if result is not None:
                execution_success_count += 1
                if isinstance(result, int):
                    print(f"Number of rows affected：{result}")
                else:
                    # Keep the original SQL text as a seed even for empty result sets.
                    batch.append(sql)
                    batch.append("\n")
                    success_count += 1
                    print(f"Number of Result Rows：{len(result)}")
            else:
                execution_failed_count += 1
                self._record_query_error(
                    query_index=i,
                    sql=sql,
                    error_stats=error_stats,
                    error_examples=error_examples,
                )
                #print(sql)
                print("Executing query failed.")
            
            # Flush in batches. `*2` because we also append trailing newline entries.
            if len(batch) >= batch_size * 2:
                with open(seed_file_path, "a", encoding="utf-8") as f:
                    for seed in batch:
                        f.write(seed)
                batch = []
                batch_count += 1
        
        # Flush remaining buffered queries.
        if batch:
            with open(seed_file_path, "a", encoding="utf-8") as f:
                for seed in batch:
                    f.write(seed)

        executed_total = execution_success_count + execution_failed_count
        execution_accuracy = (
            execution_success_count / executed_total if executed_total else 0.0
        )
        self.execution_stats = {
            "total": executed_total,
            "passed": execution_success_count,
            "failed": execution_failed_count,
            "accuracy": execution_accuracy,
            "seed_query_count": success_count,
            "error_stats": error_stats,
            "error_examples": error_examples,
        }

        print(
            "\nQuery execution complete: "
            f"total={executed_total}, "
            f"passed={execution_success_count}, "
            f"failed={execution_failed_count}, "
            f"accuracy={execution_accuracy * 100:.2f}%"
        )
        if error_stats:
            print(f"Query execution error stats: {error_stats}")
        
        print(f"\nSeed Query Generation Complete！Successfully extracted {success_count} validSELECTInquiries")
        print(f"Seed query saved to: {seed_file_path}")

    def _record_query_error(
        self,
        query_index,
        sql,
        error_stats,
        error_examples,
        max_error_examples=5,
    ):
        error = self.last_error
        error_type = self._format_error_type(error)
        error_stats[error_type] = error_stats.get(error_type, 0) + 1
        if len(error_examples) < max_error_examples:
            error_examples.append(
                f"#{query_index}: {error_type}: {error}; SQL={self._compact_sql(sql)}"
            )

    def _format_error_type(self, error):
        if error is None:
            return "UnknownError"
        error_type = type(error).__name__
        error_args = getattr(error, "args", ())
        if error_args:
            return f"{error_type}:{error_args[0]}"
        return error_type

    def _compact_sql(self, sql, max_length=300):
        compacted = " ".join(str(sql).split())
        if len(compacted) <= max_length:
            return compacted
        return compacted[: max_length - 3] + "..."
