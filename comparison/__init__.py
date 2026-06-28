"""Result comparison package for generated SQL pairs."""

from .factory import get_comparison_stage
from .stage import ComparisonStage
from .RIFT import RiftComparisonStage

__all__ = ["ComparisonStage", "RiftComparisonStage", "get_comparison_stage"]
