"""Structured grammar configuration for configurable SQL generation."""

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, MutableMapping


@dataclass
class GrammarSpec:
    """Configuration wrapper with dotted-path access helpers."""

    rules: Dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.rules
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return default
            current = current[part]
        return current

    def merge(self, overrides: Mapping[str, Any]) -> "GrammarSpec":
        merged = _deep_merge(dict(self.rules), overrides)
        return GrammarSpec(merged)


_REPLACE_KEYS = {"source_kinds", "join_source_kinds", "expr_kinds", "atoms", "connectors", "rhs_kinds"}


def _deep_merge(base: MutableMapping[str, Any], overrides: Mapping[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if key not in _REPLACE_KEYS and isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return dict(base)


def default_select_spec() -> GrammarSpec:
    """Return the default configurable SELECT profile."""

    return GrammarSpec(
        {
            "query": {
                "root": "select",
                "max_depth": 3,
            },
            "set_operation": {
                "operation_types": ["UNION", "UNION ALL", "EXCEPT", "INTERSECT"],
                "mixed_operations": True,
                "query_count": [2, 3],
                "projection_count": [1, 3],
                "categories": ["numeric", "string", "datetime"],
            },
            "select": {
                "distinct_prob": 0.1,
                "cte": {
                    "enabled_prob": 0.1,
                    "count": [1, 2],
                    "projection_count": [1, 3],
                    "where": {
                        "enabled_prob": 0.45,
                    },
                    "having": {
                        "enabled_prob": 0.35,
                    },
                    "order_by": {
                        "enabled_prob": 0.2,
                    },
                    "limit": {
                        "enabled_prob": 0.2,
                    },
                },
                "projection": {
                    "count": [1, 4],
                    "expr_kinds": {
                        "column": 0.72,
                        "literal": 0.15,
                        "arithmetic": 0.05,
                        "bool_expr": 0.03,
                        "subquery": 0.05,
                        "window_function": 0.0,
                    },
                    "bool_expr": {
                        "max_depth": 1,
                    },
                },
                "from": {
                    "source_kinds": {
                        "table": 0.65,
                        "join": 0.25,
                        "derived_table": 0.05,
                        "cte": 0.05,
                    },
                    "join_types": ["INNER", "LEFT", "RIGHT", "CROSS"],
                    "join_source_kinds": {
                        "table": 0.8,
                        "derived_table": 0.15,
                        "cte": 0.05,
                    },
                    "max_joins": 2,
                },
                "where": {
                    "enabled_prob": 0.7,
                    "expr": "bool_expr",
                },
                "having": {
                    "enabled_prob": 0.3,
                },
                "order_by": {
                    "enabled_prob": 0.35,
                    "max_columns": 2,
                },
                "limit": {
                    "enabled_prob": 0.25,
                    "range": [1, 100],
                },
            },
            "bool_expr": {
                "max_depth": 2,
                "atom_prob": 0.65,
                "atoms": {
                    "comparison": 0.45,
                    "is_null": 0.15,
                    "between": 0.1,
                    "like": 0.1,
                    "regexp": 0.05,
                    "in_subquery": 0.05,
                    "not_in_subquery": 0.03,
                    "any_all_subquery": 0.02,
                    "exists_subquery": 0.05,
                },
                "connectors": {
                    "and": 0.45,
                    "or": 0.45,
                    "not": 0.1,
                },
                "connector_operands": {
                    "and": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "or": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "not": {
                        "operand": {"kind": "bool_expr"},
                    },
                },
            },
            "join_on": {
                "max_depth": 2,
                "atom_prob": 0.65,
                "atoms": {
                    "column_comparison": 0.6,
                    "comparison": 0.15,
                    "between": 0.05,
                    "like": 0.05,
                    "is_null": 0.05,
                    "in_subquery": 0.1,
                    "not_in_subquery": 0.05,
                    "exists_subquery": 0.05,
                },
                "connectors": {
                    "and": 0.45,
                    "or": 0.45,
                    "not": 0.1,
                },
                "connector_operands": {
                    "and": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "or": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "not": {
                        "operand": {"kind": "bool_expr"},
                    },
                },
            },
            "having_bool": {
                "max_depth": 2,
                "atom_prob": 0.65,
                "atoms": {
                    "aggregate_comparison": 0.7,
                    "group_expression_comparison": 0.2,
                    "exists_subquery": 0.1,
                },
                "connectors": {
                    "and": 0.45,
                    "or": 0.45,
                    "not": 0.1,
                },
                "connector_operands": {
                    "and": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "or": {
                        "left": {"kind": "bool_expr"},
                        "right": {"kind": "bool_expr"},
                    },
                    "not": {
                        "operand": {"kind": "bool_expr"},
                    },
                },
            },
            "subquery": {
                "max_depth": 2,
                "correlated_prob": 0.0,
                "in_subquery": {
                    "from": {
                        "source_kinds": {
                            "table": 0.65,
                            "join": 0.25,
                            "derived_table": 0.05,
                            "cte": 0.05,
                        },
                        "join_source_kinds": {
                            "table": 0.8,
                            "derived_table": 0.15,
                            "cte": 0.05,
                        },
                        "join_types": ["INNER", "LEFT", "RIGHT", "CROSS"],
                        "max_joins": 2,
                    },
                    "projection": {
                        "expr_kinds": ["column", "function", "arithmetic", "literal"],
                    },
                    "where": {
                        "enabled_prob": 0.45,
                        "max_depth": 1,
                    },
                    "order_by": {
                        "enabled_prob": 0.2,
                    },
                    "limit": {
                        "enabled_prob": 0.0,
                        "range": [1, 50],
                    },
                },
                "exists_subquery": {
                    "from": {
                        "source_kinds": {
                            "table": 0.55,
                            "join": 0.35,
                            "derived_table": 0.05,
                            "cte": 0.05,
                        },
                        "join_source_kinds": {
                            "table": 0.75,
                            "derived_table": 0.2,
                            "cte": 0.05,
                        },
                        "join_types": ["INNER", "LEFT", "RIGHT", "CROSS"],
                        "max_joins": 2,
                    },
                    "projection": {
                        "expr_kinds": ["literal", "column"],
                    },
                    "where": {
                        "enabled_prob": 0.45,
                        "max_depth": 1,
                    },
                    "order_by": {
                        "enabled_prob": 0.25,
                    },
                    "limit": {
                        "enabled_prob": 0.25,
                        "range": [1, 50],
                    },
                },
                "scalar_subquery": {
                    "projection": {
                        "expr_kinds": ["column", "function", "arithmetic", "literal"],
                    },
                    "where": {
                        "enabled_prob": 0.45,
                        "max_depth": 1,
                    },
                    "order_by": {
                        "enabled_prob": 0.4,
                    },
                },
            },
            "window_function": {
                "functions": {
                    "ROW_NUMBER": 1.0,
                    "RANK": 0.8,
                    "DENSE_RANK": 0.8,
                    "NTILE": 0.4,
                    "LAG": 0.5,
                    "LEAD": 0.5,
                    "FIRST_VALUE": 0.4,
                    "LAST_VALUE": 0.4,
                },
                "partition_by": {
                    "enabled_prob": 0.45,
                    "max_columns": 1,
                },
                "order_by": {
                    "enabled_prob": 0.9,
                    "max_columns": 1,
                },
                "frame": {
                    "enabled_prob": 0.0,
                    "clauses": ["ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW"],
                },
            },
            "arithmetic": {
                "operators": ["+", "-", "*", "/", "%"],
            },
        }
    )
