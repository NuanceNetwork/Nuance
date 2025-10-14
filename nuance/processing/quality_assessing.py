import nuance.models as models
from nuance.utils.logging import logger
from nuance.processing.base import Processor, ProcessingResult
from nuance.processing.llm import query_llm, strip_thinking
from nuance.constitution import constitution_store


class QualityAssessor(Processor):
    """Checks content for good quality using LLM."""
    processor_name = "quality_assessor"
    
    async def process(self, input_data: models.Post) -> ProcessingResult[models.Post]:
        """
        Check if content shows good quality (interesting, insightful, ...).
        
        Args:
            post: Post object to check
            
        Returns:
            Processing result with quality assessment
        """
        try:
            post = input_data
            post_id = post.post_id
            content = post.content

            # Get quality assessing prompt
            quality_assessing_prompt = await constitution_store.get_quality_assessing_prompt()

            # Format the prompt with the post content
            quality_assessing_prompt = quality_assessing_prompt.format(tweet_text=content)
            
            # Call LLM to assess quality
            llm_response = strip_thinking(await query_llm(prompt=quality_assessing_prompt, temperature=0.0))
            
            # Check if the post is a quality post
            is_quality_post = llm_response.strip().lower() == "approve"

            # Update post 's data, use extra_data for now, maybe make this a field in schema if needed
            post.extra_data["is_quality_post"] = is_quality_post

            if is_quality_post:
                logger.info(f"✅ Post {post_id} is good quality")
                return ProcessingResult(
                    status=models.ProcessingStatus.ACCEPTED,
                    output=post, 
                    processor_name=self.processor_name,
                    details={"quality_assessment": "approved", "llm_response": llm_response}
                )
            else:
                logger.info(f"⚠️ Post {post_id} is not good quality")
                return ProcessingResult(
                    status=models.ProcessingStatus.ACCEPTED,
                    output=post, 
                    processor_name=self.processor_name,
                    details={"quality_assessment": "disapproved", "llm_response": llm_response}
                )
            
        except Exception as e:
            logger.error(f"❌ Error asssessing quality for post {post.post_id}: {str(e)}")
            return ProcessingResult(
                status=models.ProcessingStatus.ERROR, 
                output=post, 
                processor_name=self.processor_name,
                reason=f"Error assessing quality: {str(e)}"
            )