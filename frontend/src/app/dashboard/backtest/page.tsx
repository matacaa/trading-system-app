"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart3, Play, Plus, Search, Trash2, X } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS, PLAN_HIST_LABEL } from "@/lib/types";
import type { Backtest, BacktestUsage, Guardrail, CustomModel, TickerInfo, ModelType } from "@/lib/types";
import BacktestChart from "@/components/backtest-chart";

function mtId(m: ModelType): string { return m.type_id || m.name || ""; }
function fmtDate(d: Date): string { return d.toISOString().slice(0, 10); }

/* ── Guardrails direccionales ─────────────────────────────────────────── */

const DIRECTIONAL_GUARDRAILS = new Set([
  "rsi", "macd", "bollinger", "ema_tendencia", "vwap_spread", "sentiment",
]);

/* Guardrails ocultos en backtest (trading en vivo) */
const HIDDEN_GUARDRAILS = new Set([
  "horario_mercado", "posicion_abierta", "max_posiciones",
  "ordenes_diarias_max", "circuit_breaker",
]);

/* Params duales para guardrails direccionales (el DB no los tiene) */
const DIRECTIONAL_PARAMS: Record<string, { long: Array<{key: string; label: string; default: number; min: number; max: number; step: number}>; short: Array<{key: string; label: string; default: number; min: number; max: number; step: number}> }> = {
  rsi: {
    long:  [{ key: "long_max", label: "RSI máx", default: 30, min: 0, max: 100, step: 1 }],
    short: [{ key: "short_min", label: "RSI mín", default: 70, min: 0, max: 100, step: 1 }],
  },
  macd: { long: [], short: [] }, // sin params — solo dirección del cruce
  bollinger: {
    long:  [{ key: "long_max", label: "BB% máx", default: 0.2, min: 0, max: 1, step: 0.05 }],
    short: [{ key: "short_min", label: "BB% mín", default: 0.8, min: 0, max: 1, step: 0.05 }],
  },
  ema_tendencia: { long: [], short: [] }, // sin params — precio vs EMA
  vwap_spread: {
    long:  [{ key: "max_spread_pct", label: "Spread máx %", default: 2.0, min: 0, max: 10, step: 0.1 }],
    short: [{ key: "max_spread_pct", label: "Spread máx %", default: 2.0, min: 0, max: 10, step: 0.1 }],
  },
  sentiment: {
    long:  [{ key: "long_min", label: "Sent. mín", default: 0.0, min: -1, max: 1, step: 0.05 }],
    short: [{ key: "short_max", label: "Sent. máx", default: 0.0, min: -1, max: 1, step: 0.05 }],
  },
};

/* Params para score mínimo (POST guardrail) — siempre dual */
const SCORE_PARAMS = {
  long:  { key: "long_min", label: "Confianza LONG", default: 55, min: 0, max: 100, step: 1 },
  short: { key: "short_min", label: "Confianza SHORT", default: 55, min: 0, max: 100, step: 1 },
};

/* ── Component ────────────────────────────────────────────────────────── */

export default function BacktestPage() {
  const { user } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;

  const [backtests, setBacktests] = useState<Backtest[]>([]);
  const [usage, setUsage] = useState<BacktestUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  // Form state
  const [fName, setFName] = useState("");
  const [fTicker, setFTicker] = useState("AAPL");
  const [fDateFrom, setFDateFrom] = useState("");
  const [fDateTo, setFDateTo] = useState("");
  const [mlOn, setMlOn] = useState(true);
  const [modelWeights, setModelWeights] = useState<Record<string, number>>({});
  const [guardrailsConfig, setGuardrailsConfig] = useState<Record<string, Record<string, unknown>>>({});
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [customModels, setCustomModels] = useState<CustomModel[]>([]);
  const [modelTypes, setModelTypes] = useState<ModelType[]>([]);
  const [launching, setLaunching] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [stopLoss, setStopLoss] = useState(2);
  const [takeProfit, setTakeProfit] = useState(4);
  const [positionSize, setPositionSize] = useState(10);

  // Ticker dropdown
  const [silverTickers, setSilverTickers] = useState<TickerInfo[]>([]);
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerResults, setTickerResults] = useState<TickerInfo[]>([]);
  const [tickerDropdownOpen, setTickerDropdownOpen] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [btRes, usageRes, gdRes, cmRes, mtRes, stRes] = await Promise.all([
        api.get("/api/backtest/list").catch(() => ({ data: { backtests: [] } })),
        api.get("/api/backtest/usage").catch(() => ({ data: {} })),
        api.get("/api/guardrails/registry").catch(() => ({ data: { guardrails: [] } })),
        api.get("/api/models/custom").catch(() => ({ data: { models: [] } })),
        api.get("/api/model-types").catch(() => ({ data: { model_types: [] } })),
        api.get("/api/tickers/silver-available?limit=100").catch(() => ({ data: { tickers: [] } })),
      ]);
      setBacktests(btRes.data.backtests || []);
      setUsage(usageRes.data);
      setGuardrails(gdRes.data.guardrails || []);
      setCustomModels(cmRes.data.models || []);
      const types: ModelType[] = (mtRes.data.model_types || []).map((t: Record<string, unknown>) => ({
        type_id: t.type_id || t.name || "",
        label: t.label || t.type_id || t.name || "",
        category: t.category || "",
        params_schema: t.params_schema || [],
      }));
      setModelTypes(types);
      setSilverTickers(stRes.data.tickers || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  /* ── Ticker search ──────────────────────────────────────────────── */

  useEffect(() => {
    if (!tickerSearch || tickerSearch.length < 1) { setTickerResults(silverTickers); return; }
    const q = tickerSearch.toUpperCase();
    setTickerResults(silverTickers.filter((t) =>
      t.ticker.includes(q) || (t.name || "").toUpperCase().includes(q)
    ));
  }, [tickerSearch, silverTickers]);

  /* ── Auto-set dates when ticker changes ─────────────────────────── */

  useEffect(() => {
    if (!fTicker || silverTickers.length === 0) return;
    const match = silverTickers.find((t) => t.ticker === fTicker);
    if (!match?.data_from || !match?.data_to) return;
    setFDateFrom(match.data_from.slice(0, 10));
    setFDateTo(match.data_to.slice(0, 10));
  }, [fTicker, silverTickers]);

  /* ── Derived state ──────────────────────────────────────────────── */

  const selected = backtests.find((b) => String(b.id) === selectedId);
  const tickerSilver = silverTickers.find((t) => t.ticker === fTicker);
  const tickerDataMin = tickerSilver?.data_from?.slice(0, 10) || "";
  const tickerDataMax = tickerSilver?.data_to?.slice(0, 10) || "";

  const days = fDateFrom && fDateTo
    ? Math.round((new Date(fDateTo).getTime() - new Date(fDateFrom).getTime()) / 86400000)
    : 0;
  const daysOk = days > 0 && days <= limits.max_hist_days;
  const totalWeight = Object.values(modelWeights).reduce((a, b) => a + b, 0);
  const weightsOk = !mlOn || totalWeight === 100 || Object.keys(modelWeights).length === 0;
  const canLaunch = daysOk && weightsOk;

  const maxModels = limits.max_models_backtest;
  const sysAvail = modelTypes.slice(0, maxModels).map((m) => ({
    id: mtId(m), label: m.label || mtId(m), cat: m.category,
  }));
  const customAvail = customModels
    .filter((m) => m.ticker === fTicker || (m.ticker && m.ticker.includes(fTicker)))
    .map((m) => ({ id: m.experiment_name, label: m.experiment_name, cat: `custom · ${m.ticker}` }));

  const today = fmtDate(new Date());

  /* ── Actions ────────────────────────────────────────────────────── */

  const selectBacktest = (bt: Backtest) => {
    setSelectedId(String(bt.id));
    setShowNew(false);
    setFName(bt.name);
    setFTicker(bt.ticker || "AAPL");
    if (bt.date_from && bt.date_to) {
      setFDateFrom(bt.date_from);
      setFDateTo(bt.date_to);
    } else {
      const match = silverTickers.find((t) => t.ticker === (bt.ticker || "AAPL"));
      setFDateFrom(match?.data_from?.slice(0, 10) || "");
      setFDateTo(match?.data_to?.slice(0, 10) || "");
    }
    setMlOn(bt.models_enabled !== false);
    setModelWeights((bt.models_config as Record<string, number>) || {});
    setGuardrailsConfig((bt.guardrails_config as Record<string, Record<string, unknown>>) || {});
    // Load position config from stored config or defaults
    const cfg = (bt as Record<string, unknown>).config as Record<string, unknown> | undefined;
    setStopLoss((cfg?.stop_loss_pct as number) || 2);
    setTakeProfit((cfg?.take_profit_pct as number) || 4);
    setPositionSize((cfg?.position_size_pct as number) || 10);
  };

  const handleAutoWeights = () => {
    const keys = Object.keys(modelWeights);
    if (keys.length === 0) return;
    const base = Math.floor(100 / keys.length);
    const rem = 100 - base * keys.length;
    const next: Record<string, number> = {};
    keys.forEach((k, i) => { next[k] = base + (i < rem ? 1 : 0); });
    setModelWeights(next);
  };

  const toggleModel = (id: string) => {
    setModelWeights((prev) => {
      const next = { ...prev };
      if (next[id] !== undefined) delete next[id];
      else next[id] = 0;
      return next;
    });
  };

  const toggleGuardrail = (name: string) => {
    setGuardrailsConfig((prev) => {
      const next = { ...prev };
      if (next[name]) delete next[name];
      else next[name] = { on: true };
      return next;
    });
  };

  const setGdParam = (gdName: string, key: string, value: number) => {
    setGuardrailsConfig((prev) => ({
      ...prev,
      [gdName]: { ...prev[gdName], on: true, [key]: value },
    }));
  };

  const handleLaunch = () => {
    setErrors([]);
    const errs: string[] = [];
    if (!fTicker) errs.push("Selecciona un ticker");
    if (!fDateFrom || !fDateTo) errs.push("Selecciona fechas");
    if (days <= 0) errs.push("La fecha fin debe ser posterior a la de inicio");
    if (days > limits.max_hist_days) errs.push(`${days}d excede el máximo del plan (${limits.max_hist_days}d)`);
    if (mlOn && Object.keys(modelWeights).length > 0 && Math.abs(totalWeight - 100) > 0.01) errs.push(`Los pesos deben sumar 100% (suman ${totalWeight}%)`);
    if (errs.length > 0) { setErrors(errs); return; }

    const btName = fName || `bt_${fTicker.toLowerCase()}_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`;
    setLaunching(btName);

    const config: Record<string, boolean | Record<string, unknown>> = {};
    for (const [k, v] of Object.entries(guardrailsConfig)) {
      config[k] = v.on !== undefined ? v : { on: true, ...v };
    }

    // Fire in background — no await, user can navigate freely
    api.post("/api/backtest", {
      name: btName,
      ticker: fTicker,
      date_from: fDateFrom,
      date_to: fDateTo,
      models_config: mlOn ? modelWeights : {},
      models_enabled: mlOn,
      guardrails_config: config,
      stop_loss_pct: stopLoss,
      take_profit_pct: takeProfit,
      position_size_pct: positionSize,
    }, { timeout: 600_000 }).then((res) => {
      if (res.data.id) setSelectedId(String(res.data.id));
      setShowNew(false);
      fetchData();
    }).catch((err: unknown) => {
      const resp = (err as { response?: { data?: { detail?: { errors?: string[] } | string } } }).response?.data?.detail;
      if (typeof resp === "object" && resp?.errors) setErrors(resp.errors);
      else if (typeof resp === "string") setErrors([resp]);
      else setErrors(["Error al lanzar backtest"]);
    }).finally(() => {
      setLaunching(null);
      fetchData();
    });
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/backtest/${id}`);
      if (selectedId === id) { setSelectedId(null); setShowNew(false); }
      fetchData();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string } }; message?: string };
      setErrors([axErr.response?.data?.detail || axErr.message || "Error al eliminar"]);
    }
  };

  // Group backtests by ticker
  const grouped: Record<string, Backtest[]> = {};
  backtests.forEach((bt) => {
    const tk = bt.ticker || "Sin ticker";
    if (!grouped[tk]) grouped[tk] = [];
    grouped[tk].push(bt);
  });

  /* ── Render helpers for guardrails ─────────────────────────────── */

  const renderSlider = (
    gdName: string, pKey: string, label: string,
    min: number, max: number, step: number, def: number,
  ) => {
    const cfg = guardrailsConfig[gdName] || {};
    const val = (cfg[pKey] as number) ?? def;
    return (
      <div key={pKey} className="flex items-center gap-2">
        <span className="text-[0.6rem] w-24 flex-shrink-0" style={{ color: "var(--text-muted)" }}>{label}</span>
        <input type="range" min={min} max={max} step={step} value={val}
          onChange={(e) => setGdParam(gdName, pKey, parseFloat(e.target.value))}
          className="flex-1" style={{ accentColor: "var(--accent-cyan)" }} />
        <input type="number" value={val} min={min} max={max} step={step}
          onChange={(e) => setGdParam(gdName, pKey, parseFloat(e.target.value) || def)}
          className="w-14 text-center text-xs rounded py-0.5"
          style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }} />
      </div>
    );
  };

  /* ── Render ─────────────────────────────────────────────────────── */

  return (
    <div className="h-[calc(100vh-3rem)] flex">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <div className="w-[220px] min-w-[220px] flex flex-col overflow-hidden"
        style={{ background: "rgba(0,0,0,0.4)", backdropFilter: "blur(20px)", borderRight: "1px solid var(--border-glass)" }}>
        <div className="px-3 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border-glass)" }}>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Backtests</span>
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-mono" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>
              {backtests.length}/{limits.max_backtests_saved}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {usage && (
              <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-semibold" style={{
                background: usage.remaining_month > 0 ? "var(--accent-cyan-dim)" : "var(--accent-red-dim)",
                color: usage.remaining_month > 0 ? "var(--accent-cyan)" : "var(--accent-red)",
              }}>
                {usage.remaining_month} lanz.
              </span>
            )}
            <button
              onClick={() => {
                const newShow = !showNew;
                setShowNew(newShow);
                setSelectedId(null);
                setErrors([]);
                if (newShow) {
                  setFName(""); setFTicker("AAPL"); setMlOn(true);
                  setStopLoss(2); setTakeProfit(4); setPositionSize(10);
                  setModelWeights({}); setGuardrailsConfig({
                    rsi: { on: true, long_max: 35, short_min: 65 },
                    macd: { on: true },
                    ema_tendencia: { on: true },
                    score_minimo: { on: true, long_min: 55, short_min: 55 },
                  });
                  const match = silverTickers.find((t) => t.ticker === "AAPL");
                  setFDateFrom(match?.data_from?.slice(0, 10) || "");
                  setFDateTo(match?.data_to?.slice(0, 10) || "");
                }
              }}
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ border: "1px solid var(--border-glass-hover)", background: showNew ? "var(--accent-cyan-dim)" : "transparent", color: "var(--accent-cyan)", cursor: "pointer" }}>
              {showNew ? <X size={12} /> : <Plus size={12} />}
            </button>
          </div>
        </div>

        {launching && (
          <div className="px-3 py-2 flex items-center gap-2" style={{ background: "var(--accent-cyan-dim)", borderBottom: "1px solid var(--border-glass)" }}>
            <div className="spin-slow w-3 h-3 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full flex-shrink-0" />
            <span className="text-[0.6rem] truncate" style={{ color: "var(--accent-cyan)" }}>{launching}</span>
          </div>
        )}

        {showNew && (
          <div className="p-2 space-y-2" style={{ borderBottom: "1px solid var(--border-glass)" }}>
            <p className="text-[0.65rem] font-bold" style={{ color: "var(--text-primary)" }}>Nuevo backtest</p>
            <div className="relative">
              <div className="flex items-center" style={{ background: "rgba(15,23,42,0.8)", border: "1px solid var(--border-glass)", borderRadius: 8 }}>
                <Search size={12} className="ml-2 flex-shrink-0" style={{ color: "var(--text-muted)" }} />
                <input type="text" value={tickerDropdownOpen ? tickerSearch : fTicker}
                  onChange={(e) => { setTickerSearch(e.target.value.toUpperCase()); setTickerDropdownOpen(true); }}
                  onFocus={() => { setTickerSearch(fTicker); setTickerDropdownOpen(true); }}
                  onBlur={() => setTimeout(() => setTickerDropdownOpen(false), 150)}
                  placeholder="Buscar ticker..." className="w-full text-xs py-1.5 px-2 bg-transparent outline-none" style={{ color: "var(--text-primary)", border: "none" }} />
                {fTicker && <span className="text-[0.6rem] px-1.5 py-0.5 rounded mr-1 flex-shrink-0" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fTicker}</span>}
              </div>
              {tickerDropdownOpen && tickerResults.length > 0 && (
                <div className="absolute left-0 right-0 mt-1 rounded-lg overflow-hidden z-20 max-h-48 overflow-y-auto" style={{ background: "rgba(15,23,42,0.95)", border: "1px solid var(--border-glass)", backdropFilter: "blur(12px)" }}>
                  {tickerResults.map((t) => (
                    <button key={t.ticker} onMouseDown={(e) => { e.preventDefault(); setFTicker(t.ticker); setTickerSearch(""); setTickerDropdownOpen(false); }}
                      className="w-full text-left px-3 py-1.5 flex justify-between items-center hover:bg-white/5" style={{ background: t.ticker === fTicker ? "rgba(255,255,255,0.06)" : "transparent", border: "none", cursor: "pointer", color: "var(--text-primary)" }}>
                      <span className="text-xs"><b>{t.ticker}</b> <span style={{ color: "var(--text-muted)" }}>{t.name}</span></span>
                      <span className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>{t.sector}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input type="text" value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Nombre" className="input-glass text-xs py-1.5" />
            {fName && fTicker && (
              <div className="text-[0.6rem] text-center py-1" style={{ color: "var(--accent-emerald)" }}>
                ✓ Configura y pulsa Launch →
              </div>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {Object.entries(grouped).map(([ticker, bts]) => (
            <div key={ticker}>
              <div className="px-3 py-1.5 text-[0.6rem] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{ticker}</div>
              {bts.map((bt) => (
                <button key={bt.id} onClick={() => selectBacktest(bt)}
                  className="w-full text-left flex items-center gap-2 px-3 py-2"
                  style={{
                    background: selectedId === String(bt.id) ? "rgba(255,255,255,0.06)" : "transparent",
                    borderLeft: selectedId === String(bt.id) ? "2px solid var(--accent-cyan)" : "2px solid transparent",
                    border: "none", cursor: "pointer",
                    color: selectedId === String(bt.id) ? "var(--text-primary)" : "var(--text-muted)",
                  }}>
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{
                    background: launching === bt.name
                      ? "var(--accent-cyan)"
                      : bt.status === "completed"
                        ? (bt.pnl_pct != null && bt.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)")
                        : "var(--text-muted)",
                    animation: launching === bt.name ? "pulse 1s infinite" : "none",
                  }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs truncate" style={{ fontWeight: selectedId === String(bt.id) ? 600 : 400 }}>{bt.name}</div>
                    <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>
                      {launching === bt.name ? "Ejecutando..." : bt.pnl_pct != null ? `${bt.pnl_pct >= 0 ? "+" : ""}${bt.pnl_pct.toFixed(1)}%` : bt.status}
                      {bt.long_trades != null && bt.short_trades != null && ` · L${bt.long_trades} S${bt.short_trades}`}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ))}
          {backtests.length === 0 && !loading && (
            <div className="flex flex-col items-center py-8 gap-2">
              <BarChart3 size={24} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>Sin backtests aún</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Main ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
          </div>
        ) : !selectedId && !showNew ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <BarChart3 size={40} style={{ color: "var(--text-muted)", opacity: 0.2 }} />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>Selecciona un backtest o crea uno nuevo</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{selected?.name || fName || "Nuevo backtest"}</span>
                <span className="text-xs px-2 py-0.5 rounded font-mono" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{selected?.ticker || fTicker}</span>
                <span className="text-[0.6rem] px-2 py-0.5 rounded font-semibold" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>LONG + SHORT</span>
              </div>
              {selectedId && (
                <button onClick={() => handleDelete(selectedId)} className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs" style={{ border: "1px solid rgba(239,68,68,0.2)", background: "transparent", color: "var(--accent-red)", cursor: "pointer" }}>
                  <Trash2 size={12} /> Eliminar
                </button>
              )}
            </div>

            {errors.length > 0 && (
              <div className="px-4 py-3 rounded-lg space-y-1" style={{ background: "var(--accent-red-dim)", border: "1px solid rgba(239,68,68,0.2)" }}>
                {errors.map((e, i) => <p key={i} className="text-xs" style={{ color: "var(--accent-red)" }}>{e}</p>)}
              </div>
            )}

            {/* ── Métricas — Total + por dirección ───────────────── */}
            <div className="grid grid-cols-5 gap-3">
              {[
                { label: "Win Rate", value: selected?.win_rate != null ? `${Number(selected.win_rate).toFixed(1)}%` : "—", color: selected?.win_rate != null && selected.win_rate > 55 ? "var(--accent-emerald)" : undefined },
                { label: "Trades", value: selected?.total_trades ?? "—" },
                { label: "PnL Total", value: selected?.pnl_pct != null ? `${selected.pnl_pct >= 0 ? "+" : ""}${selected.pnl_pct.toFixed(1)}%` : "—", color: selected?.pnl_pct != null && selected.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)" },
                { label: "Sharpe", value: selected?.sharpe_ratio?.toFixed(2) ?? "—" },
                { label: "Drawdown", value: selected?.max_drawdown != null ? `${selected.max_drawdown.toFixed(1)}%` : "—", color: "var(--accent-amber)" },
              ].map((m) => (
                <div key={m.label} className="glass-card p-3 text-center">
                  <div className="text-lg font-bold font-mono" style={{ color: m.color || "var(--text-primary)" }}>{m.value}</div>
                  <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                </div>
              ))}
            </div>

            {/* Métricas por dirección */}
            {selected && (selected.long_trades != null || selected.short_trades != null) && (
              <div className="grid grid-cols-2 gap-3">
                {/* LONG */}
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: "var(--accent-emerald)" }} />
                    <span className="text-xs font-bold" style={{ color: "var(--accent-emerald)" }}>LONG</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div><div className="text-sm font-bold font-mono" style={{ color: "var(--text-primary)" }}>{selected.long_trades ?? 0}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>Trades</div></div>
                    <div><div className="text-sm font-bold font-mono" style={{ color: (selected.long_pnl ?? 0) >= 0 ? "var(--accent-emerald)" : "var(--accent-red)" }}>{selected.long_pnl != null ? `${selected.long_pnl >= 0 ? "+" : ""}${selected.long_pnl.toFixed(0)}` : "—"}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>PnL</div></div>
                    <div><div className="text-sm font-bold font-mono" style={{ color: "var(--text-primary)" }}>{selected.long_win_rate != null ? `${selected.long_win_rate.toFixed(0)}%` : "—"}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>Win Rate</div></div>
                  </div>
                </div>
                {/* SHORT */}
                <div className="glass-card p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: "var(--accent-red)" }} />
                    <span className="text-xs font-bold" style={{ color: "var(--accent-red)" }}>SHORT</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div><div className="text-sm font-bold font-mono" style={{ color: "var(--text-primary)" }}>{selected.short_trades ?? 0}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>Trades</div></div>
                    <div><div className="text-sm font-bold font-mono" style={{ color: (selected.short_pnl ?? 0) >= 0 ? "var(--accent-emerald)" : "var(--accent-red)" }}>{selected.short_pnl != null ? `${selected.short_pnl >= 0 ? "+" : ""}${selected.short_pnl.toFixed(0)}` : "—"}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>PnL</div></div>
                    <div><div className="text-sm font-bold font-mono" style={{ color: "var(--text-primary)" }}>{selected.short_win_rate != null ? `${selected.short_win_rate.toFixed(0)}%` : "—"}</div><div className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>Win Rate</div></div>
                  </div>
                </div>
              </div>
            )}

            {/* ── Price Chart + Signals ─────────────────────────── */}
            <div className="glass-card p-4">
              {selected?.id ? <BacktestChart backtestId={selected.id} /> : (
                <div className="flex items-center justify-center h-48 text-xs" style={{ color: "var(--text-muted)" }}>Lanza un backtest para ver la gráfica</div>
              )}
            </div>

            {/* ── Launch bar + Dates ─────────────────────────────── */}
            <div className="glass-card p-4">
              <div className="flex gap-3 items-end flex-wrap">
                <button onClick={handleLaunch} disabled={!canLaunch || launching !== null}
                  className="btn-primary flex items-center gap-2 text-sm h-9">
                  {launching ? <div className="spin-slow w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" /> : <Play size={14} />}
                  {showNew ? "Lanzar" : "Re-lanzar"}
                </button>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Desde</label>
                  <input type="date" value={fDateFrom} min={tickerDataMin} max={fDateTo || tickerDataMax} onChange={(e) => setFDateFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Hasta</label>
                  <input type="date" value={fDateTo} min={fDateFrom || tickerDataMin} max={tickerDataMax || today} onChange={(e) => setFDateTo(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs flex-wrap">
                <span style={{ color: daysOk ? "var(--text-muted)" : "var(--accent-red)" }}>
                  {days}d {days > limits.max_hist_days && `(máx ${limits.max_hist_days}d)`}
                </span>
                <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>Plan {plan}: máx {PLAN_HIST_LABEL[plan] || "—"}</span>
                {tickerDataMin && tickerDataMax && (
                  <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>
                    Datos {fTicker}: {tickerDataMin} → {tickerDataMax}
                  </span>
                )}
              </div>
              {!weightsOk && <div className="mt-2 text-xs" style={{ color: "var(--accent-red)" }}>Pesos deben sumar 100% (suman {totalWeight}%)</div>}
            </div>

            {/* ── Gestión de posición ─────────────────────────────── */}
            <div className="glass-card p-4 space-y-3">
              <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Gestión de posición</span>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-[0.6rem] mb-1.5" style={{ color: "var(--text-muted)" }}>Stop Loss %</label>
                  <div className="flex items-center gap-2">
                    <input type="range" min={0.5} max={10} step={0.5} value={stopLoss}
                      onChange={(e) => setStopLoss(parseFloat(e.target.value))}
                      className="flex-1" style={{ accentColor: "var(--accent-red)" }} />
                    <input type="number" value={stopLoss} min={0.5} max={10} step={0.5}
                      onChange={(e) => setStopLoss(parseFloat(e.target.value) || 2)}
                      className="w-14 text-center text-xs rounded py-1"
                      style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--accent-red)" }} />
                  </div>
                  <p className="text-[0.55rem] mt-1" style={{ color: "var(--text-muted)" }}>Cierra con pérdida de {stopLoss}%</p>
                </div>
                <div>
                  <label className="block text-[0.6rem] mb-1.5" style={{ color: "var(--text-muted)" }}>Take Profit %</label>
                  <div className="flex items-center gap-2">
                    <input type="range" min={0.5} max={20} step={0.5} value={takeProfit}
                      onChange={(e) => setTakeProfit(parseFloat(e.target.value))}
                      className="flex-1" style={{ accentColor: "var(--accent-emerald)" }} />
                    <input type="number" value={takeProfit} min={0.5} max={20} step={0.5}
                      onChange={(e) => setTakeProfit(parseFloat(e.target.value) || 4)}
                      className="w-14 text-center text-xs rounded py-1"
                      style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--accent-emerald)" }} />
                  </div>
                  <p className="text-[0.55rem] mt-1" style={{ color: "var(--text-muted)" }}>Cierra con ganancia de {takeProfit}%</p>
                </div>
                <div>
                  <label className="block text-[0.6rem] mb-1.5" style={{ color: "var(--text-muted)" }}>Tamaño posición %</label>
                  <div className="flex items-center gap-2">
                    <input type="range" min={1} max={50} step={1} value={positionSize}
                      onChange={(e) => setPositionSize(parseInt(e.target.value))}
                      className="flex-1" style={{ accentColor: "var(--accent-cyan)" }} />
                    <input type="number" value={positionSize} min={1} max={50} step={1}
                      onChange={(e) => setPositionSize(parseInt(e.target.value) || 10)}
                      className="w-14 text-center text-xs rounded py-1"
                      style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--accent-cyan)" }} />
                  </div>
                  <p className="text-[0.55rem] mt-1" style={{ color: "var(--text-muted)" }}>{positionSize}% del capital por trade</p>
                </div>
              </div>
            </div>

            {/* ── Models ─────────────────────────────────────────── */}
            <div className="glass-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Modelos ML</span>
                  <span className="text-[0.65rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>{Object.keys(modelWeights).length} activos</span>
                  {mlOn && weightsOk && Object.keys(modelWeights).length > 0 && (
                    <span className="text-[0.65rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-emerald-dim)", color: "var(--accent-emerald)" }}>{totalWeight}%</span>
                  )}
                  {mlOn && !weightsOk && (
                    <span className="text-[0.65rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-red-dim)", color: "var(--accent-red)" }}>{totalWeight}%≠100</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {mlOn && Object.keys(modelWeights).length > 1 && (
                    <button onClick={handleAutoWeights} className="text-[0.6rem] px-2 py-0.5 rounded" style={{ border: "1px solid var(--border-glass)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>Auto</button>
                  )}
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>ML</span>
                  <button onClick={() => setMlOn(!mlOn)} className="w-8 h-5 rounded-full relative" style={{ background: mlOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: "pointer" }}>
                    <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: mlOn ? 16 : 2 }} />
                  </button>
                </div>
              </div>

              {!mlOn ? (
                <p className="text-xs text-center py-3" style={{ color: "var(--text-muted)" }}>ML desactivado. Solo señales rule-based.</p>
              ) : (
                <>
                  <div className="text-[0.6rem] font-bold uppercase tracking-wider pt-1" style={{ color: "var(--text-muted)" }}>Sistema</div>
                  {sysAvail.map((m) => {
                    const isOn = modelWeights[m.id] !== undefined;
                    const w = modelWeights[m.id] || 0;
                    return (
                      <div key={m.id} className="flex items-center gap-2 py-1.5" style={{ borderBottom: "1px solid var(--border-glass)" }}>
                        <button onClick={() => toggleModel(m.id)} className="w-8 h-5 rounded-full relative flex-shrink-0" style={{ background: isOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: "pointer" }}>
                          <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: isOn ? 16 : 2 }} />
                        </button>
                        <span className="flex-1 text-xs" style={{ color: isOn ? "var(--text-primary)" : "var(--text-muted)" }}>{m.label} <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.cat}</span></span>
                        {isOn && (
                          <>
                            <input type="range" min={0} max={100} value={w} onChange={(e) => setModelWeights((p) => ({ ...p, [m.id]: parseInt(e.target.value) || 0 }))} className="w-16" style={{ accentColor: "var(--accent-cyan)" }} />
                            <input type="number" value={w} onChange={(e) => setModelWeights((p) => ({ ...p, [m.id]: Math.min(100, Math.max(0, parseInt(e.target.value) || 0)) }))}
                              className="w-10 text-center text-xs rounded py-0.5" style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }} />
                            <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>%</span>
                          </>
                        )}
                      </div>
                    );
                  })}
                  {customAvail.length > 0 && (
                    <>
                      <div className="text-[0.6rem] font-bold uppercase tracking-wider pt-2" style={{ color: "var(--text-muted)" }}>Custom (Training)</div>
                      {customAvail.map((m) => {
                        const isOn = modelWeights[m.id] !== undefined;
                        const w = modelWeights[m.id] || 0;
                        return (
                          <div key={m.id} className="flex items-center gap-2 py-1.5" style={{ borderBottom: "1px solid var(--border-glass)" }}>
                            <button onClick={() => toggleModel(m.id)} className="w-8 h-5 rounded-full relative flex-shrink-0" style={{ background: isOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: "pointer" }}>
                              <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: isOn ? 16 : 2 }} />
                            </button>
                            <span className="flex-1 text-xs" style={{ color: isOn ? "var(--text-primary)" : "var(--text-muted)" }}>
                              {m.label}<span className="text-[0.6rem] ml-1 px-1 py-0.5 rounded" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>custom</span>
                            </span>
                            {isOn && (
                              <>
                                <input type="range" min={0} max={100} value={w} onChange={(e) => setModelWeights((p) => ({ ...p, [m.id]: parseInt(e.target.value) || 0 }))} className="w-16" style={{ accentColor: "var(--accent-cyan)" }} />
                                <input type="number" value={w} onChange={(e) => setModelWeights((p) => ({ ...p, [m.id]: Math.min(100, Math.max(0, parseInt(e.target.value) || 0)) }))}
                                  className="w-10 text-center text-xs rounded py-0.5" style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }} />
                                <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>%</span>
                              </>
                            )}
                          </div>
                        );
                      })}
                    </>
                  )}
                  {customAvail.length === 0 && (
                    <p className="text-[0.65rem] py-2" style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border-glass)" }}>Sin modelos custom. Entrena uno en Training.</p>
                  )}
                </>
              )}
            </div>

            {/* ── Confianza mínima (Score POST guardrail) ─────────── */}
            <div className="glass-card p-4 space-y-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Umbral de confianza</span>
                <span className="text-[0.55rem] px-1 py-0.5 rounded" style={{ background: "var(--accent-amber-dim)", color: "var(--accent-amber)" }}>Post</span>
              </div>
              <p className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>Confianza mínima del modelo para generar señal en cada dirección.</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: "var(--accent-emerald)" }} />
                    <span className="text-[0.65rem] font-bold" style={{ color: "var(--accent-emerald)" }}>LONG</span>
                  </div>
                  {renderSlider("score_minimo", SCORE_PARAMS.long.key, SCORE_PARAMS.long.label, SCORE_PARAMS.long.min, SCORE_PARAMS.long.max, SCORE_PARAMS.long.step, SCORE_PARAMS.long.default)}
                </div>
                <div>
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: "var(--accent-red)" }} />
                    <span className="text-[0.65rem] font-bold" style={{ color: "var(--accent-red)" }}>SHORT</span>
                  </div>
                  {renderSlider("score_minimo", SCORE_PARAMS.short.key, SCORE_PARAMS.short.label, SCORE_PARAMS.short.min, SCORE_PARAMS.short.max, SCORE_PARAMS.short.step, SCORE_PARAMS.short.default)}
                </div>
              </div>
            </div>

            {/* ── Guardrails ─────────────────────────────────────── */}
            {guardrails.length > 0 && (
              <div className="glass-card p-4 space-y-3">
                <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Guardrails</span>
                {["básico", "técnico", "riesgo"].map((cat) => {
                  const catGds = guardrails.filter((g) => (g.category || "").toLowerCase() === cat && !HIDDEN_GUARDRAILS.has(g.name));
                  if (catGds.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-[0.65rem] font-bold capitalize mb-2" style={{ color: "var(--text-muted)" }}>{cat}</div>
                      {catGds.map((g, gi) => {
                        const isAvail = gi < limits.guardrails_count;
                        const isOn = !!guardrailsConfig[g.name];
                        const isDirectional = DIRECTIONAL_GUARDRAILS.has(g.name);
                        const dirParams = isDirectional ? DIRECTIONAL_PARAMS[g.name] : null;
                        const gParams = !isDirectional ? (Array.isArray(g.params_schema) ? g.params_schema : []) : [];

                        return (
                          <div key={g.name} className="py-1.5" style={{ borderBottom: "1px solid var(--border-glass)", opacity: isAvail ? 1 : 0.35 }}>
                            <div className="flex items-center gap-2">
                              <button onClick={() => isAvail && toggleGuardrail(g.name)}
                                className="w-8 h-5 rounded-full relative flex-shrink-0"
                                style={{ background: isOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: isAvail ? "pointer" : "default" }}>
                                <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: isOn ? 16 : 2 }} />
                              </button>
                              <div className="flex-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs" style={{ fontWeight: isOn ? 600 : 400, color: "var(--text-primary)" }}>{g.label || g.name}</span>
                                  <span className="text-[0.55rem] px-1 py-0.5 rounded" style={{
                                    background: g.phase === "pre" ? "var(--accent-emerald-dim)" : "var(--accent-amber-dim)",
                                    color: g.phase === "pre" ? "var(--accent-emerald)" : "var(--accent-amber)",
                                  }}>{g.phase === "pre" ? "Pre" : "Post"}</span>
                                  {isDirectional && <span className="text-[0.55rem] px-1 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>L/S</span>}
                                  {!isAvail && <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>🔒</span>}
                                </div>
                              </div>
                            </div>

                            {/* Directional params: two columns */}
                            {isOn && isDirectional && dirParams && (dirParams.long.length > 0 || dirParams.short.length > 0) && (
                              <div className="ml-10 mt-2 grid grid-cols-2 gap-3">
                                <div>
                                  <div className="flex items-center gap-1 mb-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent-emerald)" }} />
                                    <span className="text-[0.55rem] font-bold" style={{ color: "var(--accent-emerald)" }}>LONG</span>
                                  </div>
                                  {dirParams.long.map((p) => renderSlider(g.name, p.key, p.label, p.min, p.max, p.step, p.default))}
                                </div>
                                <div>
                                  <div className="flex items-center gap-1 mb-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent-red)" }} />
                                    <span className="text-[0.55rem] font-bold" style={{ color: "var(--accent-red)" }}>SHORT</span>
                                  </div>
                                  {dirParams.short.map((p) => renderSlider(g.name, p.key, p.label, p.min, p.max, p.step, p.default))}
                                </div>
                              </div>
                            )}

                            {/* Non-directional params: single column */}
                            {isOn && !isDirectional && gParams.length > 0 && (
                              <div className="ml-10 mt-2 space-y-2">
                                {gParams.map((p: Record<string, unknown>) => {
                                  const key = p.key as string;
                                  const label = (p.label || key) as string;
                                  const min = (p.min ?? 0) as number;
                                  const max = (p.max ?? 100) as number;
                                  const step = (p.step ?? 1) as number;
                                  const def = (p.default ?? min) as number;
                                  return renderSlider(g.name, key, label, min, max, step, def);
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
