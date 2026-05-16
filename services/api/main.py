"""
services/api/main.py
────────────────────
API Gateway — punto de entrada único para la app móvil y el dashboard.
Solo hace: auth, routing, rate limiting, CORS.
NO contiene lógica de negocio, NO lanza subprocesos.

Uso:
    uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Asegurar que el repo root está en sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from services.api.routers import (
    auth,
    backtest,
    health,
    live,
    models,
    signals,
    squawks,
    tickers,
    trading,
    training,
)

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

app = FastAPI(title="Squawks ML API", version="4.0.0")

# CORS: leer orígenes permitidos de env var, default restrictivo.
# En desarrollo: CORS_ORIGINS=* en .env
# En producción: CORS_ORIGINS=https://app.squawks.ml,https://squawks.ml
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(health.router,    tags=["Health"])
app.include_router(auth.router,      tags=["Auth"])
app.include_router(tickers.router,   prefix="/api", tags=["Data"])
app.include_router(models.router,    prefix="/api", tags=["Models"])
app.include_router(training.router,  prefix="/api", tags=["Training"])
app.include_router(backtest.router,  prefix="/api", tags=["Backtest"])
app.include_router(live.router,      prefix="/api", tags=["Live"])
app.include_router(trading.router,   prefix="/api", tags=["Trading"])
app.include_router(signals.router,   prefix="/api", tags=["Signals"])
app.include_router(squawks.router,   prefix="/api", tags=["Squawks"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8000, reload=True)
