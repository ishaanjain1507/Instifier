from fastapi import FastAPI
from api.endpoints import router as creators_router

app = FastAPI()

app.include_router(creators_router, prefix="/creators", tags=["Creators"])
@app.get("/")
def read_root():
    return {"message": "Welcome to the Instagram Creators API. Use /creators to filter creators."}

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "API is running smoothly."}

@app.get("/docs")
def get_docs():
    return {"message": "API documentation is available at /docs."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
