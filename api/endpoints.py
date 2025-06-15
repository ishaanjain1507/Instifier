from fastapi import APIRouter
from database.mongo import creators_collection
from scraper.worker import scrape_profile
from fastapi import HTTPException


router = APIRouter()

@router.get("/")
def filter_creators(min_followers: int = 1000, max_followers: int = 100000, location: str = ""):
    query = {
        "follower_count": {"$gte": min_followers, "$lte": max_followers}
    }
    if location:
        query["bio"] = {"$regex": location, "$options": "i"}

    results = creators_collection.find(query).limit(50)
    return list(results)

@router.post("/scrape/{username}")
async def scrape_creator(username: str):
    try:
        await scrape_profile(username)
        return {"message": f"Scraped profile: {username}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
