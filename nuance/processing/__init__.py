# nuance/processing/__init__.py
from nuance.processing.base import ProcessingResult
from nuance.processing.pipeline import PipelineFactory

__all__ = [
    "PipelineFactory",
    "ProcessingResult",
]