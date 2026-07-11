"""Small helper functions for configurable SQL generators."""

from typing import Any, Mapping, Sequence


def weighted_choice(rng, weights: Mapping[str, float], default: str) -> str:
    if not weights:
        return default
    total = sum(max(float(weight), 0.0) for weight in weights.values())
    if total <= 0:
        return default
    pick = rng.random() * total
    running = 0.0
    for key, weight in weights.items():
        running += max(float(weight), 0.0)
        if pick <= running:
            return key
    return next(iter(weights))


def rand_range(rng, value: Sequence[int] | int, default_min: int, default_max: int) -> int:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        return rng.randint(int(value[0]), int(value[1]))
    if isinstance(value, int):
        return value
    return rng.randint(default_min, default_max)


def next_alias(ctx, prefix: str = "t") -> str:
    counter = int(ctx.flags.get("alias_counter", 0)) + 1
    ctx.flags["alias_counter"] = counter
    return f"{prefix}{counter}"


def literal_for_category(rng, category: str, data_type: str | None = None) -> tuple[Any, str]:
    dtype = data_type or {
        "numeric": "INT",
        "string": "VARCHAR",
        "datetime": "DATE",
        "boolean": "BOOLEAN",
    }.get(category, "INT")
    if category == "numeric":
        return rng.randint(0, 100), dtype
    if category == "string":
        return f"sample_{rng.randint(1, 100)}", dtype
    if category == "datetime":
        return "2023-01-01", dtype
    if category == "boolean":
        return rng.choice([True, False]), dtype
    return rng.randint(0, 100), dtype
