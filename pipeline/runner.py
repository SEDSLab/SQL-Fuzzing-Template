"""Coordinates end-to-end generation, preprocessing, and mutation."""

import gc
import os
import time

from generate_random_sql import Generate
from get_seedQuery import SeedQueryGenerator
from data_structures.db_dialect import set_dialect
from preprocessor import Preprocessor
from mutator import MutatorStage
from comparison import get_comparison_stage

from .logger import log_message
from .models import RunSettings
from .preprocess_validator import execute_sql_file, validate_preprocessed_sql_file


def _run_internal_generation(
    run_settings: RunSettings,
    log_file_path: str,
    round_dir: str,
    round_name: str,
    round_db_config: dict,
) -> str:
    log_message("Start generating SQL...", log_file_path)
    generate_start = time.time()
    if run_settings.use_database_tables and not run_settings.db_config:
        raise ValueError(
            "use_database_tables=True requires db_config in RunSettings."
        )

    Generate(
        subquery_depth=2,
        total_insert_statements=40,
        num_queries=1000,
        query_type="default",
        use_database_tables=run_settings.use_database_tables,
        db_config=round_db_config,
        output_dir=round_dir,
        database_name=round_name,
        generator_mode=run_settings.generator_mode,
        grammar_path=run_settings.grammar_path,
    )
    generate_end = time.time()
    log_message(
        f"SQL generation completed in {generate_end - generate_start:.2f}s.",
        log_file_path,
    )

    schema_file_path = os.path.join(round_dir, "schema.sql")
    log_message(f"Start executing round schema before seed extraction: {schema_file_path}", log_file_path)
    schema_result = execute_sql_file(
        schema_file_path,
        db_config=round_db_config,
        dialect_str=run_settings.dialect_str,
        connect_database=False,
        continue_on_error=True,
    )
    if schema_result.status == "failed":
        raise RuntimeError(
            "Schema execution before seed extraction failed: "
            f"{schema_result.status} {schema_result.message} "
            f"{schema_result.failed_statement}"
        )
    log_message(
        "Round schema executed before seed extraction. "
        f"total={schema_result.total}, passed={schema_result.passed}, "
        f"failed={schema_result.failed}",
        log_file_path,
    )
    for error_example in schema_result.error_examples:
        log_message(
            f"Skipped schema error before seed extraction: {error_example}",
            log_file_path,
        )

    log_message("Start generating seed queries...", log_file_path)
    seed_start = time.time()
    seed_file_path = os.path.join(round_dir, "seedQuery.sql")
    seed_query_generator = SeedQueryGenerator(
        file_path=os.path.join(round_dir, "queries.sql"),
        db_config=round_db_config,
        output_path=seed_file_path,
    )
    seed_query_generator.get_seedQuery()
    query_execution_stats = seed_query_generator.execution_stats
    if query_execution_stats:
        log_message(
            "Query SQL execution completed. "
            f"total={query_execution_stats['total']}, "
            f"passed={query_execution_stats['passed']}, "
            f"failed={query_execution_stats['failed']}, "
            f"accuracy={query_execution_stats['accuracy'] * 100:.2f}%, "
            f"seed_queries={query_execution_stats['seed_query_count']}",
            log_file_path,
        )
        if query_execution_stats["error_stats"]:
            log_message(
                f"Query SQL execution error stats: {query_execution_stats['error_stats']}",
                log_file_path,
            )
        for error_example in query_execution_stats["error_examples"]:
            log_message(
                f"Query SQL execution error example: {error_example}",
                log_file_path,
            )
    seed_end = time.time()
    log_message(
        f"Seed query generation completed in {seed_end - seed_start:.2f}s.",
        log_file_path,
    )
    return seed_file_path


def _read_text_file(file_path: str) -> str:
    abs_path = os.path.abspath(file_path)
    with open(abs_path, "r", encoding="utf-8") as file_obj:
        return file_obj.read()


def _get_next_round_number(base_dir: str = "generated_sql") -> int:
    if not os.path.isdir(base_dir):
        return 1

    max_round = 0
    for name in os.listdir(base_dir):
        if not name.startswith("round"):
            continue
        suffix = name[len("round") :]
        if suffix.isdigit():
            max_round = max(max_round, int(suffix))
    return max_round + 1


def _make_round_db_config(db_config, round_name: str) -> dict:
    round_db_config = dict(db_config or {})
    round_db_config["database"] = round_name
    return round_db_config


def run(run_settings: RunSettings) -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"execution_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    log_file_path = os.path.join(log_dir, log_filename)

    start_time = time.time()
    log_message(
        f"Program started at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}",
        log_file_path,
    )

    try:
        set_dialect(run_settings.dialect_str)
        log_message(f"Dialect set to: {run_settings.dialect_str}", log_file_path)

        total_seconds = run_settings.run_hours * 3600
        cycle_count = 0
        next_round_number = _get_next_round_number()
        cycle_start_time = time.time()

        log_message(
            f"Begin loop execution for up to {run_settings.run_hours} hour(s).",
            log_file_path,
        )

        while time.time() - cycle_start_time < total_seconds:
            cycle_count += 1
            round_number = next_round_number + cycle_count - 1
            round_name = f"round{round_number}"
            round_dir = os.path.join("generated_sql", round_name)
            os.makedirs(round_dir, exist_ok=True)
            round_db_config = _make_round_db_config(run_settings.db_config, round_name)

            log_message(f"\n===== Cycle {cycle_count} start =====", log_file_path)
            log_message(
                f"Round output directory: {os.path.abspath(round_dir)}",
                log_file_path,
            )
            log_message(f"Round database: {round_name}", log_file_path)

            try:
                seed_file_path = _run_internal_generation(
                    run_settings,
                    log_file_path,
                    round_dir=round_dir,
                    round_name=round_name,
                    round_db_config=round_db_config,
                )

                log_message("Start preprocessing seed queries...", log_file_path)
                preprocess_start = time.time()
                preprocessed_file_path = os.path.join(
                    round_dir,
                    "preprocessed_seedQuery.sql",
                )
                preprocessor = Preprocessor(
                    input_path=seed_file_path,
                    output_path=preprocessed_file_path,
                )
                preprocessed_file_path = preprocessor.preprocess()
                preprocess_end = time.time()
                log_message(
                    f"Seed query preprocessing completed in {preprocess_end - preprocess_start:.2f}s.",
                    log_file_path,
                )
                log_message(
                    f"Preprocessed seed file: {os.path.abspath(preprocessed_file_path)}",
                    log_file_path,
                )

                schema_file_path = os.path.join(round_dir, "schema.sql")
                log_message(
                    f"Start executing round schema before preprocessed SQL validation: {schema_file_path}",
                    log_file_path,
                )
                schema_result = execute_sql_file(
                    schema_file_path,
                    db_config=round_db_config,
                    dialect_str=run_settings.dialect_str,
                    connect_database=False,
                    continue_on_error=True,
                )
                if schema_result.status == "failed":
                    raise RuntimeError(
                        "Schema execution before preprocessed SQL validation failed: "
                        f"{schema_result.status} {schema_result.message} "
                        f"{schema_result.failed_statement}"
                    )
                log_message(
                    "Round schema executed before preprocessed SQL validation. "
                    f"total={schema_result.total}, passed={schema_result.passed}, "
                    f"failed={schema_result.failed}",
                    log_file_path,
                )
                for error_example in schema_result.error_examples:
                    log_message(
                        f"Skipped schema error before preprocessed SQL validation: {error_example}",
                        log_file_path,
                    )

                log_message("Start validating preprocessed SQL execution...", log_file_path)
                validate_start = time.time()
                validation_result = validate_preprocessed_sql_file(
                    preprocessed_file_path,
                    db_config=round_db_config,
                    dialect_str=run_settings.dialect_str,
                )
                validate_end = time.time()
                if validation_result.status == "completed":
                    accuracy_percent = validation_result.accuracy * 100
                    log_message(
                        "Preprocessed SQL validation completed in "
                        f"{validate_end - validate_start:.2f}s. "
                        f"total={validation_result.total}, "
                        f"passed={validation_result.passed}, "
                        f"failed={validation_result.failed}, "
                        f"accuracy={accuracy_percent:.2f}%. "
                        f"Kept passed SQL in {validation_result.output_path}",
                        log_file_path,
                    )
                    for error_example in validation_result.error_examples:
                        log_message(
                            f"Preprocessed SQL validation error example: {error_example}",
                            log_file_path,
                        )
                else:
                    log_message(
                        "Preprocessed SQL validation "
                        f"{validation_result.status}: {validation_result.message}",
                        log_file_path,
                    )

                log_message("Start mutation stage...", log_file_path)
                mutate_start = time.time()
                mutator = MutatorStage(
                    input_path=preprocessed_file_path,
                    output_path=os.path.join(round_dir, "mutated_queries.sql"),
                )
                if mutator.has_rules():
                    mutated_file_path = mutator.mutate()
                    log_message(
                        f"Mutation stage completed in {time.time() - mutate_start:.2f}s.",
                        log_file_path,
                    )
                    log_message(
                        f"Mutated query file: {os.path.abspath(mutated_file_path)}",
                        log_file_path,
                    )

                    log_message("Start comparison stage...", log_file_path)
                    compare_start = time.time()
                    comparator = get_comparison_stage(
                        run_settings.oracle,
                        db_config=round_db_config,
                    )
                    comparison_result = comparator.compare(
                        original_sql=_read_text_file(preprocessed_file_path),
                        mutated_sql=_read_text_file(mutated_file_path),
                        db_config=round_db_config,
                        original_path=os.path.abspath(preprocessed_file_path),
                        mutated_path=os.path.abspath(mutated_file_path),
                    )
                    compare_end = time.time()
                    log_message(
                        f"Comparison stage completed in {compare_end - compare_start:.2f}s.",
                        log_file_path,
                    )
                    log_message(
                        f"Comparison interface result: {comparison_result['status']}",
                        log_file_path,
                    )
                else:
                    log_message("No mutation rules registered; skip mutation stage.", log_file_path)

                elapsed = time.time() - cycle_start_time
                remaining = max(total_seconds - elapsed, 0.0)
                log_message(
                    f"Cycle {cycle_count} done. elapsed={elapsed:.2f}s remaining={remaining:.2f}s",
                    log_file_path,
                )
            except Exception as exc:
                log_message(f"Cycle {cycle_count} failed: {exc}", log_file_path)
                continue
            finally:
                gc.collect()
                log_message("Garbage collection completed.")

        end_time = time.time()
        total_time = end_time - start_time
        log_message("\n===== Run Summary =====", log_file_path)
        log_message(
            f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}",
            log_file_path,
        )
        log_message(
            f"Ended at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}",
            log_file_path,
        )
        log_message(f"Total elapsed: {total_time:.2f}s", log_file_path)
        log_message(f"Completed cycles: {cycle_count}", log_file_path)
        log_message(f"Log file saved to: {os.path.abspath(log_file_path)}", log_file_path)
    except Exception as exc:
        error_time = time.time()
        log_message(f"\nProgram failed: {exc}", log_file_path)
        log_message(
            f"Failure time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(error_time))}",
            log_file_path,
        )
        log_message(f"Elapsed before failure: {error_time - start_time:.2f}s", log_file_path)
        log_message(f"Log file saved to: {os.path.abspath(log_file_path)}", log_file_path)
        raise
