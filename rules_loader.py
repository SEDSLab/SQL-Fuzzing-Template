"""Utilities for discovering rule functions from a rules directory."""

import inspect
import importlib.util
import os
from types import ModuleType
from typing import Callable, Iterable, List, Optional


def discover_rule_functions(
    rules_dir: str,
) -> List[Callable]:
    """Import rule modules under `rules_dir` and collect public functions."""
    discovered_rules: List[Callable] = []
    if not rules_dir or not os.path.isdir(rules_dir):
        return discovered_rules

    for module_path in _iter_python_files(rules_dir):
        module = _import_module_from_path(module_path)
        if module is None:
            continue

        for name, candidate in inspect.getmembers(module, inspect.isfunction):
            if candidate.__module__ != module.__name__:
                continue
            if name.startswith("_"):
                continue
            discovered_rules.append(candidate)

    return discovered_rules


def _iter_python_files(rules_dir: str) -> Iterable[str]:
    """Yield Python source files recursively under `rules_dir`."""
    for root, _, files in os.walk(rules_dir):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            if filename == "__init__.py":
                continue
            yield os.path.join(root, filename)


def _import_module_from_path(module_path: str) -> Optional[ModuleType]:
    """Import a module from a concrete file path."""
    module_name = _build_module_name(module_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"Failed to import rule module {module_path}: {exc}")
        return None
    return module


def _build_module_name(module_path: str) -> str:
    """Build a stable synthetic module name from a file path."""
    normalized_path = os.path.abspath(module_path)
    stem = os.path.splitext(normalized_path)[0]
    safe_name = stem.replace(os.sep, "_").replace(":", "_")
    return f"dynamic_rules_{safe_name}"
