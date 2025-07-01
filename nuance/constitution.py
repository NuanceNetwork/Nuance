# nuance/constitution.py
import asyncio
import csv
import json
import time
import traceback
from typing import Any, Optional
from collections import defaultdict

import aiohttp

import nuance.constants as cst
from nuance.utils.logging import logger
from nuance.utils.networking import async_http_request_with_retry


class ConstitutionStore:
    """
    Centralized store for fetching and caching constitution data from GitHub repository.
    Handles prompts, topic prompts, and verified users across platforms.
    """

    def __init__(self, repo_url: str = None, cache_ttl: int = None):
        # Parse GitHub repo URL to get API endpoints
        self.repo_url = repo_url or cst.NUANCE_CONSTITUTION_STORE_URL
        self.cache_ttl = cache_ttl or cst.NUANCE_CONSTITUTION_UPDATE_INTERVAL

        # Extract repo path for GitHub API
        self.repo_path = (
            self.repo_url.replace("https://github.com/", "")
            .replace("https://raw.githubusercontent.com/", "")
            .split("/")[:2]
        )
        if len(self.repo_path) == 2:
            self.repo_path = "/".join(self.repo_path)
        else:
            # Fallback for raw URLs with branch
            parts = self.repo_url.replace(
                "https://raw.githubusercontent.com/", ""
            ).split("/")
            self.repo_path = f"{parts[0]}/{parts[1]}"

        # Build base URLs
        self.api_base = f"https://api.github.com/repos/{self.repo_path}/contents"
        self.raw_base = f"https://raw.githubusercontent.com/{self.repo_path}/{cst.NUANCE_CONSTITUTION_BRANCH}"
        
        self.constitution_config_file_name = "constitution_config.json"

        # URL-based cache: {url: {"data": content, "last_updated": timestamp}}
        self._url_cache = {}

        # Locks
        self._url_cache_lock = defaultdict(asyncio.Lock)

    def _build_api_url(self, path: str) -> str:
        """Build API URL with branch reference"""
        return f"{self.api_base}/{path}?ref={cst.NUANCE_CONSTITUTION_BRANCH}"
    
    def _should_update_url_cache(self, url: str) -> bool:
        if url not in self._url_cache:
            return True        
        current_time = time.time()
        last_updated = self._url_cache[url]["last_updated"]
        return current_time - last_updated > self.cache_ttl
    
    async def _fetch_raw_content_from_relative_path(self, relative_path: str) -> str:
        # Build the raw content URL from relative path
        url = f"{self.raw_base}/{relative_path}"
        
        if not self._should_update_url_cache(url):
            # We can use the cached data
            return self._url_cache[url]["data"]
        else:
            # We may have to update data
            async with self._url_cache_lock[url]:
                # Double-check after acquiring lock
                if not self._should_update_url_cache(url):
                    return self._url_cache[url]["data"]
                
                try:
                    # Update cache data
                    async with aiohttp.ClientSession() as session:
                        content = await async_http_request_with_retry(session, "GET", url)
                    
                    self._url_cache[url] = {
                        "data": content,
                        "last_updated": time.time()
                    }
                    
                    logger.debug(f"✅ Fetched and cached: {relative_path}")
                    return content

                except Exception:
                    logger.error(f"❌ Error fetching {relative_path}: {traceback.format_exc()}")
                    # Return cached data if available, even if stale
                    if url in self._url_cache:
                        return self._url_cache[url]["data"]
                    raise
    
    async def get_constitution_config(self) -> Optional[dict]:
        try:
            config_content = await self._fetch_raw_content_from_relative_path(self.constitution_config_file_name)
            config_data = json.loads(config_content)
            
            logger.info("✅ Constitution config loaded")
            return config_data

        except Exception:
            logger.error(f"❌ Error getting constitution config: {traceback.format_exc()}")
            return None

    async def get_nuance_prompt(self) -> Optional[str]:
        try:
            return await self._fetch_raw_content_from_relative_path("post_evaluation_prompt.txt")
        except Exception:
            logger.error(f"❌ Failed to get nuance prompt: {traceback.format_exc()}")
            return None
        
    async def get_topic_prompts(self) -> dict[str, str]:
        """Get topic-specific prompts based on config"""
        try:
            config = await self.get_constitution_config()
            if not config or "topics" not in config:
                logger.warning("⚠️ No topics found in config")
                return {}

            topic_prompts = {}
            
            # Fetch prompts for each topic concurrently
            fetch_tasks = []
            topic_names = []
            
            for topic_name, topic_config in config["topics"].items():
                if "prompt_path" in topic_config and topic_config["prompt_path"]:
                    fetch_tasks.append(self._fetch_raw_content_from_relative_path(topic_config["prompt_path"]))
                    topic_names.append(topic_name)

            if fetch_tasks:
                prompt_contents = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                
                for topic_name, content in zip(topic_names, prompt_contents):
                    if not isinstance(content, Exception):
                        topic_prompts[topic_name] = content
                    else:
                        logger.error(f"❌ Failed to fetch prompt for topic {topic_name}: {content}")

            logger.info(f"✅ Topic prompts loaded: {len(topic_prompts)} topics")
            return topic_prompts

        except Exception:
            logger.error(f"❌ Error getting topic prompts: {traceback.format_exc()}")
            return {}
        
    async def get_topic_weights(self) -> dict[str, float]:
        try:
            config = await self.get_constitution_config()

            if not config or "topics" not in config:
                logger.warning("⚠️ No topics found in config")
                return {}

            topic_weights = {}
            for topic_name, topic_config in config["topic"].items():
                if "weight" in topic_config:
                    topic_weights[topic_name] = topic_config["weight"]

            return topic_weights

        except Exception:
            logger.error(f"❌ Error getting topic weights: {traceback.format_exc()}")
            return {}
        
    async def get_verified_users(
        self, platform: str = "twitter", category: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get complete verified user data (id, display_name, username, weight) for a platform and optionally a category.
        
        Args:
            platform: Platform name (e.g., "twitter")
            category: Optional topic category (e.g., "bittensor", "nuance_subnet")
                     If None, returns all users for the platform
        
        Returns:
            List of user data dictionaries
        """
        try:
            config = await self.get_constitution_config()
            if not config:
                logger.warning("⚠️ No config available")
                return []

            csv_paths = []
            
            if category:
                # Get topic-specific verified users
                if category in config.get("topics", {}):
                    topic_config = config["topics"][category]
                    if "verified_users" in topic_config and platform in topic_config["verified_users"]:
                        csv_paths = [topic_config["verified_users"][platform]]
                else:
                    logger.warning(f"⚠️ Topic category '{category}' not found in config")
                    return []
            else:
                # Get all verified users for platform
                if platform in config.get("platforms", {}):
                    csv_paths = config["platforms"][platform].get("verified_users", [])
                else:
                    logger.warning(f"⚠️ Platform '{platform}' not found in config")
                    return []

            if not csv_paths:
                logger.warning(f"⚠️ No verified users paths found for platform '{platform}', category '{category}'")
                return []

            # Fetch and parse CSV files concurrently
            all_users = []
            
            fetch_tasks = [self._fetch_raw_content_from_relative_path(csv_path) for csv_path in csv_paths]
            csv_contents = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            for csv_path, content in zip(csv_paths, csv_contents):
                if isinstance(content, Exception):
                    logger.error(f"❌ Failed to fetch {csv_path}: {content}")
                    continue
                
                try:
                    lines = content.splitlines()
                    if not lines:
                        continue
                    
                    reader = csv.DictReader(lines)
                    for row in reader:
                        if "id" in row and row["id"]:
                            user_data = {
                                "id": row["id"],
                                "display_name": row.get("display name", "").strip(),
                                "username": row.get("username", "").strip(),
                                "weight": float(row.get("weight", 1.0)),
                            }
                            all_users.append(user_data)
                    
                    logger.debug(f"✅ Processed {csv_path}: users added to list")
                    
                except Exception as e:
                    logger.error(f"❌ Error parsing CSV {csv_path}: {str(e)}")
                    continue

            logger.info(f"✅ Loaded {len(all_users)} verified users for platform '{platform}', category '{category}'")
            return all_users

        except Exception:
            logger.error(f"❌ Error getting verified users full data: {traceback.format_exc()}")
            return []

    def get_cache_status(self) -> dict[str, Any]:
        """Get detailed information about cache status"""
        current_time = time.time()
        
        url_cache_status = {}
        for url, cache_data in self._url_cache.items():
            url_cache_status[url] = {
                "last_updated": cache_data["last_updated"],
                "age_seconds": current_time - cache_data["last_updated"],
                "data_size": len(cache_data["data"]) if cache_data["data"] else 0,
            }
        
        
        return {
            "url_cache": url_cache_status,
            "total_cached_urls": len(self._url_cache),
        }

    async def get_file_content(self, file_path: str) -> Optional[str]:
        """Generic method to fetch any file from the constitution repo"""
        try:
            url = f"{self.raw_base}/{file_path}"
            async with aiohttp.ClientSession() as session:
                return await async_http_request_with_retry(session, "GET", url)
        except Exception:
            logger.error(
                f"❌ Error fetching file {file_path}: {traceback.format_exc()}"
            )
            return None


# Global instance
constitution_store = ConstitutionStore()
