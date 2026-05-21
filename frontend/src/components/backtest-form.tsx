"use client";

import { useState, useEffect } from "react";
import { Play, Search, X } from "lucide-react";
import api from "@/lib/api";

interface Ticker {
  ticker: string;
  name: string;
  sector: string | null;
}

interface Guardrail {
  name: string;
  label: string;
  category: string;
  phase: string;
}

interface BacktestFormProps {
  onSuccess: () => void;
  onClose: () => void;
}

export default function BacktestForm({ onSuccess, onClose }: BacktestFormProps) {
  const [name, setName] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [showTickerDropdown, setShowTickerDropdown] = useState(false);
  const [direction, setDirection] = useState<"long" | "short">("long");
  const [dateFrom, setDateFrom] = useState("2024-01-01");
  const [dateTo, setDateTo] = useState("2024-12-31");
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [enabledGuardrails, setEnabledGuardrails] = useState<
    Record<string, boolean>
  >({});
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  // Fetch tickers
  useEffect(() => {
    const fetchTickers = async () => {
      try {
        const { data } = await api.get("/api/tickers/universe", {
          params: { limit: 100 },
        });
        setTickers(data.tickers || []);
      } catch {
        /* ignore */
      }
    };
    fetchTickers();
  }, []);

  // Fetch guardrails
  useEffect(() => {
    const fetchGuardrails = async () => {
      try {
        const { data } = await api.get("/api/guardrails/available");
        setGuardrails(data.guardrails || []);
        // Enable all by default
        const defaults: Record<string, boolean> = {};
        for (const g of data.guardrails || []) {
          defaults[g.name] = true;
        }
        setEnabledGuardrails(defaults);
      } catch {
        /* ignore */
      }
    };
    fetchGuardrails();
  }, []);

  const filteredTickers = tickers.filter(
    (t) =>
      t.ticker.toLowerCase().includes(tickerSearch.toLowerCase()) ||
      (t.name && t.name.toLowerCase().includes(tickerSearch.toLowerCase()))
  );

  const handleSubmit = async () => {
    setErrors([]);
    setLoading(true);

    const guardrailsConfig: Record<string, boolean> = {};
    for (const [k, v] of Object.entries(enabledGuardrails)) {
      if (v) guardrailsConfig[k] = true;
    }

    try {
      await api.post("/api/backtest", {
        name: name || undefined,
        ticker,
        direction,
        date_from: dateFrom,
        date_to: dateTo,
        models_config: {},
        models_enabled: true,
        guardrails_config: guardrailsConfig,
      });
      onSuccess();
    } catch (err: unknown) {
      const resp = (
        err as { response?: { data?: { detail?: { errors?: string[] } | string } } }
      ).response?.data?.detail;
      if (typeof resp === "object" && resp?.errors) {
        setErrors(resp.errors);
      } else if (typeof resp === "string") {
        setErrors([resp]);
      } else {
        setErrors(["Error al lanzar backtest"]);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card p-5 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h3
          className="text-sm font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Nuevo Backtest
        </h3>
        <button onClick={onClose} style={{ color: "var(--text-muted)" }}>
          <X size={16} />
        </button>
      </div>

      {errors.length > 0 && (
        <div
          className="px-4 py-3 rounded-lg space-y-1"
          style={{
            background: "var(--accent-red-dim)",
            border: "1px solid rgba(239,68,68,0.2)",
          }}
        >
          {errors.map((e, i) => (
            <p key={i} className="text-xs" style={{ color: "var(--accent-red)" }}>
              {e}
            </p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Name */}
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Nombre (opcional)
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input-glass"
            placeholder="Mi backtest"
          />
        </div>

        {/* Ticker */}
        <div className="relative">
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Ticker
          </label>
          <div className="relative">
            <input
              type="text"
              value={showTickerDropdown ? tickerSearch : ticker}
              onChange={(e) => {
                setTickerSearch(e.target.value);
                setShowTickerDropdown(true);
              }}
              onFocus={() => setShowTickerDropdown(true)}
              className="input-glass pl-8"
              placeholder="Buscar ticker..."
            />
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2"
              style={{ color: "var(--text-muted)" }}
            />
          </div>
          {showTickerDropdown && (
            <div
              className="absolute z-50 top-full left-0 right-0 mt-1 max-h-48 overflow-y-auto rounded-lg"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-glass)",
                boxShadow: "var(--shadow-glass)",
              }}
            >
              {filteredTickers.slice(0, 20).map((t) => (
                <button
                  key={t.ticker}
                  onClick={() => {
                    setTicker(t.ticker);
                    setTickerSearch("");
                    setShowTickerDropdown(false);
                  }}
                  className="w-full text-left px-3 py-2 text-xs flex justify-between transition-colors"
                  style={{ color: "var(--text-primary)" }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = "var(--bg-glass-hover)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "transparent")
                  }
                >
                  <span className="font-mono font-medium">{t.ticker}</span>
                  <span style={{ color: "var(--text-muted)" }}>
                    {t.name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Direction */}
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Dirección
          </label>
          <div className="flex gap-2">
            {(["long", "short"] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDirection(d)}
                className="flex-1 py-2 rounded-lg text-xs font-semibold uppercase transition-all"
                style={{
                  background:
                    direction === d
                      ? d === "long"
                        ? "var(--accent-emerald-dim)"
                        : "var(--accent-red-dim)"
                      : "rgba(15,23,42,0.5)",
                  color:
                    direction === d
                      ? d === "long"
                        ? "var(--accent-emerald)"
                        : "var(--accent-red)"
                      : "var(--text-muted)",
                  border: `1px solid ${
                    direction === d
                      ? d === "long"
                        ? "rgba(16,185,129,0.3)"
                        : "rgba(239,68,68,0.3)"
                      : "var(--border-glass)"
                  }`,
                }}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* Dates */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--text-secondary)" }}
            >
              Desde
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="input-glass"
            />
          </div>
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--text-secondary)" }}
            >
              Hasta
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="input-glass"
            />
          </div>
        </div>
      </div>

      {/* Guardrails */}
      {guardrails.length > 0 && (
        <div>
          <label
            className="block text-xs font-medium mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            Guardrails ({Object.values(enabledGuardrails).filter(Boolean).length}/{guardrails.length})
          </label>
          <div className="flex flex-wrap gap-2">
            {guardrails.map((g) => (
              <button
                key={g.name}
                onClick={() =>
                  setEnabledGuardrails((prev) => ({
                    ...prev,
                    [g.name]: !prev[g.name],
                  }))
                }
                className="text-[0.65rem] font-medium px-2.5 py-1.5 rounded-lg transition-all"
                style={{
                  background: enabledGuardrails[g.name]
                    ? "var(--accent-emerald-dim)"
                    : "rgba(15,23,42,0.5)",
                  color: enabledGuardrails[g.name]
                    ? "var(--accent-emerald)"
                    : "var(--text-muted)",
                  border: `1px solid ${
                    enabledGuardrails[g.name]
                      ? "rgba(16,185,129,0.2)"
                      : "var(--border-glass)"
                  }`,
                }}
              >
                {g.label || g.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={loading}
        className="btn-primary w-full flex items-center justify-center gap-2"
      >
        {loading ? (
          <div className="spin-slow w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
        ) : (
          <Play size={14} />
        )}
        {loading ? "Ejecutando backtest..." : "Lanzar Backtest"}
      </button>
    </div>
  );
}
