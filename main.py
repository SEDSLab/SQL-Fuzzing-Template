"""Project entrypoint for long-running SQL generation pipeline runs."""

from pipeline.models import RunSettings
from pipeline.runner import run


if __name__ == '__main__':

    # =====================
    # Runtime configuration
    # =====================
    run_settings = RunSettings(
        dialect_str='tidb',
        oracle='RIFT',
        run_hours=24,
        use_database_tables=False,
        db_config={
            "host": "127.0.0.1",
            "port": 4000,
            "database": "test",
            "user": "root",
            "password": "123456",
            "dialect": "TIDB",
        },
    )

    run(run_settings)
