import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurons.validator.api_server.dependencies import (
    get_interaction_repo,
    get_post_repo,
)
from neurons.validator.api_server.models import (
    PostVerificationResponse,
    InteractionResponse,
)
import nuance.constants as cst
import nuance.models as models
from nuance.database import (
    InteractionRepository,
    PostRepository,
)
from nuance.utils.logging import logger


router = APIRouter(
    prefix="/posts",
    tags=["posts"],
)


@router.get("/{platform_type}/recent", response_model=list[PostVerificationResponse])
async def get_recent_posts(
    platform_type: str,
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    cutoff_date: str = None,
    skip: int = 0,
    limit: int = 20,
    min_interactions: int = 1,
    only_scored: bool = True,
):
    """
    Get recent posts from a specific platform created after the cutoff date.

    Returns a paginated list of posts with their verification status.
    Posts are sorted by recency.

    Parameters:
    - platform_type: The type of platform to get interactions from
    - cutoff_date: ISO formatted date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ). Defaults to scoring window days ago if not provided
    - skip: Number of posts to skip (for pagination)
    - limit: Maximum number of posts to return
    - min_interactions: Minimum number of interactions required (default 1 to only return posts with verified interactions)
    - only_scored: Whether to filter posts by score (default True)
    """
    logger.info(
        f"Getting recent posts for platform: {platform_type}, cutoff: {cutoff_date}, min_interactions: {min_interactions}"
    )

    try:
        # If cutoff_date is not provided, use cst.SCORING_WINDOW days ago
        if cutoff_date is None:
            cutoff_date = (
                datetime.datetime.now(tz=datetime.timezone.utc)
                - datetime.timedelta(days=cst.SCORING_WINDOW)
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

            if only_scored:
                skip_post = False
                for interaction in interactions:
                    if (
                        interaction.processing_status
                        != models.ProcessingStatus.ACCEPTED
                    ):
                        logger.debug(
                            f"Interaction {interaction.interaction_id} is not accepted, skipping post {post.post_id}"
                        )
                        skip_post = True
                        break

                if skip_post:
                    continue

            result_posts.append(post)

        # Sort by most recent and apply pagination
        result_posts.sort(key=lambda p: p.created_at, reverse=True)

        result = []
        for post in result_posts:
            result.append(
                PostVerificationResponse(
                    platform_type=post.platform_type,
                    post_id=post.post_id,
                    account_id=post.account_id,
                    content=post.content,
                    topics=post.topics or [],
                    processing_status=post.processing_status,
                    processing_note=post.processing_note,
                    interaction_count=interaction_count,
                    created_at=post.created_at,
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


@router.get("/{platform_type}/{post_id}", response_model=PostVerificationResponse)
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
        account_id=post.account_id,
        content=post.content,
        topics=post.topics or [],
        processing_status=post.processing_status,
        processing_note=post.processing_note,
        interaction_count=len(interactions),
        created_at=post.created_at,
    )


@router.get(
    "/{platform_type}/{post_id}/interactions",
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
