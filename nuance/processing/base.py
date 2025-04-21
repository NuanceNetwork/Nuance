from abc import ABC, abstractmethod
from typing import Any, Optional, ClassVar

class ProcessingResult:
    """Result of a processing operation."""
    
    def __init__(self, success: bool, data: Any, reason: Optional[str] = None):
        self.success = success
        self.data = data
        self.reason = reason

class Processor(ABC):
    """Base processor interface that all processors must implement."""
    
    # Registry of processor types
    registry: ClassVar[dict[str, type]] = {}
    
    def __init_subclass__(cls, **kwargs):
        """Register processor subclasses automatically."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'processor_type'):
            Processor.registry[cls.processor_type] = cls
    
    @abstractmethod
    async def process(self) -> ProcessingResult:
        """Process input data and return a result."""
        pass