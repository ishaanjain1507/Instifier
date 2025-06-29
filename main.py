import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import router as creators_router
from api.auth import router as auth_router

# ✅ Fix for Playwright subprocess issue on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI()
app.include_router(auth_router)

# ✅ CORS fix for Swagger UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In prod, replace with your domain like ["https://instifier.in"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register API router
app.include_router(creators_router, prefix="/creators", tags=["Creators"])

@app.get("/")
def read_root():
    return {
        "message": (
            "Welcome to the Instagram Creators API. "
            "Use /creators/scrape/{username} to scrape a profile, "
            "/creators to filter creators, and "
            "/creators/upload-excel to bulk upload from Excel."
        )
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running smoothly."}

@app.get("/docs")
def get_docs():
    return {"message": "API documentation is available at /docs."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
