from fastapi import FastAPI
from api.config import settings

app = FastAPI(
    title="Nexus AI NPC Backend",
    version="1.0.0",
    description="Backend API for the Nexus AI NPC game."
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Nexus API!",
        "environment": settings.environment
    }
