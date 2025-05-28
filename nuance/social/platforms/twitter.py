# nuance/social/platforms/twitter.py
import aiohttp
from loguru import logger

from nuance.settings import settings
from nuance.social.platforms.base import BasePlatform
from nuance.utils.networking import async_http_request_with_retry


class TwitterPlatform(BasePlatform):
    
    def __init__(self):
        self.DATURA_API_KEY = settings.DATURA_API_KEY
        self._session = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp client session.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def _close_session(self):
        """
        Close the aiohttp client session.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            
    async def get_user(self, username: str) -> dict:
        """
        Retrieve twitter user data using Datura API.
        """
        api_url = "https://api.desearch.ai/twitter/user"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"user": username}
        session = await self._get_session()
        data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, params=query_params)
        return data
    
    async def get_post(self, post_id: str) -> dict:
        """
        Retrieve twitter post/ tweet data using Datura API.
        """
        api_url = "https://api.desearch.ai/twitter/post"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"id": post_id}
        session = await self._get_session()
        data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, params=query_params)
        return data
            
    async def get_all_posts(self, username: str) -> list[dict]:
        """
        Retrieve all posts for a given username using Datura API.
        """
        api_url = "https://api.desearch.ai/twitter"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"query": f"from:{username}", "sort": "Latest", "count": 100}
        session = await self._get_session()
        data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, params=query_params)
        return data
    
    async def get_all_replies(self, username: str) -> list[dict]:
        """
        Retrieve all replies for a given username using Datura API.
        """
        api_url = "https://api.desearch.ai/twitter"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"query": f"to:{username}", "sort": "Latest", "count": 100}
        session = await self._get_session()
        data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, params=query_params)
        return data
    
    async def get_all_quotes(self, account_id: str) -> list[dict]:
        """
        Retrieve all quotes for a given username using Datura API.
        """
        api_url = "https://api.desearch.ai/twitter"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"query": f"quoted_user_id:{account_id}", "sort": "Latest", "count": 100}
        session = await self._get_session()
        data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, params=query_params)
        logger.info(f"Found {len(data)} quotes for {account_id}")
        logger.debug(f"Quotes: {data}")
        return data
