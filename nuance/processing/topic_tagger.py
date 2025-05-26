import asyncio
import time
from typing import Any, ClassVar
import traceback

import aiohttp

import nuance.constants as cst
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.llm import query_llm


class TopicTagger(Processor):
    """Tags content with relevant topics using LLM."""
    
    processor_name = "topic_tagger"
    
    # Class-level cache for topic prompts
    _topic_prompts_cache: ClassVar[dict[str, Any]] = {"prompts": {}, "last_updated": None}
    _topic_prompts_lock = asyncio.Lock()
    
    async def get_topic_prompts(self) -> dict[str, str]:
        """
        Get topic relevance prompts with caching.
        Checks for updated prompts based on configured interval.
        """
        current_time = time.time()
        
        # Check if update is needed without acquiring the lock
        if (
            self._topic_prompts_cache["last_updated"] is None
            or current_time - self._topic_prompts_cache["last_updated"]
            > cst.NUANCE_CONSTITUTION_UPDATE_INTERVAL
        ):
            # Only acquire the lock if update might be needed
            async with self._topic_prompts_lock:
                # Re-check after acquiring the lock (another task might have updated meanwhile)
                if (
                    self._topic_prompts_cache["last_updated"] is None
                    or current_time - self._topic_prompts_cache["last_updated"]
                    > cst.NUANCE_CONSTITUTION_UPDATE_INTERVAL
                ):
                    # Update the cache if it's older than the update interval
                    try:
                        topic_relevance_prompt_urls = {}
                        for topic in cst.TOPICS:
                            topic_relevance_prompt_urls[topic] = (
                                cst.NUANCE_CONSTITUTION_STORE_URL
                                + f"topic_relevance_prompts/{topic}_prompt.txt"
                            )

                        async with aiohttp.ClientSession() as session:
                            # Fetch all topic relevance prompts
                            topic_relevance_prompt_data = await asyncio.gather(
                                *[
                                    async_http_request_with_retry(
                                        session, "GET", topic_relevance_prompt_urls[topic]
                                    )
                                    for topic in cst.TOPICS
                                ]
                            )
                            
                        # Map topics to their prompts
                        topic_prompts = {
                            topic: data for topic, data in zip(cst.TOPICS, topic_relevance_prompt_data)
                        }
                            
                        # Store only the topic prompts in cache
                        self._topic_prompts_cache["prompts"] = topic_prompts
                        self._topic_prompts_cache["last_updated"] = current_time
                        logger.info("✅ Topic relevance prompts updated successfully")
                    except Exception as e:
                        logger.error(f"❌ Error fetching topic prompts: {traceback.format_exc()}")

        return self._topic_prompts_cache["prompts"]
    
    async def process(self, input_data: models.Post) -> ProcessingResult[models.Post]:
        """
        Process a post by tagging it with relevant topics.
        
        Args:
            data: Dictionary containing content to tag
            
        Returns:
            Processing result with identified topics
        """
        try:
            post = input_data
            post_id = post.post_id
            content = post.content
            
            # Get the topic prompts
            topic_prompts = await self.get_topic_prompts()
            
            # Initialize topics list
            identified_topics = []
            
            # Check each topic
            for topic in cst.TOPICS:
                # Skip if we don't have a prompt for this topic
                if topic not in topic_prompts:
                    logger.warning(f"⚠️ No prompt available for topic '{topic}'")
                    continue
                
                # Use the topic-specific prompt template
                prompt_about = topic_prompts[topic].format(tweet_text=content)
                
                # Call LLM to evaluate topic relevance
                llm_response = await query_llm(prompt=prompt_about, temperature=0.0)
                
                # Check if the post is related to this topic
                is_relevant = llm_response.strip().lower() == "true"
                
                if is_relevant:
                    logger.info(f"✅ Post {post_id} is about {topic}")
                    identified_topics.append(topic)
                else:
                    logger.debug(f"🚫 Post {post_id} is not about {topic}")
            
            # Update data with identified topics
            post.topics = identified_topics
            
            # We don't fail processing if no topics are found
            logger.info(f"📋 Post {post_id} tagged with {len(identified_topics)} topics")
            return ProcessingResult(
                status=models.ProcessingStatus.ACCEPTED, 
                output=post,
                processor_name=self.processor_name,
                details={"topics": identified_topics, "topic_count": len(identified_topics)}
            )
                
        except Exception as e:
            logger.error(f"❌ Error tagging topics for post {post.post_id}: {str(e)}")
            return ProcessingResult(
                status=models.ProcessingStatus.ERROR, 
                output=post, 
                processor_name=self.processor_name,
                reason=f"Error tagging topics: {str(e)}"
            )