# session_manager.py
import os
import json
from playwright.async_api import async_playwright

SESSION_FILE = "session.json"

async def refresh_instagram_session(username, password):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.instagram.com/accounts/login/")
        await page.fill("input[name='username']", username)
        await page.fill("input[name='password']", password)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(5000)

        cookies = await context.cookies()
        sessionid = next((c["value"] for c in cookies if c["name"] == "sessionid"), None)

        if sessionid:
            with open(SESSION_FILE, "w") as f:
                json.dump({"sessionid": sessionid}, f)

        await browser.close()
        return sessionid
