# RIFT Framework

## Purpose
This project provides a SQL generation pipeline with four stages:

1. `generate_random_sql.py` and `get_seedQuery.py` generate seed SQL.
2. `preprocessor/` preprocesses generated SQL.
3. `mutator/` applies one mutation rule at a time and produces multiple mutated SQLs.
4. `comparison/` receives original SQL, mutated SQL, and database configuration as an interface for later result comparison.

## How to Run

1. Configure `main.py`.
2. Run:

```powershell
python main.py
```

## Main Configuration

Edit `main.py`:

```python
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
```

### Fields

- `dialect_str`: target SQL dialect.
- `oracle`: comparison target, such as `RIFT`.
- `run_hours`: total runtime in hours.
- `use_database_tables`: whether to load table metadata from a real database.
- `db_config`: database connection information.

## Required Project Files

The framework is organized by modules. To extend it, add files in these locations:

### Generator

- `generate_random_sql.py`
- `get_seedQuery.py`

### Preprocessor

- `preprocessor/stage.py`
- `preprocessor/RIFT/rules/*.py`

Drop any `.py` file into `preprocessor/RIFT/rules/` and it will be loaded automatically.

### Mutator

- `mutator/stage.py`
- `mutator/RIFT/rules/*.py`

Drop any `.py` file into `mutator/RIFT/rules/` and it will be loaded automatically.

### Comparison

- `comparison/stage.py` for the abstract base class
- `comparison/RIFT/stage.py` for the current oracle implementation

If you want a new oracle, add a new subpackage under `comparison/` and register it in `comparison/factory.py`.

### Pipeline

- `pipeline/models.py`
- `pipeline/runner.py`
- `main.py`

## Current Behavior

- The generator creates seed SQL.
- The preprocessor rewrites seed SQL.
- The mutator applies rules one by one and produces multiple mutated queries.
- The comparison stage is currently an interface only and does not perform real result checking yet.
