"use client";

import { useState, useEffect, useCallback } from "react";
import { Check, Plus, Settings, Trash2, X } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS } from "@/lib/types";

export default function SettingsPage() {
  const { user, preferences, fetchMe } = useAuthStore();
  const [tickers, setTickers] = useState<string[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [tickerError, setTickerError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (preferences?.tickers) {
      setTickers(
        Array.isArray(preferences.tickers)
          ? preferences.tickers
          : []
      );
    }
  }, [preferences]);

  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;

  const handleAddTicker = useCallback(async () => {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    setTickerError("");
    setSaving(true);
    try {
      const { data } = await api.put("/api/preferences/tickers", {
        action: "add",
        ticker: t,
      });
      setTickers(data.tickers || []);
      setNewTicker("");
      fetchMe();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string | { error?: string } } } })
          .response?.data?.detail;
      if (typeof msg === "string") setTickerError(msg);
      else if (typeof msg === "object" && msg?.error === "plan_limit_exceeded")
        setTickerError(`Límite de ${limits.max_tickers} tickers alcanzado`);
      else setTickerError("Error al añadir ticker");
    } finally {
      setSaving(false);
    }
  }, [newTicker, fetchMe, limits.max_tickers]);

  const handleRemoveTicker = async (ticker: string) => {
    try {
      const { data } = await api.put("/api/preferences/tickers", {
        action: "remove",
        ticker,
      });
      setTickers(data.tickers || []);
      fetchMe();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <Settings size={22} style={{ color: "var(--accent-cyan)" }} />
        <h1
          className="text-lg font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Configuración
        </h1>
      </div>

      {/* Tickers */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            Tickers seguidos
          </h2>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {tickers.length}/{limits.max_tickers}
          </span>
        </div>

        {/* Add ticker */}
        <div className="flex gap-2">
          <input
            type="text"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleAddTicker()}
            placeholder="AAPL, MSFT, TSLA..."
            className="input-glass flex-1"
            maxLength={10}
          />
          <button
            onClick={handleAddTicker}
            disabled={saving || !newTicker.trim()}
            className="btn-primary flex items-center gap-1.5"
          >
            <Plus size={14} />
            Añadir
          </button>
        </div>
        {tickerError && (
          <p className="text-xs" style={{ color: "var(--accent-red)" }}>
            {tickerError}
          </p>
        )}

        {/* Ticker list */}
        <div className="flex flex-wrap gap-2">
          {tickers.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-mono"
              style={{
                background: "var(--accent-cyan-dim)",
                color: "var(--accent-cyan)",
                border: "1px solid rgba(6,182,212,0.2)",
              }}
            >
              {t}
              <button
                onClick={() => handleRemoveTicker(t)}
                className="hover:opacity-70"
              >
                <X size={12} />
              </button>
            </span>
          ))}
          {tickers.length === 0 && (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              No sigues ningún ticker
            </p>
          )}
        </div>
      </div>

      {/* Profile */}
      <div className="glass-card p-5 space-y-3">
        <h2
          className="text-sm font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Perfil
        </h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Email
            </span>
            <p style={{ color: "var(--text-primary)" }}>{user?.email}</p>
          </div>
          <div>
            <span
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Nombre
            </span>
            <p style={{ color: "var(--text-primary)" }}>
              {user?.display_name || "—"}
            </p>
          </div>
          <div>
            <span
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Plan
            </span>
            <p
              className="font-medium capitalize"
              style={{ color: "var(--accent-cyan)" }}
            >
              {user?.plan}
            </p>
          </div>
          <div>
            <span
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Miembro desde
            </span>
            <p style={{ color: "var(--text-primary)" }}>
              {user?.created_at
                ? new Date(user.created_at).toLocaleDateString("es-ES")
                : "—"}
            </p>
          </div>
        </div>
      </div>

      {/* Plan info */}
      <div className="glass-card p-5 space-y-3">
        <h2
          className="text-sm font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Límites del plan {limits.label}
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Tickers RT", value: limits.max_tickers },
            { label: "Custom models", value: limits.max_custom_models },
            { label: "Backtests/mes", value: limits.max_backtests_month },
            { label: "Trainings/mes", value: limits.max_trainings_month },
            { label: "Guardrails", value: limits.guardrails_count },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between px-3 py-2 rounded-lg"
              style={{ background: "rgba(15,23,42,0.5)" }}
            >
              <span
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {item.label}
              </span>
              <span
                className="text-sm font-mono font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
