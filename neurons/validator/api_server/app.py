# neurons/validator/api_server.py
import asyncio
import datetime
import math
import traceback
from typing import Annotated, Awaitable, Callable

import bittensor as bt
from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import argparse
import uvicorn
from scalar_fastapi import get_scalar_api_reference

import nuance.constants as cst
from nuance.database import (
    NodeRepository,
    PostRepository,
    InteractionRepository,
    SocialAccountRepository,
)
import nuance.models as models
from nuance.utils.logging import logger
from nuance.utils.bittensor_utils import get_metagraph
from nuance.settings import settings

from neurons.validator.api_server.models import (
    MinerScore,
    MinerStatsResponse,
    MinerScoresResponse,
    PostVerificationResponse,
    InteractionResponse,
    AccountVerificationResponse,
)
from neurons.validator.api_server.dependencies import (
    get_node_repo,
    get_post_repo,
    get_interaction_repo,
    get_account_repo,
    get_nuance_checker,
)
from neurons.validator.scoring import ScoreCalculator


app = FastAPI(
    title="Nuance Network API",
    description="API for the Nuance Network decentralized social media validation system",
    version="0.0.1",
)

app.add_middleware(
    CORSMiddleware,
    # Origins that should be permitted to make cross-origin requests
    allow_origins=[
        "http://localhost:5173",  # Local development server
        "https://www.nuance.info",  # Production domain
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Register rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Endpoints
@app.get("/miners/{node_hotkey}/stats", response_model=MinerStatsResponse)
async def get_miner_stats(
    node_hotkey: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    only_count_accepted: bool = True,
):
    """
    Get overall stats for a specific miner by hotkey.

    This endpoint provides a summary of a miner's activity including:
    - Number of verified accounts
    - Number of posts submitted
    - Number of interactions received
    """
    logger.info(f"Getting stats for miner with hotkey: {node_hotkey}")

    # Check if node exists
    node = await node_repo.get_by(node_hotkey=node_hotkey, node_netuid=settings.NETUID)
    if not node:
        logger.warning(f"Miner not found with hotkey: {node_hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get accounts, posts and interactions counts
    accounts = await account_repo.find_many(node_hotkey=node_hotkey)
    account_count = len(accounts)
    logger.debug(f"Found {account_count} accounts for miner {node_hotkey}")

    # Get account IDs
    account_ids = [(acc.platform_type, acc.account_id) for acc in accounts]

    # Get posts and interactions
    post_count = 0
    interaction_count = 0

    for platform_type, account_id in account_ids:
        posts = await post_repo.find_many(
            platform_type=platform_type, account_id=account_id
        )

        for post in posts:
            post_interaction_counts = 0

            if only_count_accepted:
                interactions = await interaction_repo.find_many(
                    platform_type=platform_type,
                    post_id=post.post_id,
                    processing_status=models.ProcessingStatus.ACCEPTED,
                )
            else:
                interactions = await interaction_repo.find_many(
                    platform_type=platform_type, post_id=post.post_id
                )

            post_interaction_counts = len(interactions)
            interaction_count += len(interactions)

            if post_interaction_counts > 0:
                post_count += 1

    logger.info(
        f"Completed stats for miner {node_hotkey}: {post_count} posts, {interaction_count} interactions"
    )

    return MinerStatsResponse(
        node_hotkey=node_hotkey,
        account_count=account_count,
        post_count=post_count,
        interaction_count=interaction_count,
    )


@app.get("/miners/scores", response_model=MinerScoresResponse)
async def get_miner_scores(
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    metagraph: Annotated[bt.Metagraph, Depends(get_metagraph)],
    score_calculator: ScoreCalculator = Depends(ScoreCalculator),
):
    """
    Get scores for all miners.
    """
    logger.info("Getting scores for all miners")
    # Get cutoff date (14 days ago)
    cutoff_date = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        days=14
    )

    # 1. Get all interactions from the last 14 days that are PROCESSED and ACCEPTED
    recent_interactions = await interaction_repo.get_recent_interactions(
        cutoff_date=cutoff_date, processing_status=models.ProcessingStatus.ACCEPTED
    )

    if not recent_interactions:
        logger.info("No recent interactions found for scoring")
        return MinerScoresResponse(miner_scores=[])

    logger.info(f"Found {len(recent_interactions)} recent interactions for scoring")

    # 2. Calculate scores for all miners (keyed by hotkey)
    node_scores: dict[str, dict[str, float]] = {}  # {hotkey: {category: score}}
    node_scores = await score_calculator.aggregate_interaction_scores(
        recent_interactions=recent_interactions,
        cutoff_date=cutoff_date,
        post_repository=post_repo,
        account_repository=account_repo,
        node_repository=node_repo,
    )

    # We create a score array for each category
    categories_scores = {
        category: np.zeros(len(metagraph.hotkeys))
        for category in list(cst.CATEGORIES_WEIGHTS.keys())
    }
    for hotkey, scores in node_scores.items():
        if hotkey in metagraph.hotkeys:
            for category, score in scores.items():
                categories_scores[category][metagraph.hotkeys.index(hotkey)] = score

    # Normalize scores for each category
    for category in categories_scores:
        categories_scores[category] = np.nan_to_num(categories_scores[category], 0)
        if np.sum(categories_scores[category]) > 0:
            categories_scores[category] = categories_scores[category] / np.sum(
                categories_scores[category]
            )
        else:
            categories_scores[category] = np.ones(len(metagraph.hotkeys)) / len(
                metagraph.hotkeys
            )

    # Weighted sum of categories
    scores = np.zeros(len(metagraph.hotkeys))
    for category in categories_scores:
        scores += categories_scores[category] * cst.CATEGORIES_WEIGHTS[category]

    miner_scores = []
    for hotkey in metagraph.hotkeys:
        miner_scores.append(
            MinerScore(
                node_hotkey=hotkey, score=scores[metagraph.hotkeys.index(hotkey)]
            )
        )

    return MinerScoresResponse(miner_scores=miner_scores)


@app.get(
    "/miners/{node_hotkey}/accounts", response_model=list[AccountVerificationResponse]
)
async def get_miner_accounts(
    node_hotkey: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    skip: int = 0,
    limit: int = 20,
):
    """
    Get verified accounts associated with a specific miner.

    Returns a paginated list of social media accounts verified and managed by the miner.

    Parameters:
    - skip: Number of accounts to skip (for pagination)
    - limit: Maximum number of accounts to return
    """
    logger.info(
        f"Getting accounts for miner: {node_hotkey}, skip: {skip}, limit: {limit}"
    )

    # Check if node exists
    node = await node_repo.get_by(node_hotkey=node_hotkey, node_netuid=settings.NETUID)
    if not node:
        logger.warning(f"Miner not found with hotkey: {node_hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get accounts associated with this miner
    accounts = await account_repo.find_many(node_hotkey=node_hotkey)
    if not accounts:
        logger.info(f"No accounts found for miner {node_hotkey}")
        return []

    # Sort accounts by platform type and account ID
    accounts_sorted = sorted(accounts, key=lambda a: (a.platform_type, a.account_id))
    paginated_accounts = accounts_sorted[skip : skip + limit]

    # Create response objects
    return [
        AccountVerificationResponse(
            platform_type=account.platform_type,
            account_id=account.account_id,
            username=account.account_username,
            node_hotkey=account.node_hotkey,
            node_netuid=account.node_netuid,
            is_verified=True,  # Verified since miner exists and accounts are linked
        )
        for account in paginated_accounts
    ]


@app.get("/miners/{node_hotkey}/posts", response_model=list[PostVerificationResponse])
async def get_miner_posts(
    node_hotkey: str,
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
    logger.info(
        f"Getting posts for miner with hotkey: {node_hotkey}, skip: {skip}, limit: {limit}"
    )

    # Check if node exists
    node = await node_repo.get_by(node_hotkey=node_hotkey)
    if not node:
        logger.warning(f"Miner not found with hotkey: {node_hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get accounts associated with this miner
    accounts = await account_repo.find_many(node_hotkey=node_hotkey)
    if not accounts:
        logger.info(f"No accounts found for miner {node_hotkey}")
        return []

    # Get posts for each account
    all_posts: list[models.Post] = []
    for account in accounts:
        posts = await post_repo.find_many(
            platform_type=account.platform_type, account_id=account.account_id
        )
        all_posts.extend(posts)

    logger.debug(f"Found {len(all_posts)} total posts for miner {node_hotkey}")

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
                created_at=post.created_at,
            )
        )

    return result


@app.get("/miners/{node_hotkey}/interactions", response_model=list[InteractionResponse])
async def get_miner_interactions(
    node_hotkey: str,
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    skip: int = 0,
    limit: int = 20,
):
    """
    Get all interactions on content from a specific miner.

    Returns a paginated list of interactions (likes, comments, shares) across all posts
    from all accounts managed by the miner.

    Parameters:
    - skip: Number of interactions to skip (for pagination)
    - limit: Maximum number of interactions to return
    """
    logger.info(
        f"Getting interactions for miner: {node_hotkey}, skip: {skip}, limit: {limit}"
    )

    # Check if node exists
    node = await node_repo.get_by(node_hotkey=node_hotkey, node_netuid=settings.NETUID)
    if not node:
        logger.warning(f"Miner not found with hotkey: {node_hotkey}")
        raise HTTPException(status_code=404, detail="Miner not found")

    # Get all accounts for miner
    accounts = await account_repo.find_many(node_hotkey=node_hotkey)
    if not accounts:
        logger.info(f"No accounts found for miner {node_hotkey}")
        return []

    all_interactions: list[models.Interaction] = []
    for account in accounts:
        # Get all posts for this account
        posts = await post_repo.find_many(
            platform_type=account.platform_type, account_id=account.account_id
        )
        # Get interactions for each post
        for post in posts:
            interactions = await interaction_repo.find_many(
                platform_type=post.platform_type, post_id=post.post_id
            )
            all_interactions.extend(interactions)

    # Sort by most recent first
    all_interactions.sort(key=lambda x: x.created_at, reverse=True)
    paginated_interactions = all_interactions[skip : skip + limit]

    return [
        InteractionResponse(
            platform_type=interaction.platform_type,
            interaction_id=interaction.interaction_id,
            interaction_type=interaction.interaction_type,
            post_id=interaction.post_id,
            account_id=interaction.account_id,
            content=interaction.content,
            processing_status=interaction.processing_status,
            processing_note=interaction.processing_note,
            created_at=interaction.created_at,
        )
        for interaction in paginated_interactions
    ]


@app.get("/posts/{platform_type}/recent", response_model=list[PostVerificationResponse])
async def get_recent_posts(
    platform_type: str,
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    cutoff_date: str = None,
    skip: int = 0,
    limit: int = 20,
    min_interactions: int = 1,
):
    """
    Get recent posts from a specific platform created after the cutoff date.

    Returns a paginated list of posts with their verification status.
    Posts are sorted by recency.

    Parameters:
    - platform_type: The type of platform to get interactions from
    - cutoff_date: ISO formatted date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ). Defaults to 14 days ago if not provided
    - skip: Number of posts to skip (for pagination)
    - limit: Maximum number of posts to return
    - min_interactions: Minimum number of interactions required (default 1 to only reutnr posts with verified interactions)
    """
    logger.info(
        f"Getting recent posts for platform: {platform_type}, cutoff: {cutoff_date}, min_interactions: {min_interactions}"
    )

    try:
        # If cutoff_date is not provided, use 14 days ago
        if cutoff_date is None:
            cutoff_date = (
                datetime.datetime.now(tz=datetime.timezone.utc)
                - datetime.timedelta(days=14)
            ).isoformat()

        # Parse the cutoff_date string to a datetime object
        # Try ISO format first (with time)
        try:
            parsed_cutoff_date = datetime.datetime.fromisoformat(
                cutoff_date.replace("Z", "+00:00")
            )
        except ValueError:
            # Then try just date format
            parsed_cutoff_date = datetime.datetime.strptime(cutoff_date, "%Y-%m-%d")

        # Ensure the datetime is timezone-aware
        if parsed_cutoff_date.tzinfo is None:
            parsed_cutoff_date = parsed_cutoff_date.replace(
                tzinfo=datetime.timezone.utc
            )

        logger.debug(f"Parsed cutoff date: {parsed_cutoff_date}")

        # Get posts since the cutoff date
        recent_posts = await post_repo.get_recent_posts(
            cutoff_date=parsed_cutoff_date,
            platform_type=platform_type,
        )

        logger.debug(f"Found {len(recent_posts)} posts since {cutoff_date}")

        # Process posts and filter based on interaction count
        result_posts: list[models.Post] = []
        for post in recent_posts:
            interactions = await interaction_repo.find_many(
                platform_type=post.platform_type, post_id=post.post_id
            )

            interaction_count = len(interactions)

            # Skip posts with fewer interactions than required
            if interaction_count < min_interactions:
                continue

            result_posts.append(post)

        # Sort by most recent and apply pagination
        result_posts.sort(key=lambda p: p.created_at, reverse=True)

        result = []
        for post in result_posts:
            if post.platform_type == "twitter":
                user = post.extra_data.get("user", {})
                if user:
                    username = user.get("username", "")
                    profile_pic_url = user.get("profile_image_url", "")
                else:
                    username = ""
                    profile_pic_url = ""
            else:
                username = ""
                profile_pic_url = ""

            result.append(
                PostVerificationResponse(
                    platform_type=post.platform_type,
                    post_id=post.post_id,
                    content=post.content,
                    topics=post.topics or [],
                    processing_status=post.processing_status,
                    processing_note=post.processing_note,
                    interaction_count=interaction_count,
                    created_at=post.created_at,
                    username=username,
                    profile_pic_url=profile_pic_url,
                )
            )

        paginated_result = result[skip : skip + limit]

        logger.debug(
            f"Returning {len(paginated_result)} posts after filtering for min {min_interactions} interactions"
        )
        return paginated_result

    except ValueError as e:
        logger.error(f"Invalid date format: {cutoff_date}. Error: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Please use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)",
        )


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
        created_at=post.created_at,
    )


@app.get(
    "/posts/{platform_type}/{post_id}/interactions",
    response_model=list[InteractionResponse],
)
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
    logger.info(
        f"Getting interactions for post: {platform_type}/{post_id}, skip: {skip}, limit: {limit}"
    )

    # Verify post exists
    post = await post_repo.get_by(platform_type=platform_type, post_id=post_id)
    if not post:
        logger.warning(f"Post not found: {platform_type}/{post_id}")
        raise HTTPException(status_code=404, detail="Post not found")

    # Get all interactions for the post
    interactions = await interaction_repo.find_many(
        platform_type=platform_type, post_id=post_id
    )

    logger.debug(
        f"Found {len(interactions)} interactions for post {platform_type}/{post_id}"
    )

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
                created_at=interaction.created_at,
            )
        )

    return result


@app.get(
    "/interactions/{platform_type}/recent", response_model=list[InteractionResponse]
)
async def get_recent_interactions(
    platform_type: str,
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    cutoff_date: str = None,
    skip: int = 0,
    limit: int = 20,
):
    """
    Get recent accepted interactions from a specific platform created after the cutoff date.

    Returns a paginated list of accepted interactions sorted by recency.

    Parameters:
    - platform_type: The type of platform to get interactions from
    - cutoff_date: ISO formatted date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ). Defaults to 14 days ago if not provided
    - skip: Number of interactions to skip (for pagination)
    - limit: Maximum number of interactions to return
    """
    logger.info(
        f"Getting recent accepted interactions for platform: {platform_type}, cutoff: {cutoff_date}"
    )

    try:
        # If cutoff_date is not provided, use 14 days ago
        if cutoff_date is None:
            cutoff_date = (
                datetime.datetime.now(tz=datetime.timezone.utc)
                - datetime.timedelta(days=14)
            ).isoformat()

        # Parse the cutoff_date string to a datetime object
        # Try ISO format first (with time)
        try:
            parsed_cutoff = datetime.datetime.fromisoformat(
                cutoff_date.replace("Z", "+00:00")
            )
        except ValueError:
            # Then try just date format
            parsed_cutoff = datetime.datetime.strptime(cutoff_date, "%Y-%m-%d")

        # Ensure the datetime is timezone-aware
        if parsed_cutoff.tzinfo is None:
            parsed_cutoff = parsed_cutoff.replace(tzinfo=datetime.timezone.utc)

        logger.debug(f"Parsed cutoff date: {parsed_cutoff}")

        # Get interactions since the cutoff date that are ACCEPTED
        recent_interactions = await interaction_repo.get_recent_interactions(
            cutoff_date=parsed_cutoff,
            platform_type=platform_type,
            processing_status=models.ProcessingStatus.ACCEPTED,
        )

        logger.debug(
            f"Found {len(recent_interactions)} accepted interactions since {cutoff_date}"
        )

        # Sort by creation date (newest first) and apply pagination
        recent_interactions.sort(key=lambda i: i.created_at, reverse=True)
        paginated_interactions = recent_interactions[skip : skip + limit]

        # Convert to response objects
        return [
            InteractionResponse(
                platform_type=interaction.platform_type,
                interaction_id=interaction.interaction_id,
                interaction_type=interaction.interaction_type,
                post_id=interaction.post_id,
                account_id=interaction.account_id,
                content=interaction.content,
                processing_status=interaction.processing_status,
                processing_note=interaction.processing_note,
                created_at=interaction.created_at,
            )
            for interaction in paginated_interactions
        ]

    except ValueError as e:
        logger.error(f"Invalid date format: {cutoff_date}. Error: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Please use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)",
        )


@app.get(
    "/interactions/{platform_type}/{interaction_id}", response_model=InteractionResponse
)
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
        created_at=interaction.created_at,
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
            node_hotkey=account.node_hotkey, node_netuid=account.node_netuid
        )
        if node:
            is_verified = True
            logger.debug(
                f"Account is verified and associated with miner {account.node_hotkey}"
            )

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # For direct execution during development
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=args.port)
