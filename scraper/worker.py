import asyncio
import logging
import json
import httpx
from datetime import datetime, timezone
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from pymongo.errors import PyMongoError
from database.mongo import creators_collection as collection  # Ensure MongoDB client is configured

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_follower_count(text):
    """Parse follower count with robust handling."""
    try:
        text = text.lower().replace(',', '').replace(' ', '')
        multiplier = 1
        if 'k' in text:
            multiplier = 1_000
            text = text.replace('k', '')
        elif 'm' in text:
            multiplier = 1_000_000
            text = text.replace('m', '')
        elif 'b' in text:
            multiplier = 1_000_000_000
            text = text.replace('b', '')
        return int(float(text) * multiplier)
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to parse follower count '{text}': {e}")
        return 0

async def scrape_profile_api(username):
    """Scrape profile data using Instagram's hidden API."""
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "x-ig-app-id": "936619743392459",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "*/*",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json().get("data", {}).get("user", {})
            return {
                "username": data.get("username", username),
                "profile_url": f"https://www.instagram.com/{username}/",
                "follower_count": data.get("edge_followed_by", {}).get("count", 0),
                "bio": data.get("biography", ""),
                "posts": [
                    {
                        "image_url": edge["node"].get("display_url", ""),
                        "likes": edge["node"].get("edge_liked_by", {}).get("count", 0),
                        "comments": edge["node"].get("edge_media_to_comment", {}).get("count", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    for edge in data.get("edge_owner_to_timeline_media", {}).get("edges", [])[:3]
                ],
                "engagement_rate": 0.0,  # Calculate later
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"API scrape failed for {username}: {e}")
            return None

async def scrape_profile_dom(username, max_posts=3, timeout=30000, max_retries=2):
    """Scrape profile data using Playwright DOM scraping."""
    url = f"https://www.instagram.com/{username}/"
    logger.info(f"Scraping profile via DOM: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            # proxy={"server": "http://your_proxy:port"}  # Uncomment for proxy
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for attempt in range(max_retries + 1):
            try:
                # Navigate to profile
                await page.goto(url, timeout=timeout, wait_until="networkidle")

                # Save debug files
                await page.screenshot(path=f"debug_{username}.png")
                html = await page.content()
                with open(f"debug_{username}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Saved debug files for {username}")

                # Check for login prompt
                login_prompt = await page.locator("text=/Log In|Login/i").count()
                if login_prompt:
                    logger.error(f"Login required for {username}. Falling back to API.")
                    return None

                # Check for private account
                private_account = await page.locator("text=/This Account is Private/i").count()
                if private_account:
                    logger.warning(f"Profile {username} is private. Skipping.")
                    return None

                # Bio
                bio = ""
                try:
                    bio_selector = "header section div.x3nfvp2 span"  # Updated
                    await page.wait_for_selector(bio_selector, timeout=5000)
                    bio = await page.locator(bio_selector).text_content()
                except PlaywrightTimeoutError:
                    logger.warning(f"Bio not found for {username}")

                # Followers
                followers = 0
                try:
                    followers_selector = "ul li a[href*='/followers/'] span span"  # Updated
                    await page.wait_for_selector(followers_selector, timeout=5000)
                    followers_text = await page.locator(followers_selector).text_content()
                    followers = parse_follower_count(followers_text)
                except PlaywrightTimeoutError:
                    logger.warning(f"Followers not found for {username}")

                # Posts
                posts_data = []
                try:
                    post_selector = "article div._aabd._aa8k a"  # Updated
                    await page.wait_for_selector(post_selector, timeout=5000)
                    post_elements = await page.locator(post_selector).element_handles()

                    for i, post in enumerate(post_elements[:max_posts]):
                        try:
                            await post.click()
                            await page.wait_for_selector("article section", timeout=5000)

                            # Likes
                            likes = 0
                            try:
                                likes_selector = "section._ae5m div span a span"  # Updated
                                likes_text = await page.locator(likes_selector).first.text_content()
                                likes = int(likes_text.replace(',', '').split()[0])
                            except (PlaywrightTimeoutError, ValueError):
                                logger.warning(f"Could not parse likes for post {i+1} of {username}")

                            # Comments
                            comments_count = 0
                            try:
                                comments_selector = "ul._a9zs li div"  # Updated
                                comments = await page.locator(comments_selector).all_text_contents()
                                comments_count = len(comments)
                            except PlaywrightTimeoutError:
                                logger.warning(f"Could not parse comments for post {i+1} of {username}")

                            # Image URL
                            img_url = ""
                            try:
                                img_selector = "article div._aagv img"  # Updated
                                img_url = await page.locator(img_selector).first.get_attribute("src")
                            except PlaywrightTimeoutError:
                                logger.warning(f"Image URL not found for post {i+1} of {username}")

                            posts_data.append({
                                "image_url": img_url,
                                "likes": likes,
                                "comments": comments_count,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })

                            # Close modal
                            await page.locator("svg[aria-label='Close']").click()
                            await page.wait_for_timeout(1000)
                        except Exception as e:
                            logger.error(f"Error scraping post {i+1} for {username}: {e}")
                            continue
                except PlaywrightTimeoutError:
                    logger.warning(f"No posts found for {username}")

                # Engagement Rate
                total_engagement = sum(p['likes'] + p['comments'] for p in posts_data)
                engagement_rate = total_engagement / followers if followers > 0 else 0.0

                return {
                    "username": username,
                    "profile_url": url,
                    "follower_count": followers,
                    "bio": bio.strip() if bio else "",
                    "posts": posts_data,
                    "engagement_rate": engagement_rate,
                    "scraped_at": datetime.now(timezone.utc).isoformat()
                }

            except Exception as e:
                logger.error(f"Attempt {attempt+1} failed for {username}: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached for {username}. Giving up.")
                else:
                    await page.wait_for_timeout(2000)
            finally:
                await context.close()
                await browser.close()

async def scrape_profile(username, max_posts=3, timeout=30000, max_retries=2):
    """Scrape profile using API first, then DOM as fallback."""
    # Try API first
    creator = await scrape_profile_api(username)
    if creator:
        try:
            total_engagement = sum(p['likes'] + p['comments'] for p in creator['posts'])
            creator['engagement_rate'] = total_engagement / creator['follower_count'] if creator['follower_count'] > 0 else 0.0
            collection.update_one({"username": username}, {"$set": creator}, upsert=True)
            logger.info(f"Successfully saved API data for {username}")
            return
        except PyMongoError as e:
            logger.error(f"Failed to save API data for {username} to MongoDB: {e}")

    # Fallback to DOM scraping
    creator = await scrape_profile_dom(username, max_posts, timeout, max_retries)
    if creator:
        try:
            collection.update_one({"username": username}, {"$set": creator}, upsert=True)
            logger.info(f"Successfully saved DOM data for {username}")
        except PyMongoError as e:
            logger.error(f"Failed to save DOM data for {username} to MongoDB: {e}")

if __name__ == "__main__":
    username = input("Enter Instagram username: ")
    asyncio.run(scrape_profile(username))