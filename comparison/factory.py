"""Factory for selecting comparison stage implementations by oracle name."""

from typing import Dict, Optional, Type

from .RIFT import RiftComparisonStage
from .stage import ComparisonStage


_COMPARISON_STAGE_REGISTRY: Dict[str, Type[ComparisonStage]] = {
    "RIFT": RiftComparisonStage,
}


def _normalize_oracle_name(oracle: Optional[str]) -> str:
    if oracle is None:
        return ""
    return oracle.strip().upper()


def get_comparison_stage(
    oracle: Optional[str],
    db_config: Optional[Dict[str, object]] = None,
) -> ComparisonStage:
    """Return the comparison stage implementation registered for `oracle`."""
    oracle_name = _normalize_oracle_name(oracle)
    stage_cls = _COMPARISON_STAGE_REGISTRY.get(oracle_name)
    if stage_cls is None:
        supported = ", ".join(sorted(_COMPARISON_STAGE_REGISTRY)) or "<none>"
        raise ValueError(
            f"Unsupported oracle '{oracle}'. Supported oracles: {supported}."
        )
    return stage_cls(db_config=db_config)
