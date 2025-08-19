import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

import nuance.constants as cst
import nuance.models as models
from neurons.validator.api_server.dependencies import get_interaction_repo
from neurons.validator.api_server.models import InteractionResponse
from nuance.database import InteractionRepository
from nuance.utils.logging import logger


router = APIRouter(
    prefix="/interactions",
    tags=["interactions"],
)


@router.get("/{platform_type}/recent", response_model=list[InteractionResponse])
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
    - cutoff_date: ISO formatted date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ). Defaults to scoring window days ago if not provided
    - skip: Number of interactions to skip (for pagination)
    - limit: Maximum number of interactions to return
    """
    logger.info(
        f"Getting recent accepted interactions for platform: {platform_type}, cutoff: {cutoff_date}"
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


@router.get("/{platform_type}/{interaction_id}", response_model=InteractionResponse)
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
