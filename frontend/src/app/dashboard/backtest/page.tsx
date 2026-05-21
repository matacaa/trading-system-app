"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart3, Plus, Trash2, TrendingUp, Play } from "lucide-react";
import api from "@/lib/api";
import type { Backtest, BacktestUsage } from "@/lib/types";
import BacktestForm from "@/components/backtest-form";
import EquityCurve from "@/components/equity-curve";

export default function BacktestPage() {
  const [backtests, setBacktests] = useState<Backtest[]>([]);
  const [usage, setUsage] = useState<BacktestUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [btRes, usageRes] = await Promise.all([
        api.get("/api/backtest/list"),
        api.get("/api/backtest/usage"),
      ]);
      setBacktests(btRes.data.backtests || []);
      setUsage(usageRes.data);
    } catch {
      /* silently fail */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (id: string) => {
    if (!confirm("¿Eliminar este backtest?")) return;
    try {
      await api.delete(`/api/backtest/${id}`);
      setBacktests((prev) => prev.filter((b) => b.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch {
      /* ignore */
    }
  };

  const selected = backtests.find((b) => b.id === selectedId);

  return (
    <div className="space-y-5">
      {/* Header + Usage */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BarChart3 size={22} style={{ color: "var(--accent-cyan)" }} />
          <h1
            className="text-lg font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            Backtests
          </h1>
        </div>
        <div className="flex items-center gap-4">
          {usage && (
            <div className="flex items-center gap-3">
              <span
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                {usage.used_this_month}/{usage.limit_month} este mes
              </span>
              <div
                className="w-24 h-1.5 rounded-full"
                style={{ background: "rgba(100,116,139,0.15)" }}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, (usage.used_this_month / usage.limit_month) * 100)}%`,
                    background:
                      usage.remaining_month <= 2
                        ? "var(--accent-red)"
                        : "var(--accent-cyan)",
                  }}
                />
              </div>
            </div>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary flex items-center gap-1.5 text-xs"
          >
            <Plus size={14} />
            Nuevo Backtest
          </button>
        </div>
      </div>

      {/* Form */}
      {showForm && (
        <BacktestForm
          onSuccess={() => {
            setShowForm(false);
            fetchData();
          }}
          onClose={() => setShowForm(false)}
        />
      )}

      {/* List */}
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
          </div>
        ) : backtests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <BarChart3
              size={32}
              style={{ color: "var(--text-muted)", opacity: 0.3 }}
            />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Aún no tienes backtests
            </p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Lanza tu primer backtest para evaluar una estrategia
            </p>
          </div>
        ) : (
          <div
            className="divide-y"
            style={{ borderColor: "var(--border-glass)" }}
          >
            {backtests.map((bt) => (
              <button
                key={bt.id}
                onClick={() => setSelectedId(bt.id === selectedId ? null : bt.id)}
                className="w-full text-left px-5 py-4 flex items-center justify-between transition-colors"
                style={{
                  background:
                    selectedId === bt.id
                      ? "var(--bg-glass-hover)"
                      : "transparent",
                }}
              >
                <div className="flex items-center gap-4">
                  <div
                    className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{
                      background:
                        bt.status === "completed"
                          ? "var(--accent-emerald-dim)"
                          : "var(--accent-red-dim)",
                      color:
                        bt.status === "completed"
                          ? "var(--accent-emerald)"
                          : "var(--accent-red)",
                    }}
                  >
                    {bt.status === "completed" ? (
                      <TrendingUp size={14} />
                    ) : (
                      <Play size={14} />
                    )}
                  </div>
                  <div>
                    <p
                      className="text-sm font-medium"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {bt.name || bt.ticker}
                    </p>
                    <p
                      className="text-xs"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {bt.ticker} · {bt.direction} · {bt.date_from} →{" "}
                      {bt.date_to}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  {bt.pnl_pct != null && (
                    <span
                      className="text-sm font-mono font-medium"
                      style={{
                        color:
                          bt.pnl_pct >= 0
                            ? "var(--accent-emerald)"
                            : "var(--accent-red)",
                      }}
                    >
                      {bt.pnl_pct >= 0 ? "+" : ""}
                      {bt.pnl_pct.toFixed(1)}%
                    </span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(bt.id);
                    }}
                    className="p-1.5 rounded-lg transition-colors"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Detail with equity curve */}
      {selected && (
        <div className="glass-card p-5 animate-fade-in space-y-4">
          <h3
            className="text-sm font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            {selected.name}
          </h3>

          {/* Metrics row */}
          <div className="grid grid-cols-5 gap-4">
            {[
              { label: "Trades", value: selected.total_trades ?? "—" },
              {
                label: "PnL",
                value:
                  selected.pnl_pct != null
                    ? `${selected.pnl_pct >= 0 ? "+" : ""}${selected.pnl_pct.toFixed(1)}%`
                    : "—",
                color:
                  selected.pnl_pct != null
                    ? selected.pnl_pct >= 0
                      ? "var(--accent-emerald)"
                      : "var(--accent-red)"
                    : undefined,
              },
              {
                label: "Win Rate",
                value:
                  selected.win_rate != null
                    ? `${(selected.win_rate * 100).toFixed(0)}%`
                    : "—",
              },
              {
                label: "Sharpe",
                value: selected.sharpe_ratio?.toFixed(2) ?? "—",
              },
              {
                label: "Max DD",
                value:
                  selected.max_drawdown != null
                    ? `${selected.max_drawdown.toFixed(1)}%`
                    : "—",
                color: "var(--accent-red)",
              },
            ].map((m) => (
              <div key={m.label}>
                <p
                  className="text-[0.65rem] uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  {m.label}
                </p>
                <p
                  className="text-lg font-mono font-bold"
                  style={{ color: m.color || "var(--text-primary)" }}
                >
                  {m.value}
                </p>
              </div>
            ))}
          </div>

          {/* Equity curve chart */}
          <div>
            <p
              className="text-[0.65rem] uppercase tracking-wider mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Equity Curve
            </p>
            <EquityCurve backtestId={selected.id} />
          </div>
        </div>
      )}
    </div>
  );
}
