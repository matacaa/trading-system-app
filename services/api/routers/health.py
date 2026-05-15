"""Health check."""
from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter()

@router.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}
