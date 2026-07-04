from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, UTC
import os

from db import get_db
from models.workspace import Workspace, User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    company_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def create_token(user_id: str, workspace_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10080)))
    return jwt.encode({"sub": user_id, "wid": workspace_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/signup")
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    workspace = Workspace(name=body.company_name)
    db.add(workspace)
    await db.flush()

    user = User(
        workspace_id=workspace.id,
        email=body.email,
        hashed_password=pwd_context.hash(body.password),
        full_name=body.company_name,
    )
    db.add(user)
    await db.commit()

    return {"token": create_token(user.id, workspace.id), "workspace_id": workspace.id}


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    return {"token": create_token(user.id, user.workspace_id), "workspace_id": user.workspace_id}
