import csv
import time
import datetime
import math
import shelve
import traceback
from types import SimpleNamespace

import aiohttp
from loguru import logger

import nuance.constants as constants
from nuance.llm import model, get_nuance_prompt
from nuance.settings import settings
from nuance.utils import http_request_with_retry, record_db_error, verify_signature

twitter_verified_users_cache = {
    "verified_users": set(),
    "last_updated": None
}

async def get_twitter_verified_users():
    """
    Retrieve a list of verified Twitter users.
    """
    current_time = time.time()
    if twitter_verified_users_cache["last_updated"] is None or current_time - twitter_verified_users_cache["last_updated"] > constants.NUANCE_CONSTITUTION_UPDATE_INTERVAL:
        # Update the cache if it's older than the update interval
        try:
            twitter_verified_users_url = constants.NUANCE_CONSTITUTION_STORE_URL + "/verified_users/twitter_verified_users.csv"
            async with aiohttp.ClientSession() as session:
                twitter_verified_users_data = await http_request_with_retry(session, "GET", twitter_verified_users_url)
            
            # Process the CSV data
            lines = twitter_verified_users_data.splitlines()
            reader = csv.DictReader(lines)
            twitter_verified_users_cache["verified_users"] = {row['username'] for row in reader if 'username' in row}
            
            logger.debug(f"✅ Fetched verified Twitter users: {twitter_verified_users_cache['verified_users']}")
            twitter_verified_users_cache["last_updated"] = current_time
        except Exception as e:
            logger.error(f"❌ Error fetching verified Twitter users: {traceback.format_exc()}")
            
    return twitter_verified_users_cache["verified_users"]

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
    payload = {"query": f"to:{account}", "sort": "Latest", "count": 100}
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
    API_URL = f"https://apis.datura.ai/twitter/post?id={tweet_id}"
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

        # Tag the reply with the miner's hotkey.
        reply["miner_hotkey"] = commit.hotkey

        # 1. Reply condition checking
        # 1.1 Check if the reply comes from a verified username using the CSV list.
        username = reply["user"].get("username", "").strip().lower()
        verified_users = await get_twitter_verified_users()
        if username not in verified_users:
            logger.info(
                f"🚫 Reply {reply_id} from unverified username @{username}; skipping."
            )
            raise Exception(f"Reply {reply_id} from unverified username @{username}; skipping.")

        # 1.2 Check if the reply comes from an account younger than 1 year.
        account_created_at = datetime.datetime.strptime(
            reply["user"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
        )
        account_age = datetime.datetime.now(account_created_at.tzinfo) - account_created_at
        if account_age.days < 365:
            logger.info(
                f"⏳ Reply {reply_id} from account younger than 1 year; skipping."
            )
            raise Exception(f"Reply {reply_id} from account younger than 1 year; skipping.")
        
        # 2. Get post
        child_text = reply.get("text", "")
        parent_id = reply.get("in_reply_to_status_id")
        if not parent_id:
            logger.info(f"❓ Reply {reply_id} has no parent tweet; skipping.")
            raise Exception(f"Reply {reply_id} has no parent tweet; skipping.")

        parent_tweet = await get_tweet(tweet_id=parent_id)
        # Tag the parent tweet with the miner's hotkey.
        parent_tweet["miner_hotkey"] = commit.hotkey
        parent_text = parent_tweet.get("text", "")
        parent_hotkey_sig = parent_tweet["user"].get("description", "")

        # 3. Signature verification
        if not verify_signature(commit.hotkey, parent_hotkey_sig, commit.account_id):
            logger.warning(
                f"❌ Signature verification failed for {commit.hotkey} on tweet {parent_id}."
            )
            raise Exception(f"Signature verification failed for {commit.hotkey} on tweet {parent_id}.")
        
        # 4. Post content checking
        # Check if post already exists in db
        if parent_id in db["seen"]:
            logger.info(f"🗑️  Tweet {parent_id} seen, skipping content check.")
            if db["parent_tweets"][parent_id]["nuance_accepted"] and db["parent_tweets"][parent_id]["bittensor_relevance_accepted"]:
                # Update parent tweet
                parent_tweet["nuance_accepted"] = True
                parent_tweet["bittensor_relevance_accepted"] = True
                db["parent_tweets"][parent_id] = parent_tweet
            else:
                logger.info(f"🗑️  Parent tweet {parent_id} not accepted, skipping reply {reply_id}.")
                raise Exception(f"Parent tweet {parent_id} not accepted, skipping reply {reply_id}.")
        else:
            db["parent_tweets"][parent_id] = parent_tweet
            nuance_prompt = await get_nuance_prompt()
            # 4.1 Nuance checking
            prompt_nuance = nuance_prompt["post_evaluation_prompt"].format(
                tweet_text=parent_text
            )
            llm_response = await model(prompt_nuance)
            if llm_response.strip().lower() != "approve":
                db["parent_tweets"][parent_id]["nuance_accepted"] = False
                logger.info(f"🗑️  Parent tweet {parent_id} is not nuanced; skipping reply {reply_id}.")
                raise Exception(f"Parent tweet {parent_id} is not nuanced; skipping reply {reply_id}.")
            
            # 4.2 Check if the parent tweet is about Bittensor
            prompt_about = nuance_prompt["bittensor_relevance_prompt"].format(
                tweet_text=parent_text
            )
            llm_response = await model(prompt_about)
            if llm_response.strip().lower() != "true":
                db["parent_tweets"][parent_id]["bittensor_relevance_accepted"] = False
                logger.info(
                    f"🗑️  Parent tweet {parent_id} is not about Bittensor; skipping reply {reply_id}."
                )
                raise Exception(f"Parent tweet {parent_id} is not about Bittensor; skipping reply {reply_id}.")
            # Post accepted, add to db
            parent_tweet["nuance_accepted"] = True
            parent_tweet["bittensor_relevance_accepted"] = True
        
        # 5. Tone checkin
        tone_prompt_template = "Analyze the following Twitter conversation:\n\nOriginal Tweet: {parent_text}\n\nReply Tweet: {child_text}\n\nIs the reply positive, supportive, or constructive towards the original tweet? Respond with only 'positive', 'neutral', or 'negative'."
        prompt_tone = tone_prompt_template.format(
            child_text=child_text, parent_text=parent_text
        )
        llm_response = await model(prompt_tone)
        is_negative_response = llm_response.strip() == "negative"

        # 6. Score update
        followers_count = reply["user"].get("followers_count", 1)
        increment = math.log(followers_count) if followers_count > 0 else 0
        db["scores"][commit.hotkey].setdefault(step_block, 0)
        if is_negative_response:
            db["scores"][commit.hotkey][step_block] += increment
            logger.info(
                f"👎 Reply {reply_id} negative. Score for {commit.hotkey} decreased by {increment:.2f}."
            )
        else:
            db["scores"][commit.hotkey][step_block] -= increment
            logger.info(
                f"👍 Reply {reply_id} positive/neutral. Score for {commit.hotkey} increased by {increment:.2f}."
            )
            
    except (aiohttp.ClientError, KeyError) as e:
        error_msg = f"❌ {traceback.format_exc()}"
        logger.error(error_msg)
        record_db_error(db, error_msg)
        return
    except Exception as e:
        error_msg = f"❌ Error processing reply {reply.get('id', 'unknown')}: {traceback.format_exc()}"
        logger.error(error_msg)
        record_db_error(db, error_msg)


    # Update db if the reply is successfully processed
    db["seen"].add(parent_id)
    db["seen"].add(reply_id)
    db["total_seen"] += 1
    db["child_replies"].append(reply)