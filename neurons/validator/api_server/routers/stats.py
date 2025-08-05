# Simplified neurons/validator/api_server/routers/stats.py
import datetime
from typing import Annotated

import bittensor as bt
from fastapi import APIRouter, Depends, HTTPException, Query

from neurons.validator.api_server.dependencies import (
    get_interaction_repo,
    get_post_repo,
    get_account_repo,
    get_node_repo,
)
from neurons.validator.api_server.models import (
    TopPostsResponse,
    TopMinersResponse,
    TopPostItem,
    TopMinerItem,
    SubnetStatsSummary
)
from neurons.validator.api_server.routers.miners import get_miner_scores
from neurons.validator.api_server.utils import extract_post_stats
from neurons.validator.scoring import ScoreCalculator
import nuance.models as models
from nuance.database import (
    InteractionRepository,
    PostRepository,
    SocialAccountRepository,
    NodeRepository,
)
from nuance.utils.bittensor_utils import get_metagraph
from nuance.utils.logging import logger



def _parse_date_range(start_date: str, end_date: str) -> tuple[datetime.datetime, datetime.datetime]:
    """Parse start_date and end_date strings to datetime objects with proper timezone"""
    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        # Include the entire end date
        end_dt = end_dt + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)

        if start_dt >= end_dt:
            raise HTTPException(
                status_code=400, detail="start_date must be before end_date"
            )
        
        return start_dt, end_dt
        
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )
    
def _get_default_date_range(days=7) -> tuple[str, str]:
    """Get default start_date and end_date for last `days` days"""
    end_date = datetime.datetime.now(tz=datetime.timezone.utc)
    start_date = end_date - datetime.timedelta(days=days)
    
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


router = APIRouter(
    prefix="/stats",
    tags=["stats"],
)



@router.get("/top-posts", response_model=TopPostsResponse)
async def get_top_posts(
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    start_date: str = Query(None, description="Start date (YYYY-MM-DD), defaults to 7 days ago"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD), defaults to today"),
    limit: int = Query(50, ge=1, le=200),
):
    if not start_date or not end_date:
        default_start, default_end = _get_default_date_range()
        start_date = start_date or default_start
        end_date = end_date or default_end

    logger.info(f"Getting posts for dashboard: {start_date} to {end_date}, limit={limit}")

    start_dt, end_dt = _parse_date_range(start_date, end_date)
    # Get recent posts
    all_posts = await post_repo.get_posts_in_interval(
        start_time=start_dt,
        end_time=end_dt,
        processing_status=models.ProcessingStatus.ACCEPTED,
    )
    all_posts.sort(key=lambda p: p.created_at, reverse=True)
    limited_posts = all_posts[:limit]

    post_items = []
    for post in limited_posts:
        # Get account username
        account = await account_repo.get_by(
            platform_type=post.platform_type, account_id=post.account_id
        )
        username = account.account_username if account else "unknown"

        post_items.append(
            TopPostItem(
                date=post.created_at.strftime("%Y-%m-%d"),
                handle=username,
                text=post.content,
                stats=extract_post_stats(post)
            )
        )

    return TopPostsResponse(
        posts=post_items, 
        period=f"{start_date} to {end_date}", 
        total_count=len(post_items)
    )


@router.get("/top-miners", response_model=TopMinersResponse)
async def get_top_miners(
    node_repo: Annotated[NodeRepository, Depends(get_node_repo)],
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    metagraph: Annotated[bt.Metagraph, Depends(get_metagraph)],
    start_date: str = Query(None, description="Start date (YYYY-MM-DD), defaults to 7 days ago"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD), defaults to today"),
    limit: int = Query(10, ge=1, le=200),
    score_calculator: ScoreCalculator = Depends(ScoreCalculator)
):
    """
    Get top-performing miners ranked by engagement metrics.

    Parameters:
    - metric: Ranking metric (total_engagement, views, likes, retweets)
    - period: Time period (24h, 7d, 30d, all)
    - limit: Maximum number of results (1-100)
    """
    # Use defaults if not provided
    if not start_date or not end_date:
        default_start, default_end = _get_default_date_range()
        start_date = start_date or default_start
        end_date = end_date or default_end

    start_dt, end_dt = _parse_date_range(start_date, end_date)

    all_miner_scores = await get_miner_scores(
        node_repo=node_repo,
        post_repo=post_repo,
        account_repo=account_repo,
        interaction_repo=interaction_repo,
        metagraph=metagraph,
        score_calculator=score_calculator
    )
    all_miner_scores = {
        miner_score_item.node_hotkey: miner_score_item.score for miner_score_item in all_miner_scores.miner_scores
    }
    miner_items: list[TopMinerItem] = []
    for miner_hotkey in metagraph.hotkeys:
        miner_uid = metagraph.hotkeys.index(miner_hotkey)

        # Get accounts for this miner
        accounts = await account_repo.find_many(node_hotkey=miner_hotkey)
        if not accounts:
            continue
        primary_account = accounts[0]

        # Calculate metrics for the time period
        retweet_count = 0
        reply_count = 0
        recent_activity_count = 0

        for account in accounts:
            # Get posts in the time period
            account_posts = await post_repo.get_posts_in_interval(
                start_time=start_dt,
                end_time=end_dt,
                account_id=account.account_id,
                processing_status=models.ProcessingStatus.ACCEPTED,
            )
            recent_activity_count += len(account_posts)

            # Count interactions for these posts
            for post in account_posts:
                post_interactions = await interaction_repo.get_interactions_in_interval(
                    start_time=start_dt,
                    end_time=end_dt,
                    post_id=post.post_id,
                    processing_status=models.ProcessingStatus.ACCEPTED,
                )
                recent_activity_count += len(post_interactions)

                for interaction in post_interactions:
                    if interaction.interaction_type == models.InteractionType.QUOTE:
                        retweet_count += 1
                    elif interaction.interaction_type == models.InteractionType.REPLY:
                        reply_count += 1

        miner_items.append(
            TopMinerItem(
                uid=miner_uid,
                handle=primary_account.account_username if primary_account else "unknown",
                score=all_miner_scores.get(miner_hotkey, 0.0),
                retweet_count=retweet_count,
                reply_count=reply_count,
                node_hotkey=miner_hotkey,
            )
        )

    # Sort by score
    miner_items.sort(key=lambda x: x.score, reverse=True)

    limited_miners = miner_items[:limit]

    return TopMinersResponse(
        miners=[item['item'] for item in limited_miners],
        period=f"{start_date} to {end_date}",
        total_count=len(limited_miners)
    )


async def get_subnet_stats(
    post_repo: Annotated[PostRepository, Depends(get_post_repo)],
    interaction_repo: Annotated[InteractionRepository, Depends(get_interaction_repo)],
    account_repo: Annotated[SocialAccountRepository, Depends(get_account_repo)],
    start_date: str = Query(None, description="Start date (YYYY-MM-DD), defaults to 7 days ago"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD), defaults to today"),
):
    if not start_date or not end_date:
        default_start, default_end = _get_default_date_range()
        start_date = start_date or default_start
        end_date = end_date or default_end

    logger.info(f"Getting subnet stats: {start_date} to {end_date}")

    start_dt, end_dt = _parse_date_range(start_date=start_date, end_date=end_date)

    all_posts = await post_repo.get_posts_in_interval(
        start_time=start_dt,
        end_time=end_dt,
        processing_status=models.ProcessingStatus.ACCEPTED,
    )
    all_interactions = await interaction_repo.get_interactions_in_interval(
        start_time=start_dt,
        end_time=end_dt,
        processing_status=models.ProcessingStatus.ACCEPTED,
    )

    active_miners = set()
    active_accounts = set()
    for post in all_posts:
        active_accounts.add(post.account_id)

        account = await account_repo.get_by_platform_id(
            platform_type=post.platform_type, account_id=post.account_id
        )
        if account and account.node_hotkey:
            active_miners.add(account.node_hotkey)

    aggregated_engagement_stats = sum([extract_post_stats(post) for post in all_posts])

    return SubnetStatsSummary(
        account_count=len(active_accounts),
        post_count=len(all_posts),
        interaction_count=len(all_interactions),
        engagement_stats=aggregated_engagement_stats
    )
