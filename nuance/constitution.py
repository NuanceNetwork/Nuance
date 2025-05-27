# nuance/constitution.py
import asyncio
import csv
import time
import traceback
from typing import Any, Optional
from enum import Enum

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

        # Cache structure
        self._cache = {
            "nuance_prompt": {"data": None, "last_updated": None},
            "topic_prompts": {"data": {}, "last_updated": None},
            "verified_users": {"data": {}, "last_updated": None},  # platform
        }

        # Map categories to CSV files in constitution repo
        self.category_file_mapping = {
            "nuance_subnet": "const_followers.csv",
            "bittensor": "kaito_crypto_accounts.csv",
            "other": "legacy_verified_users.csv",
        }

        # Cache for verified users weights
        self.verified_users_by_platform_and_category: dict[str, dict[str, dict]] = {} # platform -> dict[category -> dict[id -> info]]

        # Locks for thread safety
        self._locks = {
            "nuance_prompt": asyncio.Lock(),
            "topic_prompts": asyncio.Lock(),
            "verified_users": asyncio.Lock(),
        }

    def _build_api_url(self, path: str) -> str:
        """Build API URL with branch reference"""
        return f"{self.api_base}/{path}?ref={cst.NUANCE_CONSTITUTION_BRANCH}"

    def _should_update_cache(self, cache_key: str) -> bool:
        """Check if cache needs updating"""
        cache = self._cache[cache_key]
        current_time = time.time()
        return (
            cache["last_updated"] is None
            or current_time - cache["last_updated"] > self.cache_ttl
        )

    def _update_cache(self, cache_key: str, data: Any) -> None:
        """Update cache with new data and timestamp"""
        self._cache[cache_key]["data"] = data
        self._cache[cache_key]["last_updated"] = time.time()

    async def get_nuance_prompt(self) -> Optional[str]:
        """Get the main nuance evaluation prompt"""
        if not self._should_update_cache("nuance_prompt"):
            return self._cache["nuance_prompt"]["data"]

        async with self._locks["nuance_prompt"]:
            # Double-check after acquiring lock
            if not self._should_update_cache("nuance_prompt"):
                return self._cache["nuance_prompt"]["data"]

            try:
                url = f"{self.raw_base}/post_evaluation_prompt.txt"
                async with aiohttp.ClientSession() as session:
                    prompt = await async_http_request_with_retry(session, "GET", url)

                self._update_cache("nuance_prompt", prompt)
                logger.info("✅ Nuance evaluation prompt updated successfully")
                return prompt

            except Exception as e:
                logger.error(
                    f"❌ Error fetching nuance prompt: {traceback.format_exc()}"
                )
                return self._cache["nuance_prompt"]["data"]

    async def get_topic_prompts(self) -> dict[str, str]:
        """Get all topic-specific prompts from topic_relevance_prompts directory"""
        if not self._should_update_cache("topic_prompts"):
            return self._cache["topic_prompts"]["data"]

        async with self._locks["topic_prompts"]:
            # Double-check after acquiring lock
            if not self._should_update_cache("topic_prompts"):
                return self._cache["topic_prompts"]["data"]

            try:
                # Get list of files in topic_relevance_prompts directory
                api_url = self._build_api_url("topic_relevance_prompts")

                async with aiohttp.ClientSession() as session:
                    # Get directory listing
                    files_response = await async_http_request_with_retry(
                        session, "GET", api_url
                    )

                    # Filter for .txt files and extract topic names
                    topic_files = {}
                    for file_info in files_response:
                        if isinstance(file_info, dict) and file_info.get(
                            "name", ""
                        ).endswith("_prompt.txt"):
                            topic_name = file_info["name"].replace("_prompt.txt", "")
                            topic_files[topic_name] = file_info["download_url"]

                    # Fetch all topic prompts concurrently
                    fetch_tasks = [
                        async_http_request_with_retry(session, "GET", url)
                        for url in topic_files.values()
                    ]

                    prompt_contents = await asyncio.gather(
                        *fetch_tasks, return_exceptions=True
                    )

                    # Map topic names to their prompt content
                    topic_prompts = {}
                    for (topic_name, _), content in zip(
                        topic_files.items(), prompt_contents
                    ):
                        if not isinstance(content, Exception):
                            topic_prompts[topic_name] = content
                        else:
                            logger.error(
                                f"❌ Failed to fetch prompt for topic {topic_name}: {content}"
                            )

                self._update_cache("topic_prompts", topic_prompts)
                logger.info(
                    f"✅ Topic prompts updated: {len(topic_prompts)} topics loaded"
                )
                return topic_prompts

            except Exception as e:
                logger.error(
                    f"❌ Error fetching topic prompts: {traceback.format_exc()}"
                )
                return self._cache["topic_prompts"]["data"]

    async def get_verified_user_ids(self, platform: str = "twitter") -> set[str]:
        """Get only verified user IDs for a specific platform"""
        full_data = await self._get_verified_users_data(platform)
        return {user["id"] for user in full_data}

    async def get_verified_users_by_platform_and_category(
        self, platform: str = "twitter"
    ) -> dict[str, dict[str, dict]]:
        """
        Get verified users organized by category with their info.
        
        Returns:
            Dict[category, Dict[user_id, user_info]]
        """
        if self._should_update_cache("verified_users"):
            # Update cache and rebuild organized structure
            await self._get_verified_users_data(platform)
            
            # Build organized structure by category
            platform_data = {}
            for category, source_file in self.category_file_mapping.items():
                platform_data[category] = {}
                
                # Get all users from this platform
                all_users = self._cache["verified_users"]["data"].get(platform, [])
                
                # Filter users by source file (category)
                for user in all_users:
                    if user.get("source_file") == source_file:
                        platform_data[category][user["id"]] = user
            
            # Cache the organized structure
            self.verified_users_by_platform_and_category[platform] = platform_data
            
        else:
            # Return cached organized structure, build if doesn't exist
            if platform not in self.verified_users_by_platform_and_category:
                platform_data = {}
                for category, source_file in self.category_file_mapping.items():
                    platform_data[category] = {}
                    
                    # Get all users from this platform
                    all_users = self._cache["verified_users"]["data"].get(platform, [])
                    
                    # Filter users by source file (category)
                    for user in all_users:
                        if user.get("source_file") == source_file:
                            platform_data[category][user["id"]] = user
                
                self.verified_users_by_platform_and_category[platform] = platform_data

        return self.verified_users_by_platform_and_category.get(platform, {})

    async def get_verified_users_full_data(
        self, platform: str = "twitter"
    ) -> list[dict[str, str]]:
        """Get complete verified user data (id, display_name, username, weight)"""
        return await self._get_verified_users_data(platform)

    async def _get_verified_users_data(
        self, platform: str = "twitter"
    ) -> list[dict[str, str]]:
        """Internal method to get complete verified users data with caching"""
        if not self._should_update_cache("verified_users"):
            return self._cache["verified_users"]["data"].get(platform, [])

        async with self._locks["verified_users"]:
            # Double-check after acquiring lock
            if not self._should_update_cache("verified_users"):
                return self._cache["verified_users"]["data"].get(platform, [])

            try:
                # Get current cached data to update incrementally
                all_platform_data = self._cache["verified_users"]["data"].copy()

                # Fetch users for the specific platform
                platform_users = await self._fetch_platform_verified_users(platform)
                all_platform_data[platform] = platform_users

                self._update_cache("verified_users", all_platform_data)
                logger.info(
                    f"✅ Verified users updated for {platform}: {len(platform_users)} users"
                )
                return platform_users

            except Exception as e:
                logger.error(
                    f"❌ Error fetching verified users for {platform}: {traceback.format_exc()}"
                )
                return self._cache["verified_users"]["data"].get(platform, [])

    async def _fetch_platform_verified_users(
        self, platform: str
    ) -> list[dict[str, str]]:
        """Fetch complete verified user data for a specific platform from CSV files"""
        api_url = self._build_api_url(f"verified_users/{platform}")

        async with aiohttp.ClientSession() as session:
            # Get list of CSV files in the platform directory
            files_response = await async_http_request_with_retry(
                session, "GET", api_url
            )

            all_users = []
            csv_files = [
                f
                for f in files_response
                if isinstance(f, dict)
                and f.get("name", "").endswith(".csv")
                and f.get("download_url")
            ]

            # Process each CSV file
            for csv_file in csv_files:
                try:
                    csv_content = await async_http_request_with_retry(
                        session, "GET", csv_file["download_url"]
                    )

                    # Parse CSV and extract complete user data
                    lines = csv_content.splitlines()
                    if not lines:
                        continue

                    reader = csv.DictReader(lines)
                    for row in reader:
                        if "id" in row and row["id"]:  # Ensure we have a valid ID
                            user_data = {
                                "id": row["id"],
                                "display_name": row.get("display name", "").strip(),
                                "username": row.get("username", "").strip(),
                                "weight": row.get("weight", "1").strip(),
                                "source_file": csv_file[
                                    "name"
                                ],  # Track which file this came from
                            }
                            all_users.append(user_data)

                    logger.debug(
                        f"✅ Processed {csv_file['name']}: {len([r for r in csv.DictReader(csv_content.splitlines()) if r.get('id')])} users"
                    )

                except Exception as e:
                    logger.error(f"❌ Error processing {csv_file['name']}: {str(e)}")
                    continue

            logger.info(
                f"✅ Loaded {len(all_users)} verified users from {len(csv_files)} CSV files for {platform}"
            )
            return all_users

    async def refresh_all_caches(self) -> None:
        """Force refresh all caches"""
        logger.info("🔄 Refreshing all constitution caches...")

        # Reset cache timestamps to force updates
        for cache_key in self._cache:
            self._cache[cache_key]["last_updated"] = None

        # Trigger updates
        await asyncio.gather(
            self.get_nuance_prompt(),
            self.get_topic_prompts(),
            self._get_verified_users_data("twitter"),
            return_exceptions=True,
        )

        logger.info("✅ All constitution caches refreshed")

    def get_cache_status(self) -> dict[str, dict[str, Any]]:
        """Get detailed information about cache status"""
        status = {}
        current_time = time.time()

        for cache_key, cache_data in self._cache.items():
            data = cache_data["data"]
            last_updated = cache_data["last_updated"]

            status[cache_key] = {
                "has_data": data is not None
                and (isinstance(data, (dict, set)) and len(data) > 0 or data),
                "last_updated": last_updated,
                "age_seconds": current_time - last_updated if last_updated else None,
                "needs_update": self._should_update_cache(cache_key),
                "data_summary": self._get_data_summary(cache_key, data),
            }

        return status

    def _get_data_summary(self, cache_key: str, data: Any) -> str:
        """Get a summary description of cached data"""
        if data is None:
            return "No data"

        if cache_key == "nuance_prompt":
            return f"Prompt loaded ({len(data)} chars)" if data else "No prompt"
        elif cache_key == "topic_prompts":
            return f"{len(data)} topics: {list(data.keys())}" if data else "No topics"
        elif cache_key == "verified_users":
            if not data:
                return "No users"
            summary = {}
            for platform, users in data.items():
                if isinstance(users, list):
                    summary[platform] = f"{len(users)} users"
                else:
                    summary[platform] = f"{len(users)} users (legacy format)"
            return summary

        return str(type(data))

    async def get_file_content(self, file_path: str) -> Optional[str]:
        """Generic method to fetch any file from the constitution repo"""
        try:
            url = f"{self.raw_base}/{file_path}"
            async with aiohttp.ClientSession() as session:
                return await async_http_request_with_retry(session, "GET", url)
        except Exception as e:
            logger.error(
                f"❌ Error fetching file {file_path}: {traceback.format_exc()}"
            )
            return None


# Global instance
constitution_store = ConstitutionStore()
