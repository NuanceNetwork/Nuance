import os
import asyncio
from collections import defaultdict
import json
import shelve
import traceback
from typing import Any

from aiohttp import web
import bittensor as bt
from loguru import logger

def serialize_db_data(data: Any) -> Any:
    """
    Recursively convert shelve data to JSON-serializable format.
    """
    if isinstance(data, dict):
        return {k: serialize_db_data(v) for k, v in data.items()}
    elif isinstance(data, set):
        return list(data)
    elif isinstance(data, defaultdict):
        return dict(data)
    elif hasattr(data, "__dict__"):
        return serialize_db_data(data.__dict__)
    elif isinstance(data, list):
        return [serialize_db_data(item) for item in data]
    else:
        return data

async def handle_db(request: web.Request) -> web.Response:
    """
    HTTP handler to return DB contents as JSON.
    """
    db_filename = request.app["db_filename"]
    try:
        with shelve.open(db_filename, flag="r") as db:
            data = {key: serialize_db_data(db[key]) for key in db.keys()}
        return web.json_response(data)
    except Exception as e:
        e = traceback.format_exc()
        logger.error(f"❌ Error reading DB: {e}")
        return web.json_response({"error": str(e)}, status=500)
    
async def handle_hotkey(request: web.Request) -> web.Response:
    """
    HTTP handler to return all parent tweets and replies associated with a specific hotkey as JSON.
    """
    hotkey = request.match_info.get("hotkey")
    db_filename = request.app["db_filename"]
    try:
        with shelve.open(db_filename, flag="r") as db:
            parent_tweets = db.get("parent_tweets", {})
            child_replies = db.get("child_replies", [])
            filtered_parents = [
                tweet for tweet in parent_tweets.values() if tweet.get("miner_hotkey") == hotkey
            ]
            filtered_replies = [
                reply for reply in child_replies if reply.get("miner_hotkey") == hotkey
            ]
            response_data = {
                "hotkey": hotkey,
                "parent_tweets": filtered_parents,
                "child_replies": filtered_replies,
            }
        return web.json_response(response_data)
    except Exception as e:
        e = traceback.format_exc()
        logger.error(f"❌ Error in handle_hotkey: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def run_api_server(db_filename: str, port: int, shutdown_event: asyncio.Event) -> None:
    """
    Start an aiohttp web server exposing DB endpoints.
    The server is bound to localhost (127.0.0.1) for local access.
    """
    app = web.Application()
    app["db_filename"] = db_filename
    app.router.add_get("/db", handle_db)
    app.router.add_get("/hotkey/{hotkey}", handle_hotkey)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    logger.info(f"🚀 API server starting on http://127.0.0.1:{port}")
    await site.start()
    while not shutdown_event.is_set():
        await asyncio.sleep(1)
    await runner.cleanup()