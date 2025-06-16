# worker.py
import asyncio
import logging
import json
import httpx
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstagramScraper:
    def __init__(self):
        # API headers as before
        self.api_headers = {
            "x-ig-app-id": "936619743392459",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.max_posts = 12
        self.post_timeout = 15000

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
                multiplier = multipliers.get(suffix, 1)
                return int(float(number) * multiplier)
            return int(text)
        except (ValueError, TypeError, AttributeError):
            logger.exception(f"Failed to parse follower count '{text}'")
            return 0

    def _save_debug_data(self, filename: str, data: Any):
        try:
            with open(f"debug_{filename}", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning(f"Could not save debug data to debug_{filename}")

    def _parse_join_date(self, timestamp: Optional[int]) -> str:
        try:
            if timestamp:
                dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
                return dt.isoformat()
        except Exception:
            logger.warning(f"Failed to parse join date timestamp '{timestamp}'")
        return ""

    async def login(self, page, username, password):
        try:
            await page.goto("https://www.instagram.com/accounts/login/", timeout=30000)
            try:
                await page.wait_for_selector("input[name='username'], button:has-text('Not Now')", timeout=5000)
                if await page.locator("button:has-text('Not Now')").count():
                    await page.locator("button:has-text('Not Now')").click()
            except PlaywrightTimeoutError:
                pass

            if await page.locator("input[name='username']").count():
                await page.fill("input[name='username']", username)
                await page.fill("input[name='password']", password)
                await page.click("button[type='submit']")
                try:
                    await page.wait_for_selector("input[name='verificationCode']", timeout=5000)
                    logger.warning("2FA detected - manual intervention needed")
                    return False
                except PlaywrightTimeoutError:
                    pass

            await page.wait_for_url("https://www.instagram.com/**", timeout=30000)
            logger.info("Logged in successfully")
            return True
        except Exception:
            logger.exception("Login failed")
            return False

    async def scrape_profile_api(self, username):
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(url, headers=self.api_headers)
                response.raise_for_status()
                data = response.json().get("data", {}).get("user", {})
                if not data:
                    logger.warning(f"No user data returned for {username}")
                    return None

                self._save_debug_data(f"api_{username}.json", data)

                posts = []
                for edge in data.get("edge_owner_to_timeline_media", {}).get("edges", [])[:self.max_posts]:
                    try:
                        post = {
                            "id": edge["node"].get("id"),
                            "image_url": edge["node"].get("display_url", ""),
                            "is_video": edge["node"].get("is_video", False),
                            "video_views": edge["node"].get("video_view_count", 0) if edge["node"].get("is_video") else 0,
                            "likes": edge["node"].get("edge_liked_by", {}).get("count", 0),
                            "comments": edge["node"].get("edge_media_to_comment", {}).get("count", 0),
                            "timestamp": edge["node"].get("taken_at_timestamp"),
                            "caption": edge["node"].get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", ""),
                        }
                        posts.append(post)
                    except Exception:
                        logger.exception(f"Error processing post for {username}; continuing to next")
                        continue

                location = ""
                bio = data.get("biography", "") or ""
                location_markers = ["📍", "🏠", "🌍", "✈️", "🏢"]
                for marker in location_markers:
                    if marker in bio:
                        location = bio.split(marker)[1].split("\n")[0].strip()
                        break
                if not location and data.get("business_address_json"):
                    try:
                        addr = json.loads(data.get("business_address_json", "{}"))
                        location = ", ".join(filter(None, [
                            addr.get("street_address"),
                            addr.get("city_name"),
                            addr.get("region_name"),
                            addr.get("country_name")
                        ]))
                    except json.JSONDecodeError:
                        pass

                total_engagement = sum(
                    p['likes'] + p['comments'] + (p['video_views'] if p['is_video'] else 0)
                    for p in posts
                )
                follower_count = data.get("edge_followed_by", {}).get("count", 0)
                engagement_rate = (total_engagement / follower_count) * 100 if follower_count > 0 else 0

                date_ts = data.get("edge_followed_by", {}).get("edges", [{}])[0].get("node", {}).get("timestamp")
                date_joined = self._parse_join_date(date_ts)

                creator = {
                    "username": data.get("username", username),
                    "name": data.get("full_name", "") or "",
                    "account_type": "Business" if data.get("is_business_account") else
                                    "Creator" if data.get("is_professional_account") else "Personal",
                    "date_joined": date_joined,
                    "location": location,
                    "profile_url": f"https://www.instagram.com/{username}/",
                    "follower_count": follower_count,
                    "following_count": data.get("edge_follow", {}).get("count", 0),
                    "bio": bio,
                    "number_of_posts": data.get("edge_owner_to_timeline_media", {}).get("count", 0),
                    "posts": posts,
                    "engagement_rate": round(engagement_rate, 2),
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "source": "api",
                }
                logger.info(f"Successfully scraped {username} via API")
                return creator
            except Exception:
                logger.exception(f"API scrape failed for {username}")
                return None

    async def scrape_profile_dom(self, username, login_credentials=None):
        url = f"https://www.instagram.com/{username}/"
        logger.info(f"[DOM] Start scraping profile: {url}")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 720},
                )
                # Stealth script
                await context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    window.navigator.chrome = { runtime: {} };
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.__proto__.query = (parameters) => (
                      parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                    );
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    """
                )
                page = await context.new_page()

                if login_credentials:
                    logger.info("[DOM] Attempting login before scraping")
                    ok = await self.login(page, login_credentials["username"], login_credentials["password"])
                    if not ok:
                        logger.warning("[DOM] Login failed, aborting DOM scrape")
                        await context.close()
                        await browser.close()
                        return None
                    await asyncio.sleep(2)

                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                except PlaywrightTimeoutError:
                    logger.exception(f"[DOM] Timeout navigating to {url}")
                    try:
                        await page.screenshot(path=f"error_{username}.png", full_page=True)
                        logger.info(f"[DOM] Screenshot saved to error_{username}.png")
                    except Exception:
                        pass
                    await context.close()
                    await browser.close()
                    return None
                except Exception:
                    logger.exception(f"[DOM] Error navigating to {url}")
                    await context.close()
                    await browser.close()
                    return None

                try:
                    await page.wait_for_selector("main", timeout=15000)
                except PlaywrightTimeoutError:
                    logger.exception(f"[DOM] main selector not found for {username}")
                    await context.close()
                    await browser.close()
                    return None

                # Save debug HTML
                try:
                    content = await page.content()
                    with open(f"debug_dom_{username}.html", "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info(f"[DOM] Saved debug HTML to debug_dom_{username}.html")
                except Exception:
                    logger.warning(f"[DOM] Could not save debug HTML for {username}")

                # Check for login wall or unavailable
                try:
                    if await page.locator("text=Log in to see").count():
                        logger.warning(f"[DOM] Encountered login wall or blocked content for {username}")
                        await context.close()
                        await browser.close()
                        return None
                    if await page.locator("text=Sorry, this page isn't available").count():
                        logger.warning(f"[DOM] Profile {username} not available (404).")
                        await context.close()
                        await browser.close()
                        return None
                except Exception:
                    logger.exception("[DOM] Error checking error states")

                # Extract header
                try:
                    profile_data = await self._extract_profile_header(page, username)
                    if not profile_data:
                        logger.warning(f"[DOM] _extract_profile_header returned None for {username}")
                        await context.close()
                        await browser.close()
                        return None
                except Exception:
                    logger.exception(f"[DOM] Exception in extracting header for {username}")
                    await context.close()
                    await browser.close()
                    return None

                # Extract posts
                try:
                    posts_data = await self._extract_posts(page, username)
                    profile_data["posts"] = posts_data
                except Exception:
                    logger.exception(f"[DOM] Exception in extracting posts for {username}")
                    profile_data["posts"] = []

                # Calculate engagement rate
                try:
                    total_engagement = sum(
                        p.get('likes', 0) + p.get('comments', 0) + (p.get('video_views', 0) if p.get('is_video') else 0)
                        for p in profile_data.get("posts", [])
                    )
                    follower_count = profile_data.get("follower_count", 0)
                    profile_data["engagement_rate"] = round((total_engagement / follower_count) * 100 if follower_count > 0 else 0, 2)
                except Exception:
                    logger.exception(f"[DOM] Error calculating engagement rate for {username}")
                    profile_data["engagement_rate"] = 0

                profile_data["scraped_at"] = datetime.now(timezone.utc).isoformat()
                profile_data["source"] = "dom"

                logger.info(f"[DOM] Successfully scraped {username}")
                await context.close()
                await browser.close()
                return profile_data

        except Exception:
            logger.exception(f"[DOM] Unexpected error scraping {username}")
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            return None

    async def _save_dom_debug(self, page, username):
        try:
            content = await page.content()
            with open(f"debug_dom_{username}.html", "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            logger.warning(f"Could not save DOM debug for {username}")

    async def _check_error_states(self, page, username) -> bool:
        try:
            if await page.locator("text=Sorry, this page isn't available").count():
                logger.warning(f"Profile {username} not available (404 or disabled).")
                return True
        except Exception:
            logger.exception("Error checking error states")
        return False

    async def _extract_profile_header(self, page, username):
        """
        Improved profile header extraction with better selectors,
        to avoid capturing stats as bio.
        """
        try:
            # Wait for profile header to load
            await page.wait_for_selector("header", timeout=15000)
        except PlaywrightTimeoutError:
            logger.exception(f"[DOM] Header selector not found for {username}")
            return None

        data: Dict[str, Any] = {
            "username": username,
            "profile_url": f"https://www.instagram.com/{username}/"
        }

        # 1. Name
        try:
            # Instagram often uses <h1> or <h2> for the display name
            name_locator = page.locator("header h1, header h2")
            if await name_locator.count():
                name = (await name_locator.first.text_content()) or ""
                data["name"] = name.strip()
            else:
                data["name"] = ""
        except Exception:
            logger.exception(f"[DOM] Failed to extract name for {username}")
            data["name"] = ""

        # 2. Bio
        try:
            bio = ""
            # Select spans under header section that are NOT inside the stats buttons.
            # We exclude any span whose ancestor is a <button> or whose text_content
            # combined with next sibling includes 'posts'/'followers'/'following'.
            # A simpler approach: select spans under header but skip those whose 
            # text_content is purely numeric or empty, or whose parent text includes stats keywords.
            bio_spans = await page.locator("header section div span").all()
            for span in bio_spans:
                try:
                    text = (await span.text_content()) or ""
                    text = text.strip()
                    if not text:
                        continue
                    # Check the full text of the parent element (e.g., span.parentElement.textContent)
                    parent_text = (await span.evaluate("(node) => node.parentElement.textContent")) or ""
                    parent_text = parent_text.strip().lower()
                    # Skip if parent_text indicates stats:
                    if any(keyword in parent_text for keyword in ("posts", "followers", "following")):
                        continue
                    # Also skip if the text looks like just the username repeated
                    if text.lower() == username.lower():
                        continue
                    # If passed above checks, treat as a bio line
                    bio += text + "\n"
                except Exception:
                    # If anything goes wrong for one span, skip it
                    continue
            data["bio"] = bio.strip()
        except Exception:
            logger.exception(f"[DOM] Failed to extract bio for {username}")
            data["bio"] = ""

        # 3. Stats: posts, followers, following
        try:
            stats = {}
            stat_items = await page.locator("header ul li").all()
            for li in stat_items:
                try:
                    text = (await li.text_content()) or ""
                    text = text.strip().lower()
                    if "posts" in text:
                        stats["posts"] = self.parse_follower_count(text)
                    elif "followers" in text:
                        stats["followers"] = self.parse_follower_count(text)
                    elif "following" in text:
                        stats["following"] = self.parse_follower_count(text)
                except Exception:
                    continue
            data["number_of_posts"] = stats.get("posts", 0)
            data["follower_count"] = stats.get("followers", 0)
            data["following_count"] = stats.get("following", 0)
        except Exception:
            logger.exception(f"[DOM] Failed to extract stats for {username}")
            data.setdefault("number_of_posts", 0)
            data.setdefault("follower_count", 0)
            data.setdefault("following_count", 0)

        # 4. Account type
        try:
            account_type = "Personal"
            if await page.locator("div:has-text('Professional')").count():
                account_type = "Creator"
            elif await page.locator("div:has-text('Business')").count():
                account_type = "Business"
            elif await page.locator("a[href*='/shop/']").count():
                account_type = "Business"
            data["account_type"] = account_type
        except Exception:
            logger.exception(f"[DOM] Failed to extract account type for {username}")
            data["account_type"] = "Personal"

        # 5. Location
        try:
            location = ""
            # Try link-based location (pin icon or href containing 'location')
            loc_elements = await page.locator("header a[href*='location'], header div:has(svg[aria-label='Location'])").all()
            for el in loc_elements:
                try:
                    href = await el.get_attribute("href") or ""
                    text = (await el.text_content()) or ""
                    text = text.strip()
                    # If href suggests location path or there's a pin icon, accept text
                    if "location" in href or text:
                        location = text
                        break
                except Exception:
                    continue
            # Fallback: look for emoji markers in bio
            if not location:
                bio_text = data.get("bio", "")
                for marker in ["📍", "🏠", "🌍", "✈️", "🏢"]:
                    if marker in bio_text:
                        # take the portion after the marker until newline
                        loc = bio_text.split(marker, 1)[1].split("\n", 1)[0].strip()
                        if loc:
                            location = loc
                            break
            data["location"] = location.strip()
        except Exception:
            logger.exception(f"[DOM] Failed to extract location for {username}")
            data["location"] = ""

        # 6. Date joined
        try:
            date_joined = await self._extract_join_date(page, username)
            data["date_joined"] = date_joined or ""
        except Exception:
            logger.exception(f"[DOM] Failed to extract date_joined for {username}")
            data["date_joined"] = ""

        return data


    async def _extract_join_date(self, page, username):
        date_joined = ""
        try:
            # Try "About This Account"
            await page.locator("svg[aria-label='Options']").first.click()
            await page.wait_for_selector("a:has-text('About This Account')", timeout=5000)
            await page.locator("a:has-text('About This Account')").first.click()
            await page.wait_for_selector("div:has-text('Date joined')", timeout=5000)
            date_element = page.locator("div:has-text('Date joined')")
            if await date_element.count():
                text = await date_element.first.text_content() or ""
                date_joined = text.replace("Date joined", "").strip()
            await page.go_back()
            await page.wait_for_selector("header", timeout=5000)
        except Exception:
            logger.warning(f"Couldn't get join date from About page for {username}")
            # Fallback: oldest post date
            try:
                await page.wait_for_selector("article a time", timeout=5000)
                oldest_post = page.locator("article a time").last
                if await oldest_post.count():
                    datetime_str = await oldest_post.get_attribute("datetime")
                    if datetime_str:
                        date_joined = datetime.fromisoformat(datetime_str.rstrip("Z")).strftime("%B %Y")
            except Exception:
                pass
        return date_joined

    async def _extract_posts(self, page, username):
        posts_data = []
        try:
            # Wait for posts container (adjust selector per your debug HTML)
            await page.wait_for_selector("article", timeout=20000)
            # Collect candidate post links: filter by href pattern
            anchors = await page.locator("article a[role='link']").all()
            post_elements = []
            for a in anchors:
                href = await a.get_attribute("href") or ""
                # Example patterns: /p/, /reel/, /tv/ etc
                if href.startswith(f"/{username}/") or "/p/" in href or "/reel/" in href:
                    post_elements.append(a)
            # Limit to max_posts
            post_elements = post_elements[:self.max_posts]

            # Optionally remove/hide overlays before clicking
            await page.evaluate("""
                // disable pointer-events on known overlay selectors; adjust selectors based on debug HTML
                document.querySelectorAll('div[class*="modal"], div[role="presentation"], div[class*="overlay"]').forEach(el => {
                el.style.pointerEvents = 'none';
                });
            """)

            for i, post in enumerate(post_elements):
                try:
                    href = await post.get_attribute("href") or ""
                    post_url = f"https://www.instagram.com{href}"
                    # Attempt to click with force
                    await post.scroll_into_view_if_needed()
                    await post.click(force=True)
                    # Wait for the dialog or new page to load
                    try:
                        await page.wait_for_selector('div[role="dialog"]', timeout=self.post_timeout)
                    except Exception:
                        # If click didn’t open a dialog, try navigating directly
                        await page.goto(post_url, timeout=self.post_timeout)
                        # Wait for expected selector in standalone post view
                        await page.wait_for_selector("article", timeout=10000)
                    # Extract post data
                    post_data = await self._extract_single_post(page, username, i)
                    if post_data:
                        post_data["post_url"] = post_url
                        posts_data.append(post_data)
                    # Close modal or go back
                    try:
                        # If a modal dialog is open, Escape
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                    except Exception:
                        # Otherwise, navigate back to profile
                        await page.goto(f"https://www.instagram.com/{username}/", timeout=15000)
                        await page.wait_for_selector("article", timeout=10000)
                except Exception as e:
                    logger.exception(f"Error scraping post {i+1} for {username}")
                    # After failure, ensure we are back on profile page for next iteration:
                    try:
                        await page.goto(f"https://www.instagram.com/{username}/", timeout=15000)
                        await page.wait_for_selector("article", timeout=10000)
                    except Exception:
                        pass
                    continue
        except Exception:
            logger.exception(f"Failed to extract posts for {username}")
        return posts_data


    async def _extract_single_post(self, page, username, post_index):
        try:
            await page.wait_for_selector('div[role="dialog"]', timeout=self.post_timeout)
            # Media URL
            media_url = ""
            is_video = False
            if await page.locator("video").count():
                src = await page.locator("video source").first.get_attribute("src") or ""
                media_url = src
                is_video = True
            else:
                img = await page.locator("div img").first.get_attribute("src") or ""
                media_url = img
                is_video = False
            # Likes
            likes = 0
            likes_text = ""
            try:
                likes_locator = page.locator("section div span")
                if await likes_locator.count():
                    likes_text = await likes_locator.first.text_content() or ""
                    likes = self.parse_follower_count(likes_text.split()[0]) if likes_text else 0
            except Exception:
                logger.exception("Error extracting likes")
            # Comments count
            comments_count = 0
            try:
                comments_section = page.locator("ul li")
                comments_count = await comments_section.count() - 1  # rough; adjust as needed
            except Exception:
                logger.exception("Error extracting comments count")
            # Timestamp
            timestamp = ""
            try:
                time_element = page.locator("time")
                if await time_element.count():
                    datetime_str = await time_element.first.get_attribute("datetime") or ""
                    if datetime_str:
                        timestamp = datetime.fromisoformat(datetime_str.rstrip("Z")).isoformat()
            except Exception:
                logger.exception("Error extracting timestamp")
            # Caption
            caption = ""
            try:
                caption_element = page.locator("div span")
                if await caption_element.count():
                    caption = await caption_element.first.text_content() or ""
            except Exception:
                logger.exception("Error extracting caption")
            return {
                "image_url": media_url,
                "is_video": is_video,
                "likes": likes,
                "comments": comments_count if comments_count >= 0 else 0,
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "caption": caption,
            }
        except Exception:
            logger.exception(f"Failed to extract post {post_index+1} for {username}")
            return None

    async def scrape_profile(self, username: str, login_credentials: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        creator = await self.scrape_profile_api(username)
        if creator:
            return creator
        creator = await self.scrape_profile_dom(username, login_credentials)
        if creator:
            return creator
        logger.error(f"Failed to scrape profile for {username} using both methods")
        return None

# Shared instance
instagram_scraper = InstagramScraper()

async def scrape_profile(username: str, login_credentials: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    return await instagram_scraper.scrape_profile(username, login_credentials)
