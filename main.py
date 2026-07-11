"""Project entrypoint for long-running SQL generation pipeline runs."""

from pipeline.models import RunSettings
from pipeline.runner import run


if __name__ == '__main__':

    # =====================
    # Runtime configuration
    # =====================
    run_settings = RunSettings(
        dialect_str='mysql',
        oracle='RIFT',
        run_hours=24,
        use_database_tables=False,
        generator_mode='configurable',
        grammar_path='grammars/with_join_aggregate.yaml',
        db_config={
            "host": "127.0.0.1",
            "port": 13306,
            "database": "test",
            "user": "root",
            "password": "123456",
            "dialect": "MYSQL",
        },
    )

    run(run_settings)
