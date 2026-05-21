"use client";

import { Settings, User, Bell, Shield } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS } from "@/lib/types";

export default function SettingsPage() {
  const { user, preferences } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <Settings size={22} style={{ color: "var(--accent-cyan)" }} />
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Configuración
        </h1>
      </div>

      {/* Profile */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-2">
          <User size={16} style={{ color: "var(--accent-cyan)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Perfil</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            { label: "Email", value: user?.email },
            { label: "Nombre", value: user?.display_name || "—" },
            { label: "Plan", value: user?.plan, color: "var(--accent-cyan)" },
            { label: "Miembro desde", value: user?.created_at ? new Date(user.created_at).toLocaleDateString("es-ES") : "—" },
          ].map((item) => (
            <div key={item.label}>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{item.label}</span>
              <p className="font-medium capitalize" style={{ color: item.color || "var(--text-primary)" }}>
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Notifications */}
      <div className="glass-card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Bell size={16} style={{ color: "var(--accent-amber)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Notificaciones</h2>
        </div>
        {[
          { label: "Push activadas", on: true },
          { label: "Solo alta prioridad", on: true },
          { label: "Sonido", on: false },
        ].map((item) => (
          <div key={item.label} className="flex items-center justify-between">
            <span className="text-sm" style={{ color: "var(--text-primary)" }}>{item.label}</span>
            <button
              className="w-8 h-5 rounded-full relative"
              style={{
                background: item.on ? "var(--accent-cyan)" : "var(--border-glass-hover)",
                border: "none",
                cursor: "pointer",
              }}
            >
              <div
                className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150"
                style={{ left: item.on ? 16 : 2 }}
              />
            </button>
          </div>
        ))}
      </div>

      {/* Plan limits */}
      <div className="glass-card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Shield size={16} style={{ color: "var(--accent-violet)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Límites del plan {limits.label}
          </h2>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Tickers RT", value: limits.max_tickers },
            { label: "Custom models", value: limits.max_custom_models },
            { label: "Backtests/mes", value: limits.max_backtests_month },
            { label: "Trainings/mes", value: limits.max_trainings_month },
            { label: "Guardrails", value: limits.guardrails_count },
            { label: "Hist. máx (backtest)", value: `${limits.max_hist_days}d` },
            { label: "Modelos por backtest", value: limits.max_models_backtest },
            { label: "Ventana training", value: `${limits.max_training_days}d` },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between px-3 py-2 rounded-lg"
              style={{ background: "rgba(15,23,42,0.5)" }}
            >
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{item.label}</span>
              <span className="text-sm font-mono font-medium" style={{ color: "var(--text-primary)" }}>
                {item.value}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Los tickers se gestionan desde la pestaña Squawks (botón +).
        </p>
      </div>
    </div>
  );
}
