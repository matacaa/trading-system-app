"use client";

import { useEffect, useState, useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Bar,
} from "recharts";
import { ChevronDown } from "lucide-react";
import api from "@/lib/api";

interface PriceChartProps {
  ticker: string;
}

interface DataPoint {
  ts: string;
  close: number;
  [key: string]: unknown;
}

const INDICATORS = [
  { key: "ema_9", label: "EMA 9", color: "#fbbf24", panel: "overlay" },
  { key: "ema_21", label: "EMA 21", color: "#a3e635", panel: "overlay" },
  { key: "vwap", label: "VWAP", color: "#34d399", panel: "overlay" },
  { key: "rsi_14", label: "RSI (14)", color: "#a78bfa", panel: "bottom" },
  { key: "macd_line", label: "MACD", color: "#22d3ee", panel: "bottom" },
  { key: "volume", label: "Volumen", color: "#6366f1", panel: "bottom" },
];

export default function PriceChart({ ticker }: PriceChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeInds, setActiveInds] = useState<string[]>([]);
  const [showMenu, setShowMenu] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);

    const indKeys = ["close", ...activeInds].join(",");
    api
      .get(`/api/tickers/${ticker}/indicators`, {
        params: { indicators: indKeys, limit: 200 },
      })
      .then(({ data: res }) => {
        if (!cancelled) setData(res.data || []);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [ticker, activeInds]);

  const toggleInd = (key: string) => {
    setActiveInds((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const overlays = INDICATORS.filter(
    (i) => i.panel === "overlay" && activeInds.includes(i.key)
  );
  const bottoms = INDICATORS.filter(
    (i) => i.panel === "bottom" && activeInds.includes(i.key)
  );

  const formatTime = (ts: string) => {
    const d = new Date(ts);
    return `${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
  };

  if (loading && data.length === 0) {
    return (
      <div
        className="glass-card flex items-center justify-center"
        style={{ height: 200 }}
      >
        <div className="spin-slow w-5 h-5 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div
        className="glass-card flex items-center justify-center"
        style={{ height: 200 }}
      >
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Sin datos de precio para {ticker}
        </span>
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderBottom: "1px solid var(--border-glass)" }}
      >
        <span className="text-[0.65rem]" style={{ color: "var(--text-muted)" }}>
          {ticker} — Precio{overlays.length > 0 && ` + ${overlays.map((i) => i.label).join(", ")}`}
        </span>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded-md"
            style={{
              border: "1px solid var(--border-glass)",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            Indicadores
            {activeInds.length > 0 && (
              <span
                className="text-[0.6rem] px-1.5 rounded-full font-bold"
                style={{ background: "var(--accent-cyan)", color: "white" }}
              >
                {activeInds.length}
              </span>
            )}
            <ChevronDown size={12} />
          </button>
          {showMenu && (
            <div
              className="absolute top-full right-0 mt-1 w-44 rounded-lg p-1 z-20"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-glass)",
                boxShadow: "var(--shadow-glass)",
              }}
            >
              {INDICATORS.map((ind) => {
                const isOn = activeInds.includes(ind.key);
                return (
                  <button
                    key={ind.key}
                    onClick={() => toggleInd(ind.key)}
                    className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-xs text-left"
                    style={{
                      background: isOn ? "rgba(255,255,255,0.06)" : "transparent",
                      color: "var(--text-primary)",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    <span
                      className="w-2 h-2 rounded-sm flex-shrink-0"
                      style={{ background: ind.color }}
                    />
                    <span className="flex-1">{ind.label}</span>
                    {isOn && (
                      <span style={{ color: "var(--accent-cyan)" }}>✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Price chart */}
      <div style={{ height: 180 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`pg-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.08)" vertical={false} />
            <XAxis
              dataKey="ts"
              tick={{ fill: "#64748b", fontSize: 9 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(100,116,139,0.1)" }}
              tickFormatter={formatTime}
              interval="preserveStartEnd"
              minTickGap={50}
            />
            <YAxis
              tick={{ fill: "#64748b", fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              width={50}
              domain={["auto", "auto"]}
              tickFormatter={(v) => Number(v).toFixed(1)}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(17,24,39,0.95)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 8,
                fontSize: 11,
                color: "#f1f5f9",
              }}
              labelFormatter={(v) => {
                const d = new Date(String(v));
                return d.toLocaleString("es-ES", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
              }}
            />
            <Area
              type="monotone"
              dataKey="close"
              stroke="#06b6d4"
              strokeWidth={1.5}
              fill={`url(#pg-${ticker})`}
              name="Precio"
            />
            {overlays.map((ind) => (
              <Line
                key={ind.key}
                type="monotone"
                dataKey={ind.key}
                stroke={ind.color}
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                name={ind.label}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Bottom panels for RSI/MACD/Volume */}
      {bottoms.map((ind) => (
        <div
          key={ind.key}
          style={{ height: 60, borderTop: "1px solid var(--border-glass)" }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="ts" hide />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 8 }}
                tickLine={false}
                axisLine={false}
                width={50}
                domain={["auto", "auto"]}
              />
              {ind.key === "volume" ? (
                <Bar dataKey={ind.key} fill={ind.color} opacity={0.4} name={ind.label} />
              ) : (
                <Line
                  type="monotone"
                  dataKey={ind.key}
                  stroke={ind.color}
                  strokeWidth={1.2}
                  dot={false}
                  name={ind.label}
                />
              )}
              <Tooltip
                contentStyle={{
                  background: "rgba(17,24,39,0.95)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  fontSize: 11,
                  color: "#f1f5f9",
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="px-3 pb-1 text-[0.55rem]" style={{ color: "var(--text-muted)", marginTop: -4 }}>
            {ind.label}
          </div>
        </div>
      ))}

      {/* Indicator legend */}
      {activeInds.length > 0 && (
        <div
          className="flex gap-3 flex-wrap px-4 py-2"
          style={{ borderTop: "1px solid var(--border-glass)" }}
        >
          {INDICATORS.filter((i) => activeInds.includes(i.key)).map((ind) => (
            <div key={ind.key} className="flex items-center gap-1.5 text-[0.6rem]">
              <span className="w-2 h-2 rounded-sm" style={{ background: ind.color }} />
              <span style={{ color: "var(--text-muted)" }}>{ind.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
