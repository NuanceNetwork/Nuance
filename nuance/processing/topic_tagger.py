import nuance.constants as cst
import nuance.models as models
from nuance.utils.logging import logger
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.llm import query_llm, strip_thinking
from nuance.constitution import constitution_store
from nuance.social.discovery.twitter import TwitterDiscoveryStrategy


class TopicTagger(Processor):
    """Tags content with relevant topics using LLM."""
    
    processor_name = "topic_tagger"

    def __init__(self):
        super().__init__()
        # Initialize Twitter discovery strategy once
        self._twitter_discovery = TwitterDiscoveryStrategy()
    
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
            topic_prompts = await constitution_store.get_topic_prompts()
            
            # Initialize topics list
            identified_topics = []
            
            # Check each topic
            # Topics without a prompt or not in the constitution config is implicitly skipped
            for topic, topic_ptompt in topic_prompts.items():
                # Use the topic-specific prompt template
                prompt_about = topic_ptompt.format(tweet_text=content)
                
                # Call LLM to evaluate topic relevance
                llm_response = strip_thinking(await query_llm(prompt=prompt_about, temperature=0.0))
                
                # Check if the post is related to this topic
                is_relevant = llm_response.strip().lower() == "true"
                
                if is_relevant:
                    logger.info(f"✅ Post {post_id} is about {topic}")
                    identified_topics.append(topic)
                else:
                    logger.debug(f"🚫 Post {post_id} is not about {topic}")

            # Special handling for "nuance_sharing" topic
            # This post QRT a post from Nuance subnet 's X account
            if post.platform_type == models.PlatformType.TWITTER:
                try:
                    is_quote_tweet = post.extra_data.get("is_quote_tweet", False)
                    if is_quote_tweet:
                        quoted_status_id = post.extra_data.get("quoted_status_id")
                        if quoted_status_id:
                            logger.debug(f"🔍 Post {post_id} is quote tweet, quoted_status_id: {quoted_status_id}")

                            # Fetch the quoted post to check if it's from Nuance account
                            quoted_post = await self._twitter_discovery.get_post(quoted_status_id)

                            if quoted_post.account_id == cst.NUANCE_SOCIAL_ACCOUNT_ID:
                                identified_topics.append("nuance_sharing")
                                logger.info(f"✅ Post {post_id} tagged with 'nuance_sharing' - quotes Nuance account post {quoted_status_id}")
                                
                except Exception as e:
                    logger.warning(f"⚠️ Error checking nuance_sharing for post {post_id}: {str(e)}")
            
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