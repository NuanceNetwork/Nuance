import datetime
import asyncio

from tqdm.asyncio import tqdm

import nuance.models as models
from nuance.social.content_provider import SocialContentProvider
from nuance.database.engine import get_db_session
from nuance.database import PostRepository


def _parse_date_range(start_date: str, end_date: str) -> tuple[datetime.datetime, datetime.datetime]:
    """
    Parse start_date and end_date strings to datetime objects with UTC timezone.
    Ensures that the end_date includes the full day.
    """
    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
        # Include the entire end date (23:59:59)
        end_dt = end_dt + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)

        if start_dt >= end_dt:
            raise ValueError("start_date must be before end_date")

        return start_dt, end_dt

    except ValueError as e:
        raise ValueError(f"Invalid date range: {e}") from e


async def update_post_statistics(
    start_date: str,
    end_date: str,
    platform: models.PlatformType,
    batch_size: int = 10,
    verbose: bool = True,
):
    """
    Update post statistics in a given date range for a specific platform.

    Args:
        start_date: YYYY-MM-DD string
        end_date: YYYY-MM-DD string
        platform: PlatformType enum
        batch_size: Max number of concurrent requests
        verbose: Print progress if True
    """
    post_repo = PostRepository(session_factory=get_db_session)
    social_provider = SocialContentProvider()

    # Parse date range
    start_dt, end_dt = _parse_date_range(start_date=start_date, end_date=end_date)

    # Load posts from DB
    all_posts = await post_repo.get_posts_in_interval(
        start_time=start_dt,
        end_time=end_dt,
        processing_status=models.ProcessingStatus.ACCEPTED,
    )

    if verbose:
        print(f"Found {len(all_posts)} posts between {start_date} and {end_date}")

    # Sort newest first
    posts_sorted_by_date = sorted(
        all_posts, key=lambda post: post.created_at, reverse=True
    )

    semaphore = asyncio.Semaphore(batch_size)

    # Run updates in parallel batch size
    async def _process_post(
        post: models.Post,
        platform: models.PlatformType,
        social_provider: SocialContentProvider,
        post_repo: PostRepository,
        semaphore: asyncio.Semaphore,
        verbose: bool = True,
    ):
        """Fetch updated stats for one post and save it back to DB."""
        async with semaphore:
            try:
                latest_post = await social_provider.get_post(
                    platform=platform, post_id=post.post_id
                )
                post.extra_data = latest_post.extra_data
                await post_repo.upsert(post)
                if verbose:
                    print(f"✅ Updated post {post.post_id}")
            except Exception as e:
                print(f"❌ Failed to update post {getattr(post, 'post_id', '?')}: {e}")

    tasks = [
        _process_post(post, platform, social_provider, post_repo, semaphore, verbose)
        for post in posts_sorted_by_date
    ]

    if verbose:
        await tqdm.gather(*tasks, desc="Updating posts", unit="post")
    else:
        await asyncio.gather(*tasks)


async def main():
    # Example: Update posts from the last 3 months
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    await update_post_statistics(
        start_date=start_date,
        end_date=end_date,
        platform=models.PlatformType.TWITTER,  # change to your platform
        batch_size=20,
        verbose=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
