import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine
import redis.asyncio as aioredis

from api.config import settings
from api.dependencies import init_db, init_redis
from api.routers import auth, realtime, sessions

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Initializing database engine...")
    engine = create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
        pool_size=20,
        max_overflow=10,
    )
    init_db(engine)

    logger.info("Initializing Redis pool...")
    redis_client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    init_redis(redis_client)

    logger.info("Application startup complete.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Disposing database engine...")
    await engine.dispose()
    
    logger.info("Closing Redis connections...")
    await redis_client.aclose()
    logger.info("Application shutdown complete.")

app = FastAPI(
    title="Nexus AI NPC Backend",
    version="1.0.0",
    description="Backend API for the Nexus AI NPC game.",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(auth.router, prefix="/v1")
app.include_router(sessions.router, prefix="/v1")
app.include_router(realtime.router, prefix="/v1")

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Nexus API!",
        "environment": settings.environment
    }
