from typing import Any

import nuance.models as models
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.nuance_check import NuanceChecker
from nuance.processing.topic_tagger import TopicTagger

class Pipeline:
    """Pipeline that manages and executes a sequence of processors."""
    
    def __init__(self):
        self.processors: list[Processor] = []
    
    def register(self, processor: Processor) -> "Pipeline":
        """Register a processor with this pipeline."""
        self.processors.append(processor)
        return self
    
    async def process(self, data: dict[str, Any]) -> ProcessingResult:
        """Process data through all registered processors."""
        current_data = data.copy()
        
        for processor in self.processors:
            result = await processor.process(current_data)
            if not result.success:
                return result
            current_data.update(result.data)
        
        return ProcessingResult(True, current_data)


class PipelineFactory:
    """Factory for creating processing pipelines."""
    
    @staticmethod
    def create_post_pipeline() -> Pipeline:
        """
        Create a pipeline for processing posts.
        
        The sequence is:
        1. Nuance checking
        2. Topic tagging
            
        Returns:
            Configured pipeline
        """
        # Create components
        nuance_checker = NuanceChecker()
        topic_tagger = TopicTagger()
        
        # Create and configure pipeline
        pipeline = Pipeline()
        
        # Register processors in order
        pipeline.register(nuance_checker)
        pipeline.register(topic_tagger)
        
        return pipeline
    
    @staticmethod
    def create_interaction_pipeline(keypair=None) -> Pipeline:
        """
        Create a pipeline for processing interactions.
        
        Args:
            keypair: Optional keypair for LLM authentication
            
        Returns:
            Configured pipeline
        """
        # Create and configure pipeline
        pipeline = Pipeline(input_schema=models.Interaction, output_schema=models.Interaction)
        
        # Add interaction processors
        # Example: pipeline.register(SentimentAnalyzer(keypair=keypair))
        
        return pipeline
    
    @staticmethod
    def create_pipelines(keypair=None) -> dict[str, Pipeline]:
        """
        Create all required pipelines.
        
        Args:
            keypair: Optional keypair for LLM authentication
            
        Returns:
            Dictionary of named pipelines
        """
        # Create pipelines
        pipelines = {
            "post": PipelineFactory.create_post_pipeline(keypair=keypair),
            "interaction": PipelineFactory.create_interaction_pipeline(keypair=keypair)
        }
        
        return pipelines