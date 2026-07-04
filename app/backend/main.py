from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from routers import auth, workspaces, repositories, chat
from models.base import Base
from db import engine

# Import all models so SQLAlchemy registers them with Base.metadata before create_all
import models.workspace  # noqa: F401
import models.repository  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # pgvector extension must exist before vector columns are created
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Groundtruth API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(repositories.router, prefix="/api/repositories", tags=["repositories"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])



@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
