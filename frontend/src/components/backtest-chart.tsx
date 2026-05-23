"use client";

import { useEffect, useState, useMemo } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceDot,
  Legend,
} from "recharts";
import api from "@/lib/api";

/* ── Types ────────────────────────────────────────────────────────── */

interface Candle {
  ts: string;
  close: number;
  open: number;
  high: number;
  low: number;
  ema_9?: number;
  ema_21?: number;
  ema_50?: number;
  vwap?: number;
  rsi_14?: number;
  macd_line?: number;
  macd_signal?: number;
  macd_hist?: number;
  bb_pct?: number;
  atr_14?: number;
  volume_norm?: number;
  sentiment_score?: number;
}

interface Trade {
  ts_entrada: string;
  ts_salida: string | null;
  precio_entrada: number;
  precio_salida: number | null;
  side: string;
  pnl: number;
  pnl_pct: number;
  motivo_salida: string;
  ejecutada: boolean;
}

interface BacktestChartProps {
  backtestId: string;
}

/* ── Indicator definitions ────────────────────────────────────────── */

interface IndicatorDef {
  key: string;
  label: string;
  color: string;
  group: "price" | "oscillator";
  dataKey: string;
}

const INDICATORS: IndicatorDef[] = [
  { key: "ema_9", label: "EMA 9", color: "#fbbf24", group: "price", dataKey: "ema_9" },
  { key: "ema_21", label: "EMA 21", color: "#f97316", group: "price", dataKey: "ema_21" },
  { key: "ema_50", label: "EMA 50", color: "#ef4444", group: "price", dataKey: "ema_50" },
  { key: "vwap", label: "VWAP", color: "#8b5cf6", group: "price", dataKey: "vwap" },
  { key: "rsi_14", label: "RSI (14)", color: "#06b6d4", group: "oscillator", dataKey: "rsi_14" },
  { key: "macd", label: "MACD", color: "#10b981", group: "oscillator", dataKey: "macd_line" },
];

/* ── Component ────────────────────────────────────────────────────── */

export default function BacktestChart({ backtestId }: BacktestChartProps) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(new Set());
  const [showDropdown, setShowDropdown] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/api/backtest/${backtestId}/chart-data`);
        setCandles(data.candles || []);
        setTrades(data.trades || []);
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [backtestId]);

  /* ── Prepare chart data ─────────────────────────────────────── */

  const chartData = useMemo(() => {
    return candles.map((c) => ({
      ts: c.ts,
      close: c.close,
      open: c.open,
      high: c.high,
      low: c.low,
      ema_9: c.ema_9,
      ema_21: c.ema_21,
      ema_50: c.ema_50,
      vwap: c.vwap,
      rsi_14: c.rsi_14,
      macd_line: c.macd_line,
      macd_signal: c.macd_signal,
    }));
  }, [candles]);

  /* ── Find trade entries with nearest candle index ────────────── */

  const tradeMarkers = useMemo(() => {
    if (!chartData.length || !trades.length) return [];
    
    const entryTrades = trades.filter((t) => t.ejecutada && t.motivo_salida !== "abierta");

    return entryTrades.map((t) => {
      // Find closest candle to ts_entrada
      const entryTs = new Date(t.ts_entrada).getTime();
      let closestIdx = 0;
      let closestDiff = Infinity;
      for (let i = 0; i < chartData.length; i++) {
        const diff = Math.abs(new Date(chartData[i].ts).getTime() - entryTs);
        if (diff < closestDiff) {
          closestDiff = diff;
          closestIdx = i;
        }
      }
      return {
        ts: chartData[closestIdx].ts,
        price: t.precio_entrada,
        side: t.side,
        pnl: t.pnl,
        pnl_pct: t.pnl_pct,
        motivo: t.motivo_salida,
      };
    });
  }, [chartData, trades]);

  const longMarkers = tradeMarkers.filter((m) => m.side === "long");
  const shortMarkers = tradeMarkers.filter((m) => m.side === "short");

  /* ── Price domain (Y axis) ──────────────────────────────────── */

  const priceDomain = useMemo(() => {
    if (!chartData.length) return [0, 100];
    const closes = chartData.map((d) => d.close).filter(Boolean);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const pad = (max - min) * 0.05;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartData]);

  /* ── Active oscillators ─────────────────────────────────────── */

  const showRSI = activeIndicators.has("rsi_14");
  const showMACD = activeIndicators.has("macd");

  const toggleIndicator = (key: string) => {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  /* ── Render ─────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spin-slow w-5 h-5 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-xs" style={{ color: "var(--text-muted)" }}>
        Sin datos de precio para este periodo
      </div>
    );
  }

  const priceOverlays = INDICATORS.filter((ind) => ind.group === "price" && activeIndicators.has(ind.key));

  return (
    <div className="space-y-3">
      {/* ── Controls ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[0.65rem] uppercase tracking-wider font-bold" style={{ color: "var(--text-muted)" }}>Precio + Señales</span>
          {longMarkers.length > 0 && (
            <span className="flex items-center gap-1 text-[0.6rem]" style={{ color: "#10b981" }}>
              <span style={{ fontSize: 10 }}>▲</span> LONG ({longMarkers.length})
            </span>
          )}
          {shortMarkers.length > 0 && (
            <span className="flex items-center gap-1 text-[0.6rem]" style={{ color: "#ef4444" }}>
              <span style={{ fontSize: 10 }}>▼</span> SHORT ({shortMarkers.length})
            </span>
          )}
        </div>

        {/* Indicator dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="text-[0.65rem] px-3 py-1.5 rounded-lg flex items-center gap-1.5"
            style={{
              border: "1px solid var(--border-glass)",
              background: activeIndicators.size > 0 ? "var(--accent-violet-dim)" : "transparent",
              color: activeIndicators.size > 0 ? "var(--accent-violet)" : "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            Indicadores {activeIndicators.size > 0 && `(${activeIndicators.size})`}
            <span style={{ fontSize: 8 }}>▼</span>
          </button>
          {showDropdown && (
            <div
              className="absolute right-0 top-full mt-1 rounded-lg overflow-hidden z-30 w-48"
              style={{ background: "rgba(15,23,42,0.97)", border: "1px solid var(--border-glass)", backdropFilter: "blur(16px)" }}
            >
              <div className="p-2 text-[0.55rem] uppercase tracking-wider font-bold" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border-glass)" }}>
                Overlay (precio)
              </div>
              {INDICATORS.filter((i) => i.group === "price").map((ind) => (
                <button
                  key={ind.key}
                  onClick={() => toggleIndicator(ind.key)}
                  className="w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 hover:bg-white/5"
                  style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-primary)" }}
                >
                  <span
                    className="w-3 h-3 rounded-sm flex items-center justify-center text-[8px]"
                    style={{
                      border: `1px solid ${ind.color}`,
                      background: activeIndicators.has(ind.key) ? ind.color : "transparent",
                      color: activeIndicators.has(ind.key) ? "#000" : "transparent",
                    }}
                  >
                    ✓
                  </span>
                  <span className="w-3 h-0.5 rounded" style={{ background: ind.color }} />
                  {ind.label}
                </button>
              ))}
              <div className="p-2 text-[0.55rem] uppercase tracking-wider font-bold" style={{ color: "var(--text-muted)", borderTop: "1px solid var(--border-glass)" }}>
                Panel inferior
              </div>
              {INDICATORS.filter((i) => i.group === "oscillator").map((ind) => (
                <button
                  key={ind.key}
                  onClick={() => toggleIndicator(ind.key)}
                  className="w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 hover:bg-white/5"
                  style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-primary)" }}
                >
                  <span
                    className="w-3 h-3 rounded-sm flex items-center justify-center text-[8px]"
                    style={{
                      border: `1px solid ${ind.color}`,
                      background: activeIndicators.has(ind.key) ? ind.color : "transparent",
                      color: activeIndicators.has(ind.key) ? "#000" : "transparent",
                    }}
                  >
                    ✓
                  </span>
                  <span className="w-3 h-0.5 rounded" style={{ background: ind.color }} />
                  {ind.label}
                </button>
              ))}
              <button
                onClick={() => setShowDropdown(false)}
                className="w-full text-center py-1.5 text-[0.6rem]"
                style={{ background: "transparent", border: "none", borderTop: "1px solid var(--border-glass)", cursor: "pointer", color: "var(--text-muted)" }}
              >
                Cerrar
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Price chart ──────────────────────────────────────── */}
      <div style={{ height: showRSI || showMACD ? 280 : 340 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.08)" vertical={false} />
            <XAxis
              dataKey="ts"
              tick={{ fill: "#64748b", fontSize: 9 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(100,116,139,0.15)" }}
              tickFormatter={(v) => {
                const d = new Date(String(v));
                return `${d.getMonth() + 1}/${d.getDate()}`;
              }}
              interval="preserveStartEnd"
              minTickGap={50}
            />
            <YAxis
              domain={priceDomain}
              tick={{ fill: "#64748b", fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              width={55}
              tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(17,24,39,0.97)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "8px",
                fontSize: "11px",
                color: "#f1f5f9",
              }}
              labelFormatter={(v) => {
                const d = new Date(String(v));
                return d.toLocaleString("es-ES", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
              }}
            />

            {/* Price line */}
            <Line
              type="monotone"
              dataKey="close"
              stroke="#94a3b8"
              strokeWidth={1.5}
              dot={false}
              name="Precio"
            />

            {/* Indicator overlays */}
            {priceOverlays.map((ind) => (
              <Line
                key={ind.key}
                type="monotone"
                dataKey={ind.dataKey}
                stroke={ind.color}
                strokeWidth={1}
                dot={false}
                name={ind.label}
                strokeDasharray={ind.key === "vwap" ? "4 2" : undefined}
              />
            ))}

            {/* LONG entry markers (green triangles) */}
            {longMarkers.map((m, i) => (
              <ReferenceDot
                key={`long-${i}`}
                x={m.ts}
                y={m.price}
                r={5}
                fill="#10b981"
                stroke="#065f46"
                strokeWidth={1.5}
                shape={(props: Record<string, unknown>) => {
                  const { cx, cy } = props as { cx: number; cy: number };
                  return (
                    <polygon
                      points={`${cx},${cy - 6} ${cx - 5},${cy + 3} ${cx + 5},${cy + 3}`}
                      fill="#10b981"
                      stroke="#065f46"
                      strokeWidth={1}
                    />
                  );
                }}
              />
            ))}

            {/* SHORT entry markers (red inverted triangles) */}
            {shortMarkers.map((m, i) => (
              <ReferenceDot
                key={`short-${i}`}
                x={m.ts}
                y={m.price}
                r={5}
                fill="#ef4444"
                stroke="#991b1b"
                strokeWidth={1.5}
                shape={(props: Record<string, unknown>) => {
                  const { cx, cy } = props as { cx: number; cy: number };
                  return (
                    <polygon
                      points={`${cx},${cy + 6} ${cx - 5},${cy - 3} ${cx + 5},${cy - 3}`}
                      fill="#ef4444"
                      stroke="#991b1b"
                      strokeWidth={1}
                    />
                  );
                }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* ── RSI sub-chart ────────────────────────────────────── */}
      {showRSI && (
        <div>
          <span className="text-[0.55rem] uppercase tracking-wider font-bold" style={{ color: "var(--text-muted)" }}>RSI (14)</span>
          <div style={{ height: 100 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.06)" vertical={false} />
                <XAxis dataKey="ts" hide />
                <YAxis
                  domain={[0, 100]}
                  ticks={[30, 50, 70]}
                  tick={{ fill: "#64748b", fontSize: 8 }}
                  tickLine={false}
                  axisLine={false}
                  width={55}
                />
                {/* Overbought/oversold zones */}
                <Area
                  type="monotone"
                  dataKey={() => 100}
                  fill="rgba(239,68,68,0.05)"
                  stroke="none"
                  baseLine={70}
                />
                <Area
                  type="monotone"
                  dataKey={() => 30}
                  fill="rgba(16,185,129,0.05)"
                  stroke="none"
                  baseLine={0}
                />
                <Line type="monotone" dataKey="rsi_14" stroke="#06b6d4" strokeWidth={1.2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── MACD sub-chart ───────────────────────────────────── */}
      {showMACD && (
        <div>
          <span className="text-[0.55rem] uppercase tracking-wider font-bold" style={{ color: "var(--text-muted)" }}>MACD</span>
          <div style={{ height: 100 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.06)" vertical={false} />
                <XAxis dataKey="ts" hide />
                <YAxis
                  tick={{ fill: "#64748b", fontSize: 8 }}
                  tickLine={false}
                  axisLine={false}
                  width={55}
                />
                <Line type="monotone" dataKey="macd_line" stroke="#10b981" strokeWidth={1.2} dot={false} name="MACD" />
                <Line type="monotone" dataKey="macd_signal" stroke="#f97316" strokeWidth={1} dot={false} name="Signal" strokeDasharray="3 2" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
