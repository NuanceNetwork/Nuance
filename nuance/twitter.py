import datetime
import math
import shelve
from types import SimpleNamespace

import aiohttp
import bittensor as bt
from loguru import logger

import nuance.constants as constants
from nuance.llm import model
from nuance.settings import settings
from nuance.utils import http_request_with_retry, record_db_error, verify_signature


async def get_all_tweets(account: str) -> list[dict]:
    """
    Retrieve all tweets for a given account.
    """
    API_URL = "https://apis.datura.ai/twitter"
    headers = {"Authorization": settings.DATURA_API_KEY, "Content-Type": "application/json"}
    payload = {"query": f"from:{account}", "sort": "Latest"}
    async with aiohttp.ClientSession() as session:
        data = await http_request_with_retry(
            session, "POST", API_URL, json=payload, headers=headers
        )
        logger.info(f"✅ Fetched tweets for account {account} (total: {len(data)})")
        return data

async def get_all_replies(account: str) -> list[dict]:
    """
    Retrieve all tweet replies for a given account.
    """
    API_URL = "https://apis.datura.ai/twitter"
    headers = {"Authorization": settings.DATURA_API_KEY, "Content-Type": "application/json"}
    payload = {"query": f"to:{account}", "sort": "Latest"}
    async with aiohttp.ClientSession() as session:
        data = await http_request_with_retry(
            session, "POST", API_URL, json=payload, headers=headers
        )
        logger.info(f"✅ Fetched replies for account {account} (total: {len(data)})")
        return data
    
async def get_tweet(tweet_id: str) -> dict:
    """
    Retrieve tweet data using the Datura API.
    """
    API_URL = f"https://apis.datura.ai/twitter/{tweet_id}"
    headers = {"Authorization": settings.DATURA_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        data = await http_request_with_retry(session, "GET", API_URL, headers=headers)
        logger.info(f"✅ Fetched tweet {tweet_id}.")
        return data
    
async def process_reply(
    reply: dict, commit: SimpleNamespace, step_block: int, db: shelve.Shelf
) -> None:
    """
    Process a tweet reply, evaluate via LLM prompts, and update scores.
    Attaches the miner's hotkey to both the reply and its parent tweet.
    """
    try:
        reply_id = reply["id"]
        if reply_id in db["seen"]:
            logger.debug(f"⏩ Reply {reply_id} already processed.")
            return

        db["seen"].add(reply_id)
        db["total_seen"] += 1
        # Tag the reply with the miner's hotkey.
        reply["miner_hotkey"] = commit.hotkey
        db["child_replies"].append(reply)

        # Check if the reply comes from a verified username using the CSV list.
        username = reply["user"].get("screen_name", "").strip().lower()
        if username not in constants.VERIFIED_USERNAMES:
            logger.info(
                f"🚫 Reply {reply_id} from unverified username @{username}; skipping."
            )
            return

        account_created_at = datetime.strptime(
            reply["user"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
        )
        account_age = datetime.now(account_created_at.tzinfo) - account_created_at
        if account_age.days < 365:
            logger.info(
                f"⏳ Reply {reply_id} from account younger than 1 year; skipping."
            )
            return

        followers_count = reply["user"].get("followers_count", 1)
        child_text = reply.get("text", "")
        parent_id = reply.get("in_reply_to_status_id")
        if not parent_id:
            logger.info(f"❓ Reply {reply_id} has no parent tweet; skipping.")
            return

        parent_tweet = await get_tweet(tweet_id=parent_id)
        # Tag the parent tweet with the miner's hotkey.
        parent_tweet["miner_hotkey"] = commit.hotkey
        db["parent_tweets"].append(parent_tweet)
        parent_text = parent_tweet.get("text", "")
        parent_hotkey_sig = parent_tweet["user"].get("description", "")

        if not verify_signature(commit.hotkey, parent_hotkey_sig, commit.account_id):
            logger.warning(
                f"❌ Signature verification failed for {commit.hotkey} on tweet {parent_id}."
            )
            return

        prompt_about = constants.PROMPTS["nuance.constitution"]["topic"].format(
            tweet_text=parent_text
        )
        llm_response = await model(prompt_about)
        if llm_response.strip() != "True":
            logger.info(
                f"🗑️  Tweet {parent_id} is not about Bittensor; skipping reply {reply_id}."
            )
            return

        prompt_tone = constants.PROMPTS["nuance.constitution"]["tone"].format(
            child_text=child_text, parent_text=parent_text
        )
        llm_response = await model(prompt_tone)
        is_positive_response = llm_response.strip() == "True"

        increment = math.log(followers_count) if followers_count > 0 else 0
        if is_positive_response:
            db["scores"][commit.hotkey][step_block] += increment
            logger.info(
                f"👍 Reply {reply_id} positive. Score for {commit.hotkey} increased by {increment:.2f}."
            )
        else:
            db["scores"][commit.hotkey][step_block] -= increment
            logger.info(
                f"👎 Reply {reply_id} negative. Score for {commit.hotkey} decreased by {increment:.2f}."
            )
    except Exception as e:
        error_msg = f"❌ Error processing reply {reply.get('id', 'unknown')}: {e}"
        logger.error(error_msg)
        record_db_error(db, error_msg)