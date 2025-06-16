# neurons/validator/submission_server/rate_limiter.py
"""Stake-based rate limiting for submission server"""
import asyncio
import math
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import  Deque

from nuance.utils.logging import logger


class RateLimiter:
    """(Alpha) Stake-based rate limiter"""
    
    def __init__(
        self,
        base_limit_per_hour: int = 10,  # Base limit for minimal stake
        max_limit_per_hour: int = 100,  # Max limit for high stake
        cleanup_interval_seconds: int = 3600
    ):
        self.base_limit = base_limit_per_hour
        self.max_limit = max_limit_per_hour
        self.cleanup_interval = cleanup_interval_seconds
        
        # Track submissions by hotkey
        self.submissions: dict[str, Deque[datetime]] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    def calculate_rate_limit(self, stake: float) -> int:
        """
        Calculate rate limit based on stake.
        Higher stake = higher limit.
        
        Examples:
        - 0 Alpha = 10 submissions/hour
        - 100 Alpha = 50 submissions/hour  
        - 1000 Alpha = 200 submissions/hour
        - 10000+ Alpha = 1000 submissions/hour (max)
        """
        if stake <= 0:
            return self.base_limit
            
        # Logarithmic scaling: limit = base + (max-base) * log10(stake+1) / log10(10000)
        # Normalize stake to 0-1 range using log scale
        normalized = math.log10(stake + 1) / math.log10(10000)
        normalized = min(normalized, 1.0)  # Cap at 1
        
        # Calculate limit
        limit = int(self.base_limit + (self.max_limit - self.base_limit) * normalized)
        
        return limit
    
    async def check_and_update(self, hotkey: str, stake: float) -> tuple[bool, str, int]:
        """
        Check if hotkey can submit and update counter.
        Returns (allowed, message, current_limit)
        """
        # Calculate this miner's limit
        rate_limit = self.calculate_rate_limit(stake)
        
        async with self._lock:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            
            # Get submissions for this hotkey
            hotkey_submissions = self.submissions[hotkey]
            
            # Remove old submissions
            while hotkey_submissions and hotkey_submissions[0] < hour_ago:
                hotkey_submissions.popleft()
            
            # Check limit
            current_count = len(hotkey_submissions)
            if current_count >= rate_limit:
                return False, f"Rate limit exceeded: {current_count}/{rate_limit} per hour (stake: {stake:.1f} TAO)", rate_limit
            
            # Add new submission
            hotkey_submissions.append(now)
            return True, f"OK: {current_count + 1}/{rate_limit} per hour", rate_limit
    
    async def get_usage(self, hotkey: str, stake: float) -> dict[str, int]:
        """Get current usage stats for a hotkey"""
        rate_limit = self.calculate_rate_limit(stake)
        
        async with self._lock:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            
            # Count recent submissions
            hotkey_submissions = self.submissions[hotkey]
            current_count = sum(1 for ts in hotkey_submissions if ts > hour_ago)
            
            return {
                "current_count": current_count,
                "rate_limit": rate_limit,
                "remaining": max(0, rate_limit - current_count)
            }
    
    async def periodic_cleanup(self):
        """Periodically clean up old entries"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
    
    async def _cleanup(self):
        """Remove old entries to free memory"""
        async with self._lock:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            
            # Clean each hotkey's submissions
            empty_keys = []
            for hotkey, submissions in self.submissions.items():
                # Remove old submissions
                while submissions and submissions[0] < hour_ago:
                    submissions.popleft()
                
                # Mark empty keys for removal
                if not submissions:
                    empty_keys.append(hotkey)
            
            # Remove empty entries
            for key in empty_keys:
                del self.submissions[key]
            
            if empty_keys:
                logger.info(f"Rate limiter cleanup: removed {len(empty_keys)} empty entries")