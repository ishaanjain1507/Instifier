# worker.py (minimal version using only API)
import httpx
import re
import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_sessionid():
    path = "session.json"
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
            return data.get("sessionid")
    return None

class InstagramScraper:
    def __init__(self):
        sessionid = load_sessionid()
        self.api_headers = {
            "x-ig-app-id": "936619743392459",
            "User-Agent": "Mozilla/5.0...",
            "Accept": "application/json",
        }
        if sessionid:
            self.api_headers["Cookie"] = f"sessionid={sessionid}"


    @staticmethod
    def parse_follower_count(text):
        if not text:
            return 0
        text = text.lower().replace(',', '').replace(' ', '')
        multipliers = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}
        try:
            match = re.search(r'([\d.]+)([kmb]?)', text)
            if match:
                number, suffix = match.groups()
                return int(float(number) * multipliers.get(suffix, 1))
            return int(text)
        except:
            return 0

    async def scrape_profile_api(self, username: str) -> Optional[Dict[str, Any]]:
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, headers=self.api_headers)
                response.raise_for_status()
                user = response.json().get("data", {}).get("user", {})
                if not user:
                    logger.warning(f"No user data found for {username}")
                    return None
            
                return {
                    "username": user.get("username", username),
                    "profile_url": f"https://www.instagram.com/{username}/",
                    "profile_pic_url": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
                    "follower_count": user.get("edge_followed_by", {}).get("count", 0),
                    "following_count": user.get("edge_follow", {}).get("count", 0),
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "source": "api"
                }

            except Exception as e:
                logger.error(f"Failed to scrape {username}: {e}")
                return None

# Shared instance
instagram_scraper = InstagramScraper()

async def scrape_profile(username: str, login_credentials: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    return await instagram_scraper.scrape_profile_api(username)
