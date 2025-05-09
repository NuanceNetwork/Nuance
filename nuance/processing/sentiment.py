from pydantic import BaseModel
from typing import Optional, Dict, Any
import traceback

import nuance.models as models 
import nuance.constants as constants
from nuance.processing.base import Processor, ProcessingResult, ProcessingStatus
from nuance.processing.llm import query_llm
from nuance.utils.logging import logger


# Define the context input type
class InteractionPostContext(BaseModel):
    """Context model for interaction processing."""
    interaction: models.Interaction
    parent_post: models.Post


class SentimentAnalyzer(Processor[InteractionPostContext, models.Interaction]):
    """Analyzes sentiment in an interaction towards its parent post."""
    
    processor_name = "sentiment_analyzer"
    
    async def process(self, input_data: InteractionPostContext) -> ProcessingResult[models.Interaction]:
        """
        Analyze sentiment between interaction and parent post.
        
        Args:
            input_data: Context containing the interaction and its parent post
            
        Returns:
            Processing result with the interaction and sentiment analysis
        """
        try:
            # Extract objects from context
            interaction = input_data.interaction
            parent_post = input_data.parent_post
            
            # Create the tone analysis prompt
            tone_prompt_template = (
                "Analyze the following Twitter conversation:\n\n"
                "Original Tweet: {parent_text}\n\n"
                "Reply: {child_text}\n\n"
                "Is the reply positive, supportive, or constructive towards the original tweet? "
                "Respond with only 'positive', 'neutral', or 'negative'."
            )
            
            prompt_tone = tone_prompt_template.format(
                child_text=interaction.content, 
                parent_text=parent_post.content
            )
            
            # Call LLM to analyze sentiment
            llm_response = await query_llm(prompt=prompt_tone, temperature=0.0)
            sentiment = llm_response.strip().lower()
            
            is_negative_response = sentiment == "negative"
            
            # Update interaction
            interaction.extra_data["sentiment"] = sentiment
            
            # Reject if negative
            if is_negative_response:
                logger.info(f"👎 Interaction {interaction.interaction_id} has negative sentiment")
                return ProcessingResult(
                    status=ProcessingStatus.REJECTED,
                    output=interaction,
                    processor_name=self.processor_name,
                    reason="Negative sentiment"
                )
            else:
                logger.info(f"✅ Interaction {interaction.interaction_id} has positive sentiment")
                return ProcessingResult(
                    status=ProcessingStatus.ACCEPTED,
                    output=interaction,
                    processor_name=self.processor_name,
                    details={
                        "sentiment": sentiment,
                }
            )
                
        except Exception as e:
            logger.error(f"❌ Error analyzing sentiment: {traceback.format_exc()}")
            return ProcessingResult(
                status=ProcessingStatus.ERROR,
                output=input_data.interaction,
                processor_name=self.processor_name,
                reason=f"Error analyzing sentiment: {str(e)}"
            )