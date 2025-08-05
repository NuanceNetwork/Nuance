from typing import Optional
from nuance.models import PlatformType, Post, Interaction
from neurons.validator.api_server.models import EngagementStats, TwitterEngagementStats


def convert_or_none(value, target_type):
    return target_type(value) if value is not None else None


def extract_twitter_post_stats(post: Post) -> TwitterEngagementStats:
    if not post.extra_data or post.platform_type != PlatformType.TWITTER:
        return TwitterEngagementStats()

    data = {
        field: convert_or_none(post.extra_data.get(field))
        for field in TwitterEngagementStats.model_fields.keys()
    }

    return TwitterEngagementStats(**data)


def extract_twitter_interaction_stats(
    interaction: Interaction,
) -> TwitterEngagementStats:
    if not interaction.extra_data or interaction.platform_type != PlatformType.TWITTER:
        return TwitterEngagementStats()

    data = {
        field: convert_or_none(interaction.extra_data.get(field))
        for field in TwitterEngagementStats.model_fields.keys()
    }

    return TwitterEngagementStats(**data)


def extract_post_stats(post: Post) -> Optional[EngagementStats]:
    if post.platform_type == PlatformType.TWITTER:
        return extract_twitter_post_stats(post)
    else:
        return None
