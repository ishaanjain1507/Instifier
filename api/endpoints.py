from fastapi import APIRouter, HTTPException, Query, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database.mongo import creators_collection
from scraper.worker import scrape_profile
from datetime import datetime, timezone
from typing import Optional, List
from io import BytesIO
from bson import ObjectId
import pandas as pd
import traceback
import logging
import re
import asyncio
from session_manager import refresh_instagram_session

router = APIRouter()
logger = logging.getLogger(__name__)

# === Filter Creators ===
@router.get("/", response_model=List[dict])
async def filter_creators(
    min_followers: int = Query(1000),
    max_followers: int = Query(100000),
    location: Optional[str] = None,
    min_engagement: Optional[float] = None,
    account_type: Optional[str] = None,
    last_scraped_before: Optional[datetime] = None,
    limit: int = Query(50)
):
    try:
        query = {
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
            query["scraped_at"] = {"$lt": last_scraped_before.isoformat()}

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
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error while filtering creators",
                "traceback": traceback.format_exc()
            }
        )

@router.post("/refresh-session")
async def refresh_session_route(
    username: str = Query(...),
    password: str = Query(...)
):
    sessionid = await refresh_instagram_session(username, password)
    if sessionid:
        return {"message": "Session refreshed", "sessionid": sessionid}
    raise HTTPException(status_code=500, detail="Failed to refresh session")

# === Scrape One Profile ===
@router.post("/scrape/{username}", response_model=dict)
async def scrape_creator(
    username: str,
    use_login: bool = Query(False),
    login_username: Optional[str] = None,
    login_password: Optional[str] = None
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

        existing = creators_collection.find_one({"username": username}, {"scraped_at": 1})
        if existing:
            try:
                last_scraped = datetime.fromisoformat(existing.get("scraped_at"))
                if (datetime.now(timezone.utc) - last_scraped).days < 1:
                    return {
                        "message": f"Profile {username} was recently scraped ({last_scraped.isoformat()})",
                        "status": "cached"
                    }
            except:
                pass

        result = await scrape_profile(username, login_credentials)
        if not result:
            return {
                "message": f"Scraping failed or returned no data for {username}",
                "status": "failed"
            }

        creators_collection.update_one(
            {"username": username},
            {"$set": result},
            upsert=True
        )

        return {
            "message": f"Successfully scraped and saved profile: {username}",
            "source": result.get("source", "unknown"),
            "scrape_time_seconds": result.get("scrape_time_seconds", None),
            "status": "success"
        }

    except Exception as e:
        logger.exception(f"Unexpected error in /scrape/{username}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Unhandled error while scraping {username}",
                "exception": str(e),
                "traceback": traceback.format_exc()
            }
        )

# === Parse Followers Text ===
def parse_count(val):
    if pd.isna(val):
        return 0
    val = str(val).lower().strip()
    val = val.replace(",", "").replace("~", "").replace("—", "-").replace("–", "-")

    if "-" in val:
        parts = val.split("-")
        try:
            nums = [float(p) for p in parts if p]
            return int(sum(nums) / len(nums)) if nums else 0
        except:
            return 0

    match = re.match(r"([\d.]+)\s*([kmb]?)", val)
    if match:
        number, suffix = match.groups()
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
        return int(float(number) * multipliers.get(suffix, 1))

    try:
        return int(float(val))
    except:
        return 0

# === Upload Excel and Scrape All ===
@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    import time
    start_time = time.time()

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are supported.")

    content = await file.read()

    df = pd.read_excel(BytesIO(content), engine='openpyxl')
    df.columns = [col.strip().lower() for col in df.columns]

    required_columns = [
        "username", "profile_link", "followers", "insights",
        "avg reel views", "avg story views",
        "price for reel+ story (inr)", "price of 2 story"
    ]
    for col in required_columns:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")

    inserted_usernames = []
    failed_usernames = []

    tasks = []
    for _, row in df.iterrows():
        username = str(row["username"]).strip().lower()
        existing = creators_collection.find_one({"username": username}, {"scraped_at": 1})
        if existing:
            try:
                last_scraped = datetime.fromisoformat(existing["scraped_at"])
                if (datetime.now(timezone.utc) - last_scraped).days < 1:
                    continue
            except:
                pass
        tasks.append((username, row))

    async def process(username, row):
        try:
            logger.info(f"Scraping: {username}")
            scraped = await scrape_profile(username)
            if not scraped:
                logger.warning(f"Failed to scrape {username}")
                return (username, False)

            scraped.update({
                "profile_url": row["profile_link"],
                "follower_count": parse_count(row["followers"]),
                "insights": row["insights"],
                "avg_reel_views": parse_count(row["avg reel views"]),
                "avg_story_views": parse_count(row["avg story views"]),
                "price_reel_story": parse_count(row["price for reel+ story (inr)"]),
                "price_2_story": parse_count(row["price of 2 story"]),
                "source": "excel+scraped",
                "scraped_at": datetime.now(timezone.utc).isoformat()
            })

            creators_collection.update_one(
                {"username": username},
                {"$set": scraped},
                upsert=True
            )
            logger.info(f"Inserted: {username}")
            return (username, True)

        except Exception as e:
            logger.exception(f"Error processing {username}: {e}")
            return (username, False)

    results = await asyncio.gather(*[process(u, r) for u, r in tasks])
    for username, success in results:
        (inserted_usernames if success else failed_usernames).append(username)

    return {
        "message": f"{len(inserted_usernames)} profiles inserted/updated.",
        "status": "success",
        "inserted_usernames": inserted_usernames,
        "failed_usernames": failed_usernames,
        "total_time_seconds": round(time.time() - start_time, 2)
    }

# === Get Profile by Username ===
@router.get("/profile/{username}", response_model=dict)
async def get_creator_profile(username: str):
    try:
        profile = creators_collection.find_one({"username": username}, {"_id": 0})
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
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Internal server error while retrieving {username}",
                "traceback": traceback.format_exc()
            }
        )

from bson import ObjectId

@router.get("/all")  # becomes /creators/all via prefix
async def get_all_creators():
    try:
        # Use async to_list to fetch all documents
        docs = await creators_collection.find().to_list(length=None)
        creators = []
        for doc in docs:
            doc.pop("_id", None)  # Remove ObjectId
            creators.append(doc)
        return creators
    except Exception:
        logger.exception("Error fetching all creators")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error while fetching all creators",
                "traceback": traceback.format_exc(),
            },
        )
