"""Health check."""
from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
