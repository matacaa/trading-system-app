"""Endpoints de entrenamiento de modelos."""
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()

class TrainRequest(BaseModel):
    model: str
    ticker: str = "AAPL"
    timeframe: str = "1m"
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    context_tickers: list[str] = []
    columns: list[str] = [
        "ema_9","ema_12","ema_21","rsi_14","macd_line","macd_signal",
        "bb_pct","bb_width","vwap","atr_14","returns_5","volume_norm",
    ]
    params: dict[str, Any] = {}
    experiment_name: str = ""

@router.post("/train")
async def train(req: TrainRequest):
    """Encola un job de training.
    TODO fase 4: encolar en Service Bus en vez de subprocess.
    """
    # Por ahora mantiene el comportamiento actual (subprocess)
    # Se reemplazará por Service Bus queue en la fase 4
    import sys

    from apps.api.main import _generate_experiment_yaml, _run_pipeline
    tmp, exp_name = _generate_experiment_yaml(req)
    result = _run_pipeline(
        [sys.executable, "-m", "apps.ml_sandbox.pipeline", str(tmp)],
        timeout=600,
    )
    return {"experiment_name": exp_name, **result}
