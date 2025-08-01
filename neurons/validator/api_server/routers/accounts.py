from typing import Annotated
from fastapi import APIRouter, Depends

from neurons.validator.api_server.dependencies import (
    get_account_repo,
    get_node_repo,
)
from neurons.validator.api_server.models import AccountVerificationResponse
from nuance.database import (
    NodeRepository,
    SocialAccountRepository,
)
from nuance.utils.logging import logger


router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
)


@router.get(
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
