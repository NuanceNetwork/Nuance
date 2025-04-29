from typing import Any, Optional, Type 

from nuance.processing.base import Processor, ProcessingResult
from nuance.models import ProcessingStatus
from nuance.processing.nuance_check import NuanceChecker
from nuance.processing.topic_tagger import TopicTagger
from nuance.processing.sentiment import SentimentAnalyzer

    
class Pipeline:
    """
    Self-configuring pipeline that manages type compatibility automatically.
    
    The pipeline automatically determines input/output types from the registered processors
    and verifies type compatibility when adding processors.
    """
    
    def __init__(self):
        self.processors: list[Processor] = []
    
    def register(self, processor: Processor) -> "Pipeline":
        """
        Register a processor with this pipeline.
        
        For the first processor, sets the pipeline's input type.
        For subsequent processors, verifies type compatibility with previous processor.
        
        Args:
            processor: The processor to add to the pipeline
            
        Returns:
            Self for method chaining
            
        Raises:
            TypeError: If the processor's input type is incompatible with the previous processor's output
        """
        if not self.processors:
            # First processor - just add it
            self.processors.append(processor)
        else:
            # Check compatibility with previous processor
            current_output_type = self.get_output_type()
            processor_input_type = processor.get_input_type()

            if not issubclass(current_output_type, processor_input_type):
                raise TypeError(
                    f"Type mismatch in pipeline: Processor '{processor.processor_name}' expects "
                    f"{processor_input_type.__name__}, but previous processor outputs "
                    f"{current_output_type.__name__}"
                )
            
            # Add processor and update current output type
            self.processors.append(processor)
            
        return self
    
    def get_input_type(self) -> Optional[Type]:
        """Get the input type expected by this pipeline."""
        if not self.processors:
            return None
        return self.processors[0].get_input_type()
    
    def get_output_type(self) -> Optional[Type]:
        """Get the output type produced by this pipeline."""
        if not self.processors:
            return None
        return self.processors[-1].get_output_type()
    
    async def process(self, input_data: Any) -> ProcessingResult:
        """
        Process data through all registered processors.
        
        Args:
            input_data: The input data to process
            
        Returns:
            Processing result from the final processor
            
        Raises:
            TypeError: If the input data type doesn't match the pipeline's expected input type
            ValueError: If the pipeline has no processors
        """
        if not self.processors:
            raise ValueError("Pipeline has no processors")

        # Verify input type matches expected pipeline input
        if not isinstance(input_data, self.get_input_type()):
            raise TypeError(
                f"Pipeline expected input of type {self.get_input_type().__name__}, "
                f"but got {type(input_data).__name__}"
            )
        
        processing_details = {}
        current_data = input_data
        
        for processor in self.processors:
            result = await processor.process(current_data)
            processing_details[processor.processor_name] = result.processing_note
            current_data = result.output

            # Break if the result is rejected
            if result.status == ProcessingStatus.REJECTED:
                break
            
        final_result = result
        final_result.details = processing_details
        return final_result


class PipelineFactory:
    """Factory for creating processing pipelines."""
    
    @staticmethod
    def create_post_pipeline() -> Pipeline:
        """Create pipeline for processing posts."""
        pipeline = Pipeline()
        pipeline.register(NuanceChecker())
        pipeline.register(TopicTagger())
        return pipeline
    
    @staticmethod
    def create_interaction_pipeline() -> Pipeline:
        """Create pipeline for processing interactions."""
        pipeline = Pipeline()
        pipeline.register(SentimentAnalyzer())
        return pipeline
    
if __name__ == "__main__":
    print(PipelineFactory.create_post_pipeline())
    print(PipelineFactory.create_interaction_pipeline())
    
