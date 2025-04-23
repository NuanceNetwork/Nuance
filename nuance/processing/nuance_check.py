import asyncio
import time
from typing import Any, ClassVar, Dict
import traceback

import aiohttp

import nuance.constants as constants
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.llm import query_llm


class NuanceChecker(Processor):
    """Checks content for nuanced thinking using LLM."""
    processor_name = "nuance_checker"
    
    # Class-level cache for nuance prompt only
    _nuance_prompt_cache: ClassVar[Dict[str, Any]] = {"prompt": None, "last_updated": None}
    _nuance_prompt_lock = asyncio.Lock()
    
    async def get_nuance_prompt(self) -> str:
        """
        Get nuance evaluation prompt with caching.
        Checks for updated prompt based on configured interval.
        """
        current_time = time.time()
        
        # Check if update is needed without acquiring the lock
        if (
            self._nuance_prompt_cache["last_updated"] is None
            or current_time - self._nuance_prompt_cache["last_updated"]
            > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL
        ):
            # Only acquire the lock if update might be needed
            async with self._nuance_prompt_lock:
                # Re-check after acquiring the lock (another task might have updated meanwhile)
                if (
                    self._nuance_prompt_cache["last_updated"] is None
                    or current_time - self._nuance_prompt_cache["last_updated"]
                    > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL
                ):
                    # Update the cache if it's older than the update interval
                    try:
                        post_evaluation_prompt_url = (
                            constants.NUANCE_CONSTITUTION_STORE_URL + "post_evaluation_prompt.txt"
                        )

                        async with aiohttp.ClientSession() as session:
                            # Only fetch the nuance evaluation prompt
                            post_evaluation_prompt = await async_http_request_with_retry(
                                session, "GET", post_evaluation_prompt_url
                            )
                            
                        # Store only the nuance prompt in cache
                        self._nuance_prompt_cache["prompt"] = post_evaluation_prompt
                        self._nuance_prompt_cache["last_updated"] = current_time
                        logger.info("✅ Nuance evaluation prompt updated successfully")
                    except Exception as e:
                        logger.error(f"❌ Error fetching nuance prompt: {traceback.format_exc()}")

        return self._nuance_prompt_cache["prompt"]
    
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
            nuance_prompt = await self.get_nuance_prompt()
            
            # Format the prompt with the post content
            prompt_nuance = nuance_prompt.format(tweet_text=content)
            
            # Call LLM to evaluate nuance
            llm_response = await query_llm(prompt=prompt_nuance, temperature=0.0)
            
            # Check if the post is approved as nuanced
            is_nuanced = llm_response.strip().lower() == "approve"
            
            if is_nuanced:
                logger.info(f"✅ Post {post_id} is nuanced")
                
                # Create updated post with nuance information
                updated_post = post.model_copy()
                
                return ProcessingResult(
                    status=models.ProcessingStatus.ACCEPTED,
                    output=updated_post, 
                    processor_name=self.processor_name,
                    details={"nuance_status": "approved", "llm_response": llm_response}
                )
            else:
                # Create updated post with rejection reason
                updated_post = post.model_copy()
                
                logger.info(f"🚫 Post {post_id} is not nuanced")
                return ProcessingResult(
                    status=models.ProcessingStatus.REJECTED,
                    output=updated_post, 
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