"""Health check."""
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from shared.db import query

router = APIRouter()

@router.get("/api/health")
async def health():
    now = datetime.now(UTC).isoformat()
    try:
        query("SELECT 1")
        return {"status": "ok", "db": "ok", "time": now}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "unreachable", "time": now},
        )
