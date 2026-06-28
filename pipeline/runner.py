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


def _run_internal_generation(run_settings: RunSettings, log_file_path: str) -> str:
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
        db_config=run_settings.db_config,
    )
    generate_end = time.time()
    log_message(
        f"SQL generation completed in {generate_end - generate_start:.2f}s.",
        log_file_path,
    )

    log_message("Start generating seed queries...", log_file_path)
    seed_start = time.time()
    seed_query_generator = SeedQueryGenerator()
    seed_query_generator.get_seedQuery()
    seed_end = time.time()
    log_message(
        f"Seed query generation completed in {seed_end - seed_start:.2f}s.",
        log_file_path,
    )
    return "./generated_sql/seedQuery.sql"


def _read_text_file(file_path: str) -> str:
    abs_path = os.path.abspath(file_path)
    with open(abs_path, "r", encoding="utf-8") as file_obj:
        return file_obj.read()


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
        cycle_start_time = time.time()

        log_message(
            f"Begin loop execution for up to {run_settings.run_hours} hour(s).",
            log_file_path,
        )

        while time.time() - cycle_start_time < total_seconds:
            cycle_count += 1
            log_message(f"\n===== Cycle {cycle_count} start =====", log_file_path)

            try:
                seed_file_path = _run_internal_generation(run_settings, log_file_path)

                log_message("Start preprocessing seed queries...", log_file_path)
                preprocess_start = time.time()
                preprocessor = Preprocessor(
                    input_path=seed_file_path,
                    output_path="./generated_sql/preprocessed_seedQuery.sql",
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

                log_message("Start mutation stage...", log_file_path)
                mutate_start = time.time()
                mutator = MutatorStage(
                    input_path=preprocessed_file_path,
                    output_path="./generated_sql/mutated_queries.sql",
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
                        db_config=run_settings.db_config,
                    )
                    comparison_result = comparator.compare(
                        original_sql=_read_text_file(preprocessed_file_path),
                        mutated_sql=_read_text_file(mutated_file_path),
                        db_config=run_settings.db_config,
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
