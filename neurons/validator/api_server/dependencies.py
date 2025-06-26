# neurons/validator/api_server/dependencies.py
from functools import lru_cache
from typing import Callable, Awaitable

from nuance.database.engine import get_db_session
from nuance.database import PostRepository, InteractionRepository, SocialAccountRepository, NodeRepository
from nuance.processing.nuance_check import NuanceChecker
from nuance.constitution import constitution_store

from nuance.processing.llm import query_llm
# Dependency for database repositories
def get_post_repo():
    return PostRepository(session_factory=get_db_session)

def get_interaction_repo():
    return InteractionRepository(session_factory=get_db_session)

def get_account_repo():
    return SocialAccountRepository(session_factory=get_db_session)

def get_node_repo():
    return NodeRepository(session_factory=get_db_session)

# Dependency for NuanceChecker
@lru_cache(maxsize=1)
def get_nuance_checker() -> Callable[[str], Awaitable[bool]]:
    
    async def nuance_checker(content: str) -> bool:
        # Get the nuance prompt
        nuance_prompt = await constitution_store.get_nuance_prompt()
        
        # Format the prompt with the post content
        prompt_nuance = nuance_prompt.format(tweet_text=content)
        
        # Call LLM to evaluate nuance
        llm_response = await query_llm(prompt=prompt_nuance, temperature=0.0)
        
        # Check if the post is approved as nuanced
        is_nuanced = llm_response.strip().lower() == "approve"
        return is_nuanced
    
    return nuance_checker

# Dependency for TopicChecker
@lru_cache(maxsize=1)
def get_topic_checker() -> Callable[[str, str], Awaitable[bool]]:
    
    async def topic_checker(content: str, topic: str) -> tuple[bool, bool]:
        # Get the nuance prompt
        topic_prompts = await constitution_store.get_topic_prompts()
        topic_prompt = topic_prompts.get(topic)

        is_valid_topic, is_this_topic = False, False
        if topic_prompt:
            is_valid_topic = True

            # Format the prompt with the post content
            prompt_topic = topic_prompt.format(tweet_text=content)
            
            # Call LLM to evaluate nuance
            llm_response = await query_llm(prompt=prompt_topic, temperature=0.0)
            
            # Check if the post is approved as nuanced
            is_this_topic = llm_response.strip().lower() == "true"

        return is_this_topic, is_valid_topic
    
    return topic_checker
