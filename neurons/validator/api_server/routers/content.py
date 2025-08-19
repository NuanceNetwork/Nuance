from typing import Annotated, Awaitable, Callable

from fastapi import APIRouter, Body, Depends, Request

from neurons.validator.api_server.dependencies import (
    get_nuance_checker,
    get_topic_checker,
)
from neurons.validator.api_server.rate_limiter import limiter

router = APIRouter(
    tags=["content"],
)


@router.post("/nuance/check", response_model=bool)
@limiter.limit("2/minute")
async def check_nuance(
    request: Request,
    content: Annotated[str, Body(..., embed=True)],
    nuance_checker: Annotated[
        Callable[[str], Awaitable[bool]], Depends(get_nuance_checker)
    ],
):
    """
    Check text against nuance criteria (rate-limited to 2 requests per minute)
    """
    is_nuanced = await nuance_checker(content)

    return is_nuanced


@router.post("/topic/check", response_model=dict)
@limiter.limit("2/minute")
async def check_topic(
    request: Request,
    content: Annotated[str, Body(..., embed=True)],
    topic: Annotated[str, Body(..., embed=True)],
    topic_checker: Annotated[
        Callable[[str, str], Awaitable[bool]], Depends(get_topic_checker)
    ],
):
    """
    Check text against nuance criteria (rate-limited to 2 requests per minute)
    """
    is_this_topic, is_valid_topic = await topic_checker(content=content, topic=topic)

    return {
        "is_this_topic": is_this_topic,
        "is_valid_topic": is_valid_topic,
    }
