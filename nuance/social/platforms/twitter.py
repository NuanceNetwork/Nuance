# nuance/social/platforms/twitter.py
import aiohttp

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
        api_url = "https://api.datura.io/v1/twitter/user"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        query_params = {"user": username}
        async with self._get_session() as session:
            data = await async_http_request_with_retry(session, "GET", api_url, headers=headers, query_params=query_params)
        return data
    
    async def get_post(self, post_id: str) -> dict:
        """
        Retrieve twitter post/ tweet data using Datura API.
        """
        api_url = f"https://api.datura.io/v1/twitter/post/{post_id}"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        async with self._get_session() as session:
            data = await async_http_request_with_retry(session, "GET", api_url, headers=headers)
        return data
            
    async def get_all_posts(self, username: str) -> list[dict]:
        """
        Retrieve all posts for a given username using Datura API.
        """
        api_url = "https://apis.datura.ai/twitter"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {"query": f"from:{username}", "sort": "Latest", "count": 100}
        async with self._get_session() as session:
            data = await async_http_request_with_retry(session, "GET", api_url, params=payload, headers=headers)
        return data
    
    async def get_all_replies(self, username: str) -> list[dict]:
        """
        Retrieve all replies for a given username using Datura API.
        """
        api_url = "https://apis.datura.ai/twitter"
        headers = {
            "Authorization": self.DATURA_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {"query": f"to:{username}", "sort": "Latest", "count": 100}
        async with self._get_session() as session:
            data = await async_http_request_with_retry(session, "GET", api_url, params=payload, headers=headers)
        return data
    
    
        
                