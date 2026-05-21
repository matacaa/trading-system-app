"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Check,
  CreditCard,
  Crown,
  ExternalLink,
  Package,
  Star,
  Zap,
} from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS } from "@/lib/types";
import type { Subscription } from "@/lib/types";

const PLANS = [
  {
    key: "trial",
    icon: Zap,
    color: "var(--accent-amber)",
    features: [
      "1 ticker RT",
      "5 backtests/mes",
      "8 guardrails",
      "14 días gratis",
    ],
  },
  {
    key: "starter",
    icon: Star,
    color: "var(--accent-cyan)",
    features: [
      "3 tickers RT",
      "3 custom models",
      "20 backtests/mes",
      "5 trainings/mes",
      "12 guardrails",
    ],
  },
  {
    key: "pro",
    icon: Crown,
    color: "var(--accent-violet)",
    features: [
      "10 tickers RT",
      "12 custom models",
      "50 backtests/mes",
      "20 trainings/mes",
      "Todos los guardrails",
    ],
  },
];

const PACKS = [
  {
    type: "backtests",
    label: "10 Backtests extra",
    price: "4,99 €",
    icon: "📊",
  },
  {
    type: "trainings",
    label: "5 Trainings extra",
    price: "9,99 €",
    icon: "🧠",
  },
  {
    type: "ticker",
    label: "1 Ticker extra (1 mes)",
    price: "2,99 €",
    icon: "📈",
  },
];

export default function BillingPage() {
  const { user, fetchMe } = useAuthStore();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchSubscription = useCallback(async () => {
    try {
      const { data } = await api.get("/api/stripe/subscription");
      setSubscription(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  const handleCheckout = async (plan: string) => {
    setActionLoading(plan);
    try {
      const { data } = await api.post("/api/stripe/checkout", { plan });
      window.location.href = data.checkout_url;
    } catch {
      alert("Error al crear sesión de pago");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePortal = async () => {
    setActionLoading("portal");
    try {
      const { data } = await api.post("/api/stripe/portal");
      window.location.href = data.portal_url;
    } catch {
      alert("Error al abrir el portal");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async () => {
    if (!confirm("¿Cancelar tu suscripción al final del período actual?"))
      return;
    setActionLoading("cancel");
    try {
      await api.post("/api/stripe/cancel");
      fetchSubscription();
      fetchMe();
    } catch {
      alert("Error al cancelar");
    } finally {
      setActionLoading(null);
    }
  };

  const handleBuyPack = async (packType: string) => {
    setActionLoading(packType);
    try {
      const { data } = await api.post("/api/stripe/buy-pack", {
        pack_type: packType,
      });
      window.location.href = data.checkout_url;
    } catch {
      alert("Error al comprar pack");
    } finally {
      setActionLoading(null);
    }
  };

  const currentPlan = user?.plan || "trial";

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <CreditCard size={22} style={{ color: "var(--accent-cyan)" }} />
        <h1
          className="text-lg font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Billing
        </h1>
      </div>

      {/* Current subscription status */}
      {subscription?.has_subscription && (
        <div
          className="glass-card p-5 flex items-center justify-between"
          style={{ border: "1px solid rgba(6,182,212,0.2)" }}
        >
          <div>
            <p
              className="text-sm font-medium"
              style={{ color: "var(--text-primary)" }}
            >
              Suscripción activa:{" "}
              <span
                className="capitalize"
                style={{ color: "var(--accent-cyan)" }}
              >
                {subscription.plan}
              </span>
            </p>
            {subscription.period_end && (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {subscription.cancel_at_period_end
                  ? "Se cancelará el"
                  : "Próxima renovación:"}{" "}
                {new Date(subscription.period_end).toLocaleDateString("es-ES")}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={handlePortal}
              disabled={actionLoading === "portal"}
              className="btn-secondary flex items-center gap-1.5 text-xs"
            >
              <ExternalLink size={12} />
              Gestionar
            </button>
            {!subscription.cancel_at_period_end && (
              <button
                onClick={handleCancel}
                disabled={actionLoading === "cancel"}
                className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                style={{
                  color: "var(--accent-red)",
                  border: "1px solid rgba(239,68,68,0.2)",
                }}
              >
                Cancelar
              </button>
            )}
          </div>
        </div>
      )}

      {/* Plans */}
      <div className="grid grid-cols-3 gap-4">
        {PLANS.map((plan) => {
          const info = PLAN_LIMITS[plan.key];
          const isCurrent = currentPlan === plan.key;
          const Icon = plan.icon;

          return (
            <div
              key={plan.key}
              className="glass-card p-5 flex flex-col"
              style={{
                border: isCurrent
                  ? `1px solid ${plan.color}`
                  : "1px solid var(--border-glass)",
              }}
            >
              <div className="flex items-center gap-2 mb-3">
                <Icon size={18} style={{ color: plan.color }} />
                <h3
                  className="text-sm font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {info.label}
                </h3>
                {isCurrent && (
                  <span
                    className="text-[0.6rem] font-bold px-1.5 py-0.5 rounded-full ml-auto"
                    style={{ background: `${plan.color}20`, color: plan.color }}
                  >
                    ACTUAL
                  </span>
                )}
              </div>

              <p
                className="text-2xl font-bold mb-4"
                style={{ color: plan.color }}
              >
                {info.price}
              </p>

              <ul className="space-y-2 mb-5 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-xs">
                    <Check
                      size={12}
                      className="flex-shrink-0 mt-0.5"
                      style={{ color: plan.color }}
                    />
                    <span style={{ color: "var(--text-secondary)" }}>{f}</span>
                  </li>
                ))}
              </ul>

              {!isCurrent && plan.key !== "trial" && (
                <button
                  onClick={() => handleCheckout(plan.key)}
                  disabled={actionLoading === plan.key}
                  className="btn-primary w-full text-sm"
                  style={{
                    background: `linear-gradient(135deg, ${plan.color}, ${plan.color}cc)`,
                  }}
                >
                  {actionLoading === plan.key
                    ? "Redirigiendo..."
                    : currentPlan === "trial"
                      ? "Empezar"
                      : "Cambiar"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Extra packs */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Package size={16} style={{ color: "var(--text-muted)" }} />
          <h2
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            Packs extra
          </h2>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {PACKS.map((pack) => (
            <div key={pack.type} className="glass-card p-4">
              <div className="text-2xl mb-2">{pack.icon}</div>
              <p
                className="text-sm font-medium mb-1"
                style={{ color: "var(--text-primary)" }}
              >
                {pack.label}
              </p>
              <p
                className="text-lg font-bold mb-3"
                style={{ color: "var(--accent-cyan)" }}
              >
                {pack.price}
              </p>
              <button
                onClick={() => handleBuyPack(pack.type)}
                disabled={actionLoading === pack.type}
                className="btn-secondary w-full text-xs"
              >
                {actionLoading === pack.type ? "..." : "Comprar"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
