"""
shared/stripe_service.py
────────────────────────
Integración con Stripe: customers, checkout sessions, portal, webhooks.

La fuente de verdad es Stripe. Nuestra DB solo registra estado para queries rápidas.
Flujo: webhook de Stripe → actualizar users.plan + subscriptions.

Uso:
    from shared.stripe_service import stripe_svc

    url = stripe_svc.create_checkout_session(user_id, "starter")
    stripe_svc.process_webhook(payload, sig_header)

Env vars requeridas:
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
    STRIPE_STARTER_PRICE_ID, STRIPE_PRO_PRICE_ID
    STRIPE_PACK_BACKTESTS_PRICE_ID, STRIPE_PACK_TRAININGS_PRICE_ID
    STRIPE_PACK_TICKER_PRICE_ID
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# ── Stripe SDK (importación lazy para no crashear si no hay key) ─────────────

_stripe = None


def _get_stripe():
    """Importa y configura Stripe SDK una sola vez."""
    global _stripe
    if _stripe is not None:
        return _stripe

    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY no configurada. "
            "Añade la variable a tu .env para usar Stripe."
        )

    import stripe

    stripe.api_key = key
    _stripe = stripe
    log.info("Stripe SDK inicializado")
    return stripe


# ── Helpers de config ─────────────────────────────────────────────────────────

# Mapeo plan → Stripe Price ID (de env vars)
_PLAN_PRICES: dict[str, str] = {}
_PACK_PRICES: dict[str, str] = {}


def _load_prices() -> None:
    """Carga los Price IDs desde env vars (lazy, una vez)."""
    if _PLAN_PRICES:
        return

    _PLAN_PRICES["starter"] = os.getenv("STRIPE_STARTER_PRICE_ID", "")
    _PLAN_PRICES["pro"] = os.getenv("STRIPE_PRO_PRICE_ID", "")

    _PACK_PRICES["backtests"] = os.getenv("STRIPE_PACK_BACKTESTS_PRICE_ID", "")
    _PACK_PRICES["trainings"] = os.getenv("STRIPE_PACK_TRAININGS_PRICE_ID", "")
    _PACK_PRICES["ticker"] = os.getenv("STRIPE_PACK_TICKER_PRICE_ID", "")


def _get_plan_price(plan: str) -> str:
    """Devuelve el Stripe Price ID para un plan."""
    _load_prices()
    price_id = _PLAN_PRICES.get(plan, "")
    if not price_id:
        raise ValueError(f"No hay Price ID configurado para el plan '{plan}'")
    return price_id


def _get_pack_price(pack_type: str) -> str:
    """Devuelve el Stripe Price ID para un pack extra."""
    _load_prices()
    price_id = _PACK_PRICES.get(pack_type, "")
    if not price_id:
        raise ValueError(f"No hay Price ID configurado para el pack '{pack_type}'")
    return price_id


# ── Constantes ────────────────────────────────────────────────────────────────

_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

_PACK_CREDITS = {
    "backtests": ("extra_backtests", 10),
    "trainings": ("extra_trainings", 5),
    # ticker se maneja diferente (JSONB array)
}

# ── Servicio ──────────────────────────────────────────────────────────────────


class StripeService:
    """Encapsula toda la lógica de Stripe."""

    # ── Customer ──────────────────────────────────────────────────────────

    def get_or_create_customer(self, user_id: str, email: str) -> str:
        """Obtiene o crea un Stripe Customer. Guarda ID en users."""
        from shared.db import execute, query_one

        # ¿Ya tiene stripe_customer_id?
        row = query_one(
            "SELECT stripe_customer_id FROM users WHERE id = %s",
            [user_id],
        )
        if row and row.get("stripe_customer_id"):
            return row["stripe_customer_id"]

        # Crear en Stripe
        stripe = _get_stripe()
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id},
        )
        cust_id = customer["id"]

        # Guardar en users
        execute(
            "UPDATE users SET stripe_customer_id = %s WHERE id = %s",
            [cust_id, user_id],
        )
        log.info("Stripe customer creado: %s → %s", user_id, cust_id)
        return cust_id

    # ── Checkout Session (suscripción) ────────────────────────────────────

    def create_checkout_session(self, user_id: str, email: str, plan: str) -> str:
        """Crea una Checkout Session de Stripe para suscripción.

        Returns:
            URL de la Checkout Session (redirigir al usuario aquí).
        """
        if plan not in ("starter", "pro"):
            raise ValueError(f"Plan '{plan}' no disponible para checkout")

        stripe = _get_stripe()
        customer_id = self.get_or_create_customer(user_id, email)
        price_id = _get_plan_price(plan)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{_FRONTEND_URL}/billing?success=true",
            cancel_url=f"{_FRONTEND_URL}/billing?canceled=true",
            metadata={"user_id": user_id, "plan": plan},
        )
        log.info("Checkout session creada: %s → plan %s", user_id, plan)
        return session.url

    # ── Checkout Session (pack extra, one-time) ───────────────────────────

    def create_pack_checkout(
        self, user_id: str, email: str, pack_type: str
    ) -> str:
        """Crea una Checkout Session para compra de pack extra (one-time).

        Returns:
            URL de la Checkout Session.
        """
        if pack_type not in ("backtests", "trainings", "ticker"):
            raise ValueError(f"Pack '{pack_type}' no válido")

        stripe = _get_stripe()
        customer_id = self.get_or_create_customer(user_id, email)
        price_id = _get_pack_price(pack_type)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{_FRONTEND_URL}/billing?pack_success=true",
            cancel_url=f"{_FRONTEND_URL}/billing?canceled=true",
            metadata={
                "user_id": user_id,
                "pack_type": pack_type,
                "type": "pack",
            },
        )
        log.info("Pack checkout creado: %s → %s", user_id, pack_type)
        return session.url

    # ── Portal (gestión de suscripción) ───────────────────────────────────

    def create_portal_session(self, user_id: str, email: str) -> str:
        """Crea una sesión del Customer Portal de Stripe.

        Returns:
            URL del portal (redirigir al usuario aquí).
        """
        stripe = _get_stripe()
        customer_id = self.get_or_create_customer(user_id, email)

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{_FRONTEND_URL}/billing",
        )
        return session.url

    # ── Cancel ────────────────────────────────────────────────────────────

    def cancel_subscription(self, user_id: str) -> dict:
        """Cancela la suscripción al final del período actual.

        Returns:
            dict con estado de la suscripción.
        """
        from shared.db import query_one

        sub = query_one(
            """SELECT stripe_subscription_id, status
               FROM subscriptions
               WHERE user_id = %s AND status IN ('active', 'past_due', 'trialing')
               ORDER BY created_at DESC LIMIT 1""",
            [user_id],
        )
        if not sub or not sub.get("stripe_subscription_id"):
            raise ValueError("No hay suscripción activa para cancelar")

        stripe = _get_stripe()
        updated = stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=True,
        )
        log.info("Suscripción cancelada (al final del período): %s", user_id)
        return {
            "status": updated["status"],
            "cancel_at_period_end": updated["cancel_at_period_end"],
            "current_period_end": datetime.fromtimestamp(
                updated["current_period_end"], tz=UTC
            ).isoformat(),
        }

    # ── Subscription status ───────────────────────────────────────────────

    def get_subscription(self, user_id: str) -> dict | None:
        """Devuelve el estado de la suscripción desde nuestra DB."""
        from shared.db import query_one

        return query_one(
            """SELECT plan, status, current_period_start, current_period_end,
                      cancel_at_period_end, created_at, updated_at
               FROM subscriptions
               WHERE user_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            [user_id],
        )

    # ── Webhooks ──────────────────────────────────────────────────────────

    def process_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Procesa un evento de webhook de Stripe.

        Args:
            payload: body raw del request
            sig_header: header Stripe-Signature

        Returns:
            dict con el resultado del procesamiento
        """
        stripe = _get_stripe()
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET no configurada")

        # Verificar firma
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

        event_id = event["id"]
        event_type = event["type"]

        # Idempotencia: si ya procesamos este evento, skip
        if self._event_already_processed(event_id):
            log.info("Webhook duplicado (skip): %s %s", event_type, event_id)
            return {"status": "duplicate", "event_id": event_id}

        # Dispatch por tipo de evento
        handler = _WEBHOOK_HANDLERS.get(event_type)
        if handler:
            handler(event["data"]["object"])
            log.info("Webhook procesado: %s %s", event_type, event_id)
        else:
            log.debug("Webhook ignorado (tipo no manejado): %s", event_type)

        # Marcar como procesado
        self._mark_event_processed(event_id, event_type)
        return {"status": "processed", "event_type": event_type}

    # ── Helpers internos ──────────────────────────────────────────────────

    @staticmethod
    def _event_already_processed(event_id: str) -> bool:
        from shared.db import query_one

        row = query_one(
            "SELECT event_id FROM stripe_events WHERE event_id = %s",
            [event_id],
        )
        return row is not None

    @staticmethod
    def _mark_event_processed(event_id: str, event_type: str) -> None:
        from shared.db import execute

        execute(
            """INSERT INTO stripe_events (event_id, event_type)
               VALUES (%s, %s)
               ON CONFLICT (event_id) DO NOTHING""",
            [event_id, event_type],
        )


# ── Webhook handlers (funciones standalone) ──────────────────────────────────


def _handle_checkout_completed(session: dict) -> None:
    """checkout.session.completed — suscripción nueva o pack comprado."""
    from shared.db import execute, query_one

    metadata = session.get("metadata", {})
    user_id = metadata.get("user_id")
    if not user_id:
        log.warning("checkout.session.completed sin user_id en metadata")
        return

    # ¿Es un pack extra?
    if metadata.get("type") == "pack":
        _apply_pack_credits(user_id, metadata.get("pack_type", ""))
        return

    # Suscripción: obtener detalles
    stripe = _get_stripe()
    sub_id = session.get("subscription")
    if not sub_id:
        log.warning("checkout.session.completed sin subscription ID")
        return

    sub = stripe.Subscription.retrieve(sub_id)
    plan = metadata.get("plan", "starter")
    customer_id = session.get("customer", "")

    # Actualizar users.plan
    execute(
        "UPDATE users SET plan = %s, stripe_customer_id = %s WHERE id = %s",
        [plan, customer_id, user_id],
    )

    # Upsert en subscriptions
    existing = query_one(
        "SELECT id FROM subscriptions WHERE user_id = %s",
        [user_id],
    )

    period_start = datetime.fromtimestamp(
        sub["current_period_start"], tz=UTC
    )
    period_end = datetime.fromtimestamp(
        sub["current_period_end"], tz=UTC
    )

    if existing:
        execute(
            """UPDATE subscriptions
               SET stripe_customer_id = %s,
                   stripe_subscription_id = %s,
                   plan = %s,
                   status = %s,
                   current_period_start = %s,
                   current_period_end = %s,
                   cancel_at_period_end = %s,
                   updated_at = NOW()
               WHERE user_id = %s""",
            [
                customer_id, sub_id, plan, sub["status"],
                period_start, period_end,
                sub.get("cancel_at_period_end", False),
                user_id,
            ],
        )
    else:
        execute(
            """INSERT INTO subscriptions
               (user_id, stripe_customer_id, stripe_subscription_id,
                plan, status, current_period_start, current_period_end,
                cancel_at_period_end)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                user_id, customer_id, sub_id,
                plan, sub["status"], period_start, period_end,
                sub.get("cancel_at_period_end", False),
            ],
        )

    log.info("Suscripción activada: user=%s plan=%s", user_id, plan)


def _handle_invoice_paid(invoice: dict) -> None:
    """invoice.paid — renovación exitosa."""
    from shared.db import execute

    sub_id = invoice.get("subscription")
    if not sub_id:
        return

    # Actualizar status a active (por si estaba past_due)
    execute(
        """UPDATE subscriptions
           SET status = 'active', updated_at = NOW()
           WHERE stripe_subscription_id = %s""",
        [sub_id],
    )
    log.info("Invoice pagado OK: sub=%s", sub_id)


def _handle_invoice_failed(invoice: dict) -> None:
    """invoice.payment_failed — pago fallido, marcar past_due."""
    from shared.db import execute

    sub_id = invoice.get("subscription")
    if not sub_id:
        return

    execute(
        """UPDATE subscriptions
           SET status = 'past_due', updated_at = NOW()
           WHERE stripe_subscription_id = %s""",
        [sub_id],
    )
    log.warning("Invoice fallido: sub=%s", sub_id)


def _handle_subscription_updated(sub: dict) -> None:
    """customer.subscription.updated — cambio de plan u otro update."""
    from shared.db import execute, query_one

    sub_id = sub["id"]

    # Detectar plan desde price
    items = sub.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else ""

    # Buscar qué plan corresponde a ese price
    _load_prices()
    new_plan = None
    for plan_name, pid in _PLAN_PRICES.items():
        if pid == price_id:
            new_plan = plan_name
            break

    period_start = datetime.fromtimestamp(
        sub["current_period_start"], tz=UTC
    )
    period_end = datetime.fromtimestamp(
        sub["current_period_end"], tz=UTC
    )

    # Actualizar subscriptions
    execute(
        """UPDATE subscriptions
           SET status = %s,
               plan = COALESCE(%s, plan),
               current_period_start = %s,
               current_period_end = %s,
               cancel_at_period_end = %s,
               updated_at = NOW()
           WHERE stripe_subscription_id = %s""",
        [
            sub["status"], new_plan, period_start, period_end,
            sub.get("cancel_at_period_end", False), sub_id,
        ],
    )

    # Si detectamos el nuevo plan, actualizar users.plan
    if new_plan:
        row = query_one(
            "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = %s",
            [sub_id],
        )
        if row:
            execute(
                "UPDATE users SET plan = %s WHERE id = %s",
                [new_plan, row["user_id"]],
            )
            log.info(
                "Plan actualizado via webhook: user=%s → %s",
                row["user_id"], new_plan,
            )


def _handle_subscription_deleted(sub: dict) -> None:
    """customer.subscription.deleted — suscripción cancelada definitivamente."""
    from shared.db import execute, query_one

    sub_id = sub["id"]

    # Marcar subscripción como cancelada
    execute(
        """UPDATE subscriptions
           SET status = 'canceled', updated_at = NOW()
           WHERE stripe_subscription_id = %s""",
        [sub_id],
    )

    # Degradar usuario a trial
    row = query_one(
        "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = %s",
        [sub_id],
    )
    if row:
        execute(
            "UPDATE users SET plan = 'trial' WHERE id = %s",
            [row["user_id"]],
        )
        log.info("Suscripción eliminada, degradado a trial: user=%s", row["user_id"])


def _apply_pack_credits(user_id: str, pack_type: str) -> None:
    """Aplica créditos extra de un pack comprado."""
    from shared.db import execute

    if pack_type in _PACK_CREDITS:
        col, amount = _PACK_CREDITS[pack_type]
        execute(
            f"UPDATE user_credits SET {col} = {col} + %s WHERE user_id = %s",  # noqa: S608
            [amount, user_id],
        )
        log.info("Pack aplicado: user=%s %s +%d", user_id, col, amount)

    elif pack_type == "ticker":
        # Añadir 1 ticker extra por 1 mes
        import json

        execute(
            """UPDATE user_credits
               SET extra_tickers = extra_tickers || %s::jsonb
               WHERE user_id = %s""",
            [
                json.dumps([{
                    "ticker": "_placeholder",
                    "expires_at": (
                        datetime.now(UTC).replace(day=1)
                    ).isoformat(),
                }]),
                user_id,
            ],
        )
        log.info("Pack ticker aplicado: user=%s", user_id)


# ── Dispatch table ────────────────────────────────────────────────────────────

_WEBHOOK_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_failed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}

# ── Singleton ─────────────────────────────────────────────────────────────────

stripe_svc = StripeService()
