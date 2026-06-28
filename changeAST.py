"""Compatibility wrapper for the new preprocessor component."""

from preprocessor import Preprocessor


class PreSolve(Preprocessor):
    """Backward-compatible alias for the preprocessor component."""

    def __init__(self, file_path: str = "./generated_sql/seedQuery.sql", db_config=None):
        super().__init__(
            input_path=file_path,
            output_path="./generated_sql/preprocessed_seedQuery.sql",
        )
        self.db_config = db_config
