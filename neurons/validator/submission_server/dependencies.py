# neurons/validator/submission_server/dependencies.py
import json
from typing import Awaitable, TypeVar, Type, Callable, Optional

from fastapi import Request, HTTPException
from pydantic import BaseModel

from nuance.utils.epistula import verify_request
from nuance.utils.bittensor_utils import get_metagraph, get_wallet, is_validator
from nuance.utils.logging import logger

from .models import GossipData, MODEL_REGISTRY


# Generic type for any Pydantic model
T = TypeVar('T', dict, BaseModel)


def create_verified_dependency(
    data_model: Type[T],
    require_validator: bool = False,
    expected_receiver: Optional[str] = None
) -> Callable[[Request], Awaitable[tuple[T, dict]]]:
    """
    Factory to create a dependency that verifies Epistula signatures 
    and returns parsed data.
    
    Args:
        data_model: The Pydantic model to parse the body into, can also be a dict to skip parsing
        metagraph: Bittensor metagraph for verification
        require_validator: If True, only accept requests from validators
        expected_receiver: Can explicitly set to blank string to avoid receiver checking
        
    Returns:
        Dependency function for FastAPI
    """
    async def verify_and_parse(request: Request) -> tuple[T, dict]:
        """
        Verify Epistula signature and parse body.
        
        Returns:
            Tuple of (parsed_data, headers)
        """
        nonlocal expected_receiver

        metagraph = await get_metagraph()
        if expected_receiver is None:
            # Default to validator 's hotkey, can explicitly set to blank string to avoid
            self_hotkey = (await get_wallet()).hotkey.ss58_address
            expected_receiver = self_hotkey

        try:
            body = await request.body()
            headers = dict(request.headers)
            
            # Verify signature
            is_valid, error, sender_hotkey = verify_request(
                headers=headers,
                body=body,
                metagraph=metagraph,
                expected_receiver=expected_receiver
            )
            
            if not is_valid:
                raise HTTPException(403, f"Invalid request: {error}")
            
            # Check if validator required
            if require_validator and not await is_validator(sender_hotkey, metagraph):
                raise HTTPException(403, "Only validators can access this endpoint")
            
            # Check UUID
            uuid = headers.get("Epistula-Uuid") or headers.get("Epistula-Uuid".lower())
            if not uuid:
                raise HTTPException(400, "Missing Epistula-Uuid header")
            
            # Parse body
            data = json.loads(body)
            if data_model is dict:
                parsed_data = data  # skip parsing
            elif issubclass(data_model, BaseModel):
                parsed_data = data_model(**data)
            else:
                raise HTTPException(500, "Invalid data model type")
            
            return parsed_data, headers
            
        except HTTPException:
            raise
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON body")
        except Exception as e:
            logger.error(f"Error in verified dependency: {e}")
            raise HTTPException(400, f"Invalid data: {str(e)}")
    
    return verify_and_parse


def create_gossip_verified_dependency() -> Callable:
    """
    General gossip dependency that:
    - Verifies outer GossipData request
    - Extracts model name
    - Parses nested body with correct model
    """

    async def verify_gossip(request: Request) -> tuple[T, dict]:
        metagraph = await get_metagraph()

        outer_verifier = create_verified_dependency(GossipData, require_validator=True)
        gossip_data: GossipData
        gossip_data, gossip_headers = await outer_verifier(request)

        model_name = gossip_data.original_body_model
        if model_name not in MODEL_REGISTRY:
            raise HTTPException(400, f"Unsupported model: {model_name}")

        inner_model = MODEL_REGISTRY[model_name]
        # Since we currently do not re-broadcast, the expected receiver of the inner message is the one who broadcasted
        # Prepare inner data
        inner_body = bytes.fromhex(gossip_data.original_body_hex)
        inner_headers = gossip_data.original_headers
        expected_receiver = gossip_headers.get("Epistula-Signed-By") or gossip_headers.get("Epistula-Signed-By".lower())
        
        is_valid, error, sender_hotkey = verify_request(
            headers=inner_headers,
            body=inner_body,
            metagraph=metagraph,
            expected_receiver=expected_receiver,
        )
        if not is_valid:
            raise HTTPException(403, f"Invalid inner gossip request: {error}")

        # Parse
        try:
            data = json.loads(inner_body)
            if inner_model is dict:
                parsed = data
            elif issubclass(inner_model, BaseModel):
                parsed = inner_model(**data)
            else:
                raise HTTPException(500, "Invalid inner model type")
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON in inner request")

        return parsed, inner_headers

    return verify_gossip
