# neurons/validator/api_server/dependencies.py
from functools import lru_cache
from typing import Callable, Awaitable

from nuance.database.engine import get_db_session
from nuance.database import PostRepository, InteractionRepository, SocialAccountRepository, NodeRepository
from nuance.processing.nuance_check import NuanceChecker


from nuance.processing.llm import query_llm
# Dependency for database repositories
async def get_post_repo():
    return PostRepository(session_factory=get_db_session)

async def get_interaction_repo():
    return InteractionRepository(session_factory=get_db_session)

async def get_account_repo():
    return SocialAccountRepository(session_factory=get_db_session)

async def get_node_repo():
    return NodeRepository(session_factory=get_db_session)

# Dependency for NuanceChecker
@lru_cache(maxsize=1)
async def get_nuance_checker() -> Callable[[str], Awaitable[bool]]:
    nuance_checker_processor = NuanceChecker()
    
    async def nuance_checker(content: str) -> bool:
        # Get the nuance prompt
        nuance_prompt = await nuance_checker_processor.get_nuance_prompt()
        
        # Format the prompt with the post content
        prompt_nuance = nuance_prompt.format(tweet_text=content)
        
        # Call LLM to evaluate nuance
        llm_response = await query_llm(prompt=prompt_nuance, temperature=0.0)
        
        # Check if the post is approved as nuanced
        is_nuanced = llm_response.strip().lower() == "approve"
        return is_nuanced
    
    return nuance_checker