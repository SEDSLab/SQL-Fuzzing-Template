# RIFT Framework

## Purpose
This project provides a SQL generation pipeline with five stages:

1. `generate_random_sql.py` writes round-scoped SQL files under `generated_sql/roundX/`, then the pipeline creates and uses the matching `roundX` database for seed extraction.
2. `preprocessor/` preprocesses generated SQL.
3. The pipeline reloads `schema.sql`, executes preprocessed SQL on the matching `roundX` database, records the execution success rate, and keeps only executable SQL in the preprocessed SQL file.
4. `mutator/` applies one mutation rule at a time and produces multiple mutated SQLs.
5. `comparison/` receives original SQL, mutated SQL, and database configuration as an interface for later result comparison.

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

- Each cycle writes files into `generated_sql/roundX/` and runs against database `roundX`.
- The generator creates round-scoped schema and query SQL files.
- The pipeline executes `schema.sql` before seed extraction and again before preprocessed SQL validation.
- The pipeline logs `queries.sql` execution total, passed, failed, accuracy, error stats, and sampled errors.
- The preprocessor rewrites seed SQL.
- The pipeline executes preprocessed SQL on the round database, logs total, passed, failed, and accuracy, and rewrites the preprocessed SQL file with only passed statements.
- The mutator applies rules one by one and produces multiple mutated queries.
- The comparison stage is currently an interface only and does not perform real result checking yet.
