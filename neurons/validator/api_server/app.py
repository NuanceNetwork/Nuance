# neurons/validator/api_server.py
import asyncio
from typing import Annotated, Awaitable, Callable

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
from scalar_fastapi import get_scalar_api_reference

# Import your existing database and processing components
from nuance.database import (
    NodeRepository,
    PostRepository,
    InteractionRepository,
    SocialAccountRepository,
)
import nuance.models as models
from nuance.utils.logging import logger

from neurons.validator.api_server.models import (
    MinerStatsResponse,
    PostVerificationResponse,
    InteractionResponse,
    AccountVerificationResponse
)
from neurons.validator.api_server.dependencies import (
    get_node_repo,
    get_post_repo,
    get_interaction_repo,
    get_account_repo,
    get_nuance_checker
)


app = FastAPI(
    title="Nuance Network API",
    description="API for the Nuance Network decentralized social media validation system",
    version="0.0.1",
)

# Register rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Endpoints
@app.get("/miners/{hotkey}/stats", response_model=MinerStatsResponse)
async def get_miner_stats(
    hotkey: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
):
    """
    Get overall stats for a specific miner by hotkey.
    
    This endpoint provides a summary of a miner's activity including:
    - Number of verified accounts
    - Number of posts submitted
    - Number of interactions received
    """
    logger.info(f"Getting stats for miner with hotkey: {hotkey}")
    
    # Check if node exists
    node = await node_repo.get_by(hotkey=hotkey)
    if not node:
        logger.warning(f"Miner not found with hotkey: {hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get accounts, posts and interactions counts
    accounts = await account_repo.find_many(node_hotkey=hotkey)
    account_count = len(accounts)
    logger.debug(f"Found {account_count} accounts for miner {hotkey}")

    # Get account IDs
    account_ids = [(acc.platform_type, acc.account_id) for acc in accounts]

    # Get posts and interactions
    post_count = 0
    interaction_count = 0

    for platform_type, account_id in account_ids:
        posts = await post_repo.find_many(
            platform_type=platform_type, account_id=account_id
        )
        post_count += len(posts)

        for post in posts:
            interactions = await interaction_repo.find_many(
                platform_type=platform_type, post_id=post.post_id
            )
            interaction_count += len(interactions)

    logger.info(f"Completed stats for miner {hotkey}: {post_count} posts, {interaction_count} interactions")

    return MinerStatsResponse(
        hotkey=hotkey,
        account_count=account_count,
        post_count=post_count,
        interaction_count=interaction_count,
    )


@app.get("/miners/{hotkey}/posts", response_model=list[PostVerificationResponse])
async def get_miner_posts(
    hotkey: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    skip: int = 0,
    limit: int = 20,
):
    """
    Get posts submitted by a specific miner.
    
    Returns a paginated list of posts with their verification status.
    Posts are sorted by recency.
    
    Parameters:
    - skip: Number of posts to skip (for pagination)
    - limit: Maximum number of posts to return
    """
    logger.info(f"Getting posts for miner with hotkey: {hotkey}, skip: {skip}, limit: {limit}")
    
    # Check if node exists
    node = await node_repo.get_by(hotkey=hotkey)
    if not node:
        logger.warning(f"Miner not found with hotkey: {hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get accounts associated with this miner
    accounts = await account_repo.find_many(node_hotkey=hotkey)
    if not accounts:
        logger.info(f"No accounts found for miner {hotkey}")
        return []

    # Get posts for each account
    all_posts: list[models.Post] = []
    for account in accounts:
        posts = await post_repo.find_many(
            platform_type=account.platform_type, account_id=account.account_id
        )
        all_posts.extend(posts)
    
    logger.debug(f"Found {len(all_posts)} total posts for miner {hotkey}")

    # Sort by most recent and apply pagination
    all_posts.sort(
        key=lambda x: x.created_at if hasattr(x, "created_at") else 0, reverse=True
    )
    paginated_posts = all_posts[skip : skip + limit]

    # Create response objects with interaction counts
    result = []
    for post in paginated_posts:
        interactions = await interaction_repo.find_many(
            platform_type=post.platform_type, post_id=post.post_id
        )

        result.append(
            PostVerificationResponse(
                platform_type=post.platform_type,
                post_id=post.post_id,
                content=post.content,
                topics=post.topics or [],
                processing_status=post.processing_status,
                processing_note=post.processing_note,
                interaction_count=len(interactions),
            )
        )

    return result


@app.get("/posts/{platform_type}/{post_id}", response_model=PostVerificationResponse)
async def get_post(
    platform_type: str,
    post_id: str,
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
):
    """
    Get verification status for a specific post.
    
    Returns information about a post's verification status and total interactions.
    """
    logger.info(f"Getting post details: {platform_type}/{post_id}")
    
    post = await post_repo.get_by(platform_type=platform_type, post_id=post_id)
    if not post:
        logger.warning(f"Post not found: {platform_type}/{post_id}")
        raise HTTPException(status_code=404, detail="Post not found")

    interactions = await interaction_repo.find_many(
        platform_type=platform_type, post_id=post_id
    )
    
    logger.debug(f"Found post with {len(interactions)} interactions")

    return PostVerificationResponse(
        platform_type=post.platform_type,
        post_id=post.post_id,
        content=post.content,
        topics=post.topics or [],
        processing_status=post.processing_status,
        processing_note=post.processing_note,
        interaction_count=len(interactions),
    )


@app.get("/posts/{platform_type}/{post_id}/interactions", response_model=list[InteractionResponse])
async def get_post_interactions(
    platform_type: str,
    post_id: str,
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    skip: int = 0,
    limit: int = 20,
):
    """
    Get interactions for a specific post.
    
    Returns a paginated list of interactions for a post.
    Interactions are sorted by recency.
    
    Parameters:
    - skip: Number of interactions to skip (for pagination)
    - limit: Maximum number of interactions to return
    """
    logger.info(f"Getting interactions for post: {platform_type}/{post_id}, skip: {skip}, limit: {limit}")
    
    # Verify post exists
    post = await post_repo.get_by(platform_type=platform_type, post_id=post_id)
    if not post:
        logger.warning(f"Post not found: {platform_type}/{post_id}")
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Get all interactions for the post
    interactions = await interaction_repo.find_many(
        platform_type=platform_type, post_id=post_id
    )
    
    logger.debug(f"Found {len(interactions)} interactions for post {platform_type}/{post_id}")
    
    # Sort by most recent and apply pagination
    interactions.sort(
        key=lambda x: x.created_at if hasattr(x, "created_at") else 0, reverse=True
    )
    paginated_interactions = interactions[skip : skip + limit]
    
    # Create response objects
    result = []
    for interaction in paginated_interactions:
        result.append(
            InteractionResponse(
                platform_type=interaction.platform_type,
                interaction_id=interaction.interaction_id,
                interaction_type=interaction.interaction_type,
                post_id=interaction.post_id,
                account_id=interaction.account_id,
                content=interaction.content,
                processing_status=interaction.processing_status,
                processing_note=interaction.processing_note,
            )
        )
    
    return result


@app.get("/interactions/{platform_type}/{interaction_id}", response_model=InteractionResponse)
async def get_interaction(
    platform_type: str,
    interaction_id: str,
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
):
    """
    Get details for a specific interaction.
    
    Returns information about a specific interaction's verification status.
    """
    logger.info(f"Getting interaction details: {platform_type}/{interaction_id}")
    
    interaction = await interaction_repo.get_by(
        platform_type=platform_type, interaction_id=interaction_id
    )
    
    if not interaction:
        logger.warning(f"Interaction not found: {platform_type}/{interaction_id}")
        raise HTTPException(status_code=404, detail="Interaction not found")
    
    logger.debug(f"Found interaction: {platform_type}/{interaction_id}")
    
    return InteractionResponse(
        platform_type=interaction.platform_type,
        interaction_id=interaction.interaction_id,
        interaction_type=interaction.interaction_type,
        post_id=interaction.post_id,
        account_id=interaction.account_id,
        content=interaction.content,
        processing_status=interaction.processing_status,
        processing_note=interaction.processing_note,
    )
    

@app.get(
    "/accounts/verify/{platform_type}/{account_id}",
    response_model=AccountVerificationResponse,
)
async def verify_account(
    platform_type: str,
    account_id: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
):
    """
    Check if an account is verified in the system.
    
    Verifies if a social media account is registered and associated with a miner.
    """
    logger.info(f"Verifying account: {platform_type}/{account_id}")
    
    account = await account_repo.get_by(
        platform_type=platform_type, account_id=account_id
    )

    is_verified = False
    # If account refers to a node, it is verified
    if account and account.node_hotkey and account.node_netuid:
        node = await node_repo.get_by(
            hotkey=account.node_hotkey, netuid=account.node_netuid
        )
        if node:
            is_verified = True
            logger.debug(f"Account is verified and associated with miner {account.node_hotkey}")

    if not account:
        logger.warning(f"Account not found: {platform_type}/{account_id}")
        return AccountVerificationResponse(
            platform_type=platform_type,
            account_id=account_id,
            username="unknown",
            is_verified=False,
        )

    if not is_verified:
        logger.info(f"Account found but not verified: {platform_type}/{account_id}")
        return AccountVerificationResponse(
            platform_type=platform_type,
            account_id=account_id,
            username=account.account_username,
            is_verified=False,
        )

    return AccountVerificationResponse(
        platform_type=account.platform_type,
        account_id=account.account_id,
        username=account.account_username,
        node_hotkey=account.node_hotkey,
        node_netuid=account.node_netuid,
        is_verified=True,
    )


@app.post("/nuance/check", response_model=bool)
@limiter.limit("2/minute")
async def check_nuance(
    request: Request,
    content: Annotated[str, Body(..., embed=True)],
    nuance_checker: Annotated[
        Callable[[str], Awaitable[bool]], Depends(get_nuance_checker)
    ],
):
    """
    Check text against nuance criteria (rate-limited to 10 requests per minute)
    """
    is_nuanced = await nuance_checker(content)

    return is_nuanced


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
        show_sidebar=True,
    )


async def run_api_server(port: int, shutdown_event: asyncio.Event) -> None:
    """
    Run the FastAPI server with uvicorn
    """
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Start the server task
    api_task = asyncio.create_task(server.serve())

    # Wait for shutdown event
    await shutdown_event.wait()

    # Stop the server
    server.should_exit = True
    await api_task


if __name__ == "__main__":
    # For direct execution during development
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
