# nuance/processing/base.py
from abc import ABC, abstractmethod
from typing import (
    Any,
    Generic,
    TypeVar,
    Optional,
    ClassVar,
    Type,
    get_type_hints,
    get_args,
)

from nuance.models import ProcessingStatus

T_Input = TypeVar("T_Input")
T_Output = TypeVar("T_Output")


class ProcessingResult(Generic[T_Output]):
    """Result of a processing operation with typed output."""

    def __init__(
        self,
        status: ProcessingStatus,
        output: T_Output,
        processor_name: str,
        reason: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        self.status = status
        self.output = output
        self.processor_name = processor_name
        self.reason = reason
        self.details = details or {}

    @property
    def processing_note(self) -> str:
        """Get a human-readable processing note."""
        if self.status == ProcessingStatus.REJECTED:
            return f"{self.processor_name}: {self.reason}"
        elif self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.processor_name}: Passed ({details_str})"
        else:
            return f"{self.processor_name}: Passed"


class Processor(Generic[T_Input, T_Output], ABC):
    """Base processor with typed input and output."""

    # Registry of processor types
    registry: ClassVar[dict[str, Type["Processor"]]] = {}

    # Processor identification
    processor_name: str

    def __init_subclass__(cls, **kwargs):
        """Register processor subclasses automatically."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "processor_name"):
            Processor.registry[cls.processor_name] = cls

    @abstractmethod
    async def process(self, input_data: T_Input) -> ProcessingResult[T_Output]:
        """
        Process input data and return a result.

        Args:
            input_data: The input data to process

        Returns:
            Processing result with the output data
        """
        pass

    @classmethod
    def get_input_type(cls) -> Type:
        """Get the input type this processor expects."""
        hints = get_type_hints(cls.process)
        return hints["input_data"]

    @classmethod
    def get_output_type(cls) -> Type:
        """Get the output type this processor produces."""
        hints = get_type_hints(cls.process)
        result_type = hints["return"]
        return get_args(result_type)[0]
