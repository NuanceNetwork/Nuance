import asyncio
import time
from typing import Any, ClassVar, Dict
import traceback

import aiohttp

import nuance.constants as cst
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.llm import query_llm
from nuance.constitution import constitution_store


class NuanceChecker(Processor):
    """Checks content for nuanced thinking using LLM."""
    processor_name = "nuance_checker"
    
    async def process(self, input_data: models.Post) -> ProcessingResult[models.Post]:
        """
        Check if content shows nuanced thinking.
        
        Args:
            post: Post object to check
            
        Returns:
            Processing result with nuance check status
        """
        try:
            post = input_data
            post_id = post.post_id
            content = post.content
            
            # Get the nuance prompt
            nuance_prompt = await constitution_store.get_nuance_prompt()
            
            # Format the prompt with the post content
            prompt_nuance = nuance_prompt.format(tweet_text=content)
            
            # Call LLM to evaluate nuance
            llm_response = await query_llm(prompt=prompt_nuance, temperature=0.0)
            
            # Check if the post is approved as nuanced
            is_nuanced = llm_response.strip().lower() == "approve"
            
            if is_nuanced:
                logger.info(f"✅ Post {post_id} is nuanced")
                return ProcessingResult(
                    status=models.ProcessingStatus.ACCEPTED,
                    output=post, 
                    processor_name=self.processor_name,
                    details={"nuance_status": "approved", "llm_response": llm_response}
                )
            else:
                logger.info(f"🚫 Post {post_id} is not nuanced")
                return ProcessingResult(
                    status=models.ProcessingStatus.REJECTED,
                    output=post, 
                    processor_name=self.processor_name,
                    reason="Content lacks nuance",
                    details={"llm_response": llm_response}
                )
                
        except Exception as e:
            logger.error(f"❌ Error evaluating nuance for post {post.post_id}: {str(e)}")
            return ProcessingResult(
                status=models.ProcessingStatus.ERROR,
                output=post, 
                processor_name=self.processor_name,
                reason=f"Error checking nuance: {str(e)}"
            )