"""Health check endpoint — no auth required."""
from fastapi import APIRouter, Depends
from ..deps.hub import get_hub

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check(hub=Depends(get_hub)):
    return {"status": "ok", "summary": hub.summary()}
