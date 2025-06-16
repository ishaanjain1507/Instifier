import asyncio
import logging
from scraper.worker import InstagramScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

async def main():
    scraper = InstagramScraper()
    username = "therock"  # or "virat.kohli" etc.
    result = await scraper.scrape_profile_dom(username, login_credentials=None)
    if result:
        print("Scraped data keys:", result.keys())
        print("Sample:", {k: result[k] for k in ("username", "name", "follower_count", "bio")})
    else:
        print("Failed to scrape DOM for", username)

if __name__ == "__main__":
    asyncio.run(main())
