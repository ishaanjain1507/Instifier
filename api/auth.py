from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from database.mongo import users_collection
from auth.utils import hash_password, verify_password, create_access_token, decode_token
from fastapi.security import OAuth2PasswordBearer
from bson import ObjectId

router = APIRouter()

class UserIn(BaseModel):
    email: str
    password: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/auth/signup")
async def signup(user: UserIn):
    if users_collection is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    if await users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    hashed = hash_password(user.password)
    await users_collection.insert_one({"email": user.email, "password": hashed})
    return {"msg": "User created"}

@router.post("/auth/login")
async def login(user: UserIn):
    if users_collection is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    db_user = await users_collection.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(db_user["_id"])})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/auth/me")
async def get_me(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await users_collection.find_one({"_id": ObjectId(payload.get("sub"))})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"email": user["email"]}
