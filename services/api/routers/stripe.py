"""
services/api/routers/stripe.py
───────────────────────────────
Endpoints de Stripe: checkout, portal, webhooks, suscripción, packs.

Endpoints:
    POST /api/stripe/checkout       — crear Stripe Checkout session (suscripción)
    POST /api/stripe/portal         — crear Stripe Customer Portal session
    POST /api/stripe/webhook        — recibir webhooks de Stripe (SIN auth)
    GET  /api/stripe/subscription   — estado actual de la suscripción
    POST /api/stripe/cancel         — cancelar suscripción (al final del período)
    POST /api/stripe/buy-pack       — comprar pack extra (one-time)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from services.api.auth.dependencies import get_current_user
from shared.stripe_service import stripe_svc

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan: str  # "starter" o "pro"


class BuyPackRequest(BaseModel):
    pack_type: str  # "backtests", "trainings", "ticker"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/stripe/checkout")
async def create_checkout(
    req: CheckoutRequest,
    user: dict = Depends(get_current_user),
):
    """Crea una Stripe Checkout Session para suscripción.

    Devuelve la URL a la que redirigir al usuario.
    """
    if req.plan not in ("starter", "pro"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan no válido. Opciones: starter, pro",
        )

    try:
        url = stripe_svc.create_checkout_session(
            user_id=user["id"],
            email=user["email"],
            plan=req.plan,
        )
        return {"checkout_url": url}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        log.exception("Error creando checkout session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear sesión de pago",
        ) from e


@router.post("/stripe/portal")
async def create_portal(user: dict = Depends(get_current_user)):
    """Crea una sesión del Customer Portal de Stripe.

    El portal permite al usuario gestionar su suscripción,
    cambiar método de pago, ver facturas, etc.
    """
    try:
        url = stripe_svc.create_portal_session(
            user_id=user["id"],
            email=user["email"],
        )
        return {"portal_url": url}
    except Exception as e:
        log.exception("Error creando portal session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear sesión del portal",
        ) from e


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Recibe webhooks de Stripe.

    NO requiere autenticación JWT — Stripe verifica con su propia firma.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falta header Stripe-Signature",
        )

    try:
        result = stripe_svc.process_webhook(payload, sig_header)
        return result
    except ValueError as e:
        # Firma inválida
        log.warning("Webhook signature inválida: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature inválida",
        ) from e
    except Exception as e:
        log.exception("Error procesando webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando webhook",
        ) from e


@router.get("/stripe/subscription")
async def get_subscription(user: dict = Depends(get_current_user)):
    """Devuelve el estado actual de la suscripción del usuario."""
    sub = stripe_svc.get_subscription(user["id"])
    if not sub:
        return {
            "has_subscription": False,
            "plan": user["plan"],
            "message": "Sin suscripción activa. Plan actual basado en registro.",
        }

    return {
        "has_subscription": True,
        "plan": sub["plan"],
        "status": sub["status"],
        "current_period_start": sub["current_period_start"],
        "current_period_end": sub["current_period_end"],
        "cancel_at_period_end": sub["cancel_at_period_end"],
    }


@router.post("/stripe/cancel")
async def cancel_subscription(user: dict = Depends(get_current_user)):
    """Cancela la suscripción al final del período actual.

    El usuario mantiene acceso hasta que termine el período facturado.
    """
    try:
        result = stripe_svc.cancel_subscription(user["id"])
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        log.exception("Error cancelando suscripción")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cancelar suscripción",
        ) from e


@router.post("/stripe/buy-pack")
async def buy_pack(
    req: BuyPackRequest,
    user: dict = Depends(get_current_user),
):
    """Compra un pack extra (one-time payment via Stripe Checkout).

    Packs disponibles:
    - backtests: 10 backtests extra (~4.99€)
    - trainings: 5 trainings extra (~9.99€)
    - ticker: 1 ticker extra por 1 mes (~2.99€)
    """
    if req.pack_type not in ("backtests", "trainings", "ticker"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack no válido. Opciones: backtests, trainings, ticker",
        )

    try:
        url = stripe_svc.create_pack_checkout(
            user_id=user["id"],
            email=user["email"],
            pack_type=req.pack_type,
        )
        return {"checkout_url": url}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        log.exception("Error creando pack checkout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear sesión de compra",
        ) from e
