# endpoints.py
from fastapi import APIRouter, HTTPException, Query
from database.mongo import creators_collection
from scraper.worker import scrape_profile
from typing import Optional, List
from datetime import datetime, timezone
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[dict])
async def filter_creators(
    min_followers: int = Query(1000, description="Minimum follower count"),
    max_followers: int = Query(100000, description="Maximum follower count"),
    location: Optional[str] = Query(None, description="Location filter (case-insensitive)"),
    min_engagement: Optional[float] = Query(None, description="Minimum engagement rate"),
    account_type: Optional[str] = Query(None, description="Account type filter (Personal, Creator, Business)"),
    last_scraped_before: Optional[datetime] = Query(None, description="Filter profiles scraped before this date"),
    limit: int = Query(50, description="Maximum number of results to return")
):
    try:
        query: dict = {
            "follower_count": {"$gte": min_followers, "$lte": max_followers}
        }
        if location:
            query["$or"] = [
                {"bio": {"$regex": location, "$options": "i"}},
                {"location": {"$regex": location, "$options": "i"}}
            ]
        if min_engagement is not None:
            query["engagement_rate"] = {"$gte": min_engagement}
        if account_type:
            query["account_type"] = account_type.capitalize()
        if last_scraped_before:
            iso_str = last_scraped_before.isoformat()
            query["scraped_at"] = {"$lt": iso_str}
        projection = {
            "_id": 0,
            "username": 1,
            "name": 1,
            "account_type": 1,
            "follower_count": 1,
            "engagement_rate": 1,
            "location": 1,
            "profile_url": 1,
            "scraped_at": 1
        }
        results = creators_collection.find(query, projection).limit(limit)
        return list(results)
    except Exception:
        logger.exception("Error filtering creators")
        raise HTTPException(status_code=500, detail="Internal server error while filtering creators")

@router.post("/scrape/{username}", response_model=dict)
async def scrape_creator(
    username: str,
    use_login: bool = Query(False, description="Use Instagram login for scraping"),
    login_username: Optional[str] = Query(None, description="Instagram login username"),
    login_password: Optional[str] = Query(None, description="Instagram login password")
):
    try:
        login_credentials = None
        if use_login:
            if not login_username or not login_password:
                raise HTTPException(
                    status_code=400,
                    detail="Login credentials required when use_login is True"
                )
            login_credentials = {
                "username": login_username,
                "password": login_password
            }

        existing_profile = creators_collection.find_one(
            {"username": username},
            {"scraped_at": 1}
        )
        if existing_profile:
            scraped_at_str = existing_profile.get("scraped_at")
            try:
                last_scraped = datetime.fromisoformat(scraped_at_str)
            except Exception:
                last_scraped = None
            if last_scraped:
                now = datetime.now(timezone.utc)
                if (now - last_scraped).days < 1:
                    return {
                        "message": f"Profile {username} was recently scraped ({last_scraped.isoformat()})",
                        "status": "cached"
                    }

        result = await scrape_profile(username, login_credentials)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to scrape profile {username}"
            )

        try:
            creators_collection.update_one(
                {"username": username},
                {"$set": result},
                upsert=True
            )
        except Exception:
            logger.exception(f"Failed to upsert profile {username} into database")
            raise HTTPException(status_code=500, detail="Database error while saving scraped profile")

        return {
            "message": f"Successfully scraped and saved profile: {username}",
            "source": result.get("source", "unknown"),
            "status": "success"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Internal server error while scraping {username}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while scraping {username}"
        )

@router.get("/profile/{username}", response_model=dict)
async def get_creator_profile(username: str):
    try:
        profile = creators_collection.find_one(
            {"username": username},
            {"_id": 0}
        )
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"Profile {username} not found in database"
            )
        return profile
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error retrieving profile {username}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving profile"
        )
