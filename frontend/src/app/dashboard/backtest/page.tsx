"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart3, Play, Plus, RefreshCw, Search, Trash2, TrendingUp, X } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS, PLAN_HIST_LABEL } from "@/lib/types";
import type { Backtest, BacktestUsage, Guardrail, CustomModel, TickerInfo, ModelType } from "@/lib/types";
import EquityCurve from "@/components/equity-curve";

function mtId(m: ModelType): string { return m.type_id || m.name || ""; }
function fmtDate(d: Date): string { return d.toISOString().slice(0, 10); }

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
  const [fDir, setFDir] = useState<"long" | "short">("long");
  const [fDateFrom, setFDateFrom] = useState("");
  const [fDateTo, setFDateTo] = useState("");
  const [mlOn, setMlOn] = useState(true);
  const [modelWeights, setModelWeights] = useState<Record<string, number>>({});
  const [guardrailsConfig, setGuardrailsConfig] = useState<Record<string, Record<string, unknown>>>({});
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [customModels, setCustomModels] = useState<CustomModel[]>([]);
  const [modelTypes, setModelTypes] = useState<ModelType[]>([]);
  const [launching, setLaunching] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

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
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  /* ── Ticker search (filter from silver tickers) ────────────────────── */

  useEffect(() => {
    if (!tickerSearch || tickerSearch.length < 1) { setTickerResults(silverTickers); return; }
    const q = tickerSearch.toUpperCase();
    setTickerResults(silverTickers.filter((t) =>
      t.ticker.includes(q) || (t.name || "").toUpperCase().includes(q)
    ));
  }, [tickerSearch, silverTickers]);

  /* ── Auto-set dates when ticker changes ─────────────────────────────── */

  useEffect(() => {
    if (!fTicker || silverTickers.length === 0) return;
    const match = silverTickers.find((t) => t.ticker === fTicker);
    if (!match?.data_from || !match?.data_to) return;
    const dataFrom = match.data_from.slice(0, 10);
    const dataTo = match.data_to.slice(0, 10);
    setFDateFrom(dataFrom);
    setFDateTo(dataTo);
  }, [fTicker, silverTickers]);

  const selected = backtests.find((b) => String(b.id) === selectedId);

  const selectBacktest = (bt: Backtest) => {
    setSelectedId(String(bt.id));
    setShowNew(false);
    setFName(bt.name);
    const ticker = bt.ticker || "AAPL";
    setFTicker(ticker);
    setFDir((bt.direction as "long" | "short") || "long");
    // Auto-fill dates from silver data if backtest has NULL dates
    if (bt.date_from && bt.date_to) {
      setFDateFrom(bt.date_from);
      setFDateTo(bt.date_to);
    } else {
      const match = silverTickers.find((t) => t.ticker === ticker);
      setFDateFrom(match?.data_from?.slice(0, 10) || "");
      setFDateTo(match?.data_to?.slice(0, 10) || "");
    }
    setMlOn(bt.models_enabled !== false);
    setModelWeights((bt.models_config as Record<string, number>) || {});
    const gc = (bt.guardrails_config as Record<string, Record<string, unknown>>) || {};
    setGuardrailsConfig(gc);
  };

  const days = fDateFrom && fDateTo
    ? Math.round((new Date(fDateTo).getTime() - new Date(fDateFrom).getTime()) / 86400000)
    : 0;
  const daysOk = days > 0 && days <= limits.max_hist_days;
  const totalWeight = Object.values(modelWeights).reduce((a, b) => a + b, 0);
  const weightsOk = !mlOn || totalWeight === 100 || Object.keys(modelWeights).length === 0;
  const canLaunch = daysOk && weightsOk;

  const maxModels = limits.max_models_backtest;
  const sysAvail = modelTypes.slice(0, maxModels).map((m) => ({
    id: mtId(m),
    label: m.label || mtId(m),
    cat: m.category,
  }));
  const customAvail = customModels
    .filter((m) => m.ticker === fTicker || (m.ticker && m.ticker.includes(fTicker)))
    .map((m) => ({
      id: m.experiment_name,
      label: m.experiment_name,
      cat: `custom · ${m.ticker}`,
      custom: true,
    }));

  const tickerSilver = silverTickers.find((t) => t.ticker === fTicker);
  const tickerDataMin = tickerSilver?.data_from?.slice(0, 10) || "";
  const tickerDataMax = tickerSilver?.data_to?.slice(0, 10) || "";

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

  const handleLaunch = async () => {
    setErrors([]);
    // Validate before launching
    const errs: string[] = [];
    if (!fTicker) errs.push("Selecciona un ticker");
    if (!fDateFrom || !fDateTo) errs.push("Selecciona fechas de inicio y fin");
    if (days <= 0) errs.push("La fecha fin debe ser posterior a la de inicio");
    if (days > limits.max_hist_days) errs.push(`${days}d excede el máximo del plan (${limits.max_hist_days}d)`);
    if (mlOn && Object.keys(modelWeights).length > 0 && Math.abs(totalWeight - 100) > 0.01) errs.push(`Los pesos deben sumar 100% (suman ${totalWeight}%)`);
    if (errs.length > 0) { setErrors(errs); return; }

    setLaunching(true);
    try {
      const config: Record<string, boolean | Record<string, unknown>> = {};
      for (const [k, v] of Object.entries(guardrailsConfig)) {
        config[k] = v.on !== undefined ? true : v;
      }
      const res = await api.post("/api/backtest", {
        name: fName || `bt_${fTicker.toLowerCase()}_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`,
        ticker: fTicker,
        direction: fDir,
        date_from: fDateFrom,
        date_to: fDateTo,
        models_config: mlOn ? modelWeights : {},
        models_enabled: mlOn,
        guardrails_config: config,
      }, { timeout: 600_000 });
      // Auto-select the new backtest
      if (res.data.id) setSelectedId(String(res.data.id));
      setShowNew(false);
      await fetchData();
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { detail?: { errors?: string[] } | string } } }).response?.data?.detail;
      if (typeof resp === "object" && resp?.errors) setErrors(resp.errors);
      else if (typeof resp === "string") setErrors([resp]);
      else setErrors(["Error al lanzar backtest"]);
    } finally {
      setLaunching(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/backtest/${id}`);
      if (selectedId === id) { setSelectedId(null); setShowNew(false); }
      fetchData();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string }; status?: number }; message?: string };
      const detail = axErr.response?.data?.detail || axErr.message || "Error al eliminar backtest";
      setErrors([typeof detail === "string" ? detail : "Error al eliminar backtest"]);
    }
  };

  // Group backtests by ticker (handle NULL ticker)
  const grouped: Record<string, Backtest[]> = {};
  backtests.forEach((bt) => {
    const tk = bt.ticker || "Sin ticker";
    if (!grouped[tk]) grouped[tk] = [];
    grouped[tk].push(bt);
  });

  return (
    <div className="h-[calc(100vh-3rem)] flex">
      {/* Sidebar */}
      <div
        className="w-[220px] min-w-[220px] flex flex-col overflow-hidden"
        style={{
          background: "rgba(0,0,0,0.4)",
          backdropFilter: "blur(20px)",
          borderRight: "1px solid var(--border-glass)",
        }}
      >
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
                  setFName("");
                  setFTicker("AAPL");
                  setFDir("long");
                  setMlOn(true);
                  setModelWeights({});
                  setGuardrailsConfig({});
                  // Dates auto-fill via useEffect when silverTickers available
                  const match = silverTickers.find((t) => t.ticker === "AAPL");
                  setFDateFrom(match?.data_from?.slice(0, 10) || "");
                  setFDateTo(match?.data_to?.slice(0, 10) || "");
                }
              }}
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ border: "1px solid var(--border-glass-hover)", background: showNew ? "var(--accent-cyan-dim)" : "transparent", color: "var(--accent-cyan)", cursor: "pointer" }}
            >
              {showNew ? <X size={12} /> : <Plus size={12} />}
            </button>
          </div>
        </div>

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
              <div className="px-3 py-1.5 text-[0.6rem] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                {ticker}
              </div>
              {bts.map((bt) => (
                <button
                  key={bt.id}
                  onClick={() => selectBacktest(bt)}
                  className="w-full text-left flex items-center gap-2 px-3 py-2"
                  style={{
                    background: selectedId === String(bt.id) ? "rgba(255,255,255,0.06)" : "transparent",
                    borderLeft: selectedId === String(bt.id) ? "2px solid var(--accent-cyan)" : "2px solid transparent",
                    border: "none",
                    cursor: "pointer",
                    color: selectedId === String(bt.id) ? "var(--text-primary)" : "var(--text-muted)",
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{
                      background: bt.status === "completed"
                        ? (bt.pnl_pct != null && bt.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)")
                        : "var(--text-muted)",
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs truncate" style={{ fontWeight: selectedId === String(bt.id) ? 600 : 400 }}>
                      {bt.name}
                    </div>
                    <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>
                      {bt.direction}{bt.pnl_pct != null ? ` · ${bt.pnl_pct >= 0 ? "+" : ""}${bt.pnl_pct.toFixed(1)}%` : ""}
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

      {/* Main */}
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
                <span className="text-xs px-2 py-0.5 rounded" style={{
                  background: (selected?.direction || fDir) === "long" ? "var(--accent-emerald-dim)" : "var(--accent-red-dim)",
                  color: (selected?.direction || fDir) === "long" ? "var(--accent-emerald)" : "var(--accent-red)",
                }}>
                  {selected?.direction || fDir}
                </span>
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

            {/* Metrics */}
            <div className="grid grid-cols-5 gap-3">
              {[
                { label: "Win Rate", value: selected?.win_rate != null ? `${(selected.win_rate * 100).toFixed(1)}%` : "—", color: selected?.win_rate != null && selected.win_rate > 0.55 ? "var(--accent-emerald)" : undefined },
                { label: "Trades", value: selected?.total_trades ?? "—" },
                { label: "PnL", value: selected?.pnl_pct != null ? `${selected.pnl_pct >= 0 ? "+" : ""}${selected.pnl_pct.toFixed(1)}%` : "—", color: selected?.pnl_pct != null && selected.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)" },
                { label: "Sharpe", value: selected?.sharpe_ratio?.toFixed(2) ?? "—" },
                { label: "Days", value: days > 0 ? `${days}d` : "—" },
              ].map((m) => (
                <div key={m.label} className="glass-card p-3 text-center">
                  <div className="text-lg font-bold font-mono" style={{ color: m.color || "var(--text-primary)" }}>{m.value}</div>
                  <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                </div>
              ))}
            </div>

            {/* Equity Curve */}
            <div className="glass-card p-4">
              <p className="text-[0.65rem] uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>Equity Curve</p>
              {selected?.id ? (
                <EquityCurve backtestId={selected.id} />
              ) : (
                <div className="flex items-center justify-center h-48 text-xs" style={{ color: "var(--text-muted)" }}>
                  Lanza un backtest para ver la equity curve
                </div>
              )}
            </div>

            {/* Launch bar */}
            <div className="glass-card p-4">
              <div className="flex gap-3 items-end flex-wrap">
                <button
                  onClick={handleLaunch}
                  disabled={!canLaunch || launching}
                  className="btn-primary flex items-center gap-2 text-sm h-9"
                >
                  {launching ? (
                    <div className="spin-slow w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
                  ) : (
                    <Play size={14} />
                  )}
                  {selected?.status === "completed" ? "Re-launch" : "Launch"}
                </button>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Dirección</label>
                  <select value={fDir} onChange={(e) => setFDir(e.target.value as "long" | "short")} className="input-glass text-xs py-1.5 h-9 w-24">
                    <option value="long">Long</option>
                    <option value="short">Short</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Desde</label>
                  <input type="date" value={fDateFrom} min={tickerDataMin} max={fDateTo || tickerDataMax} onChange={(e) => setFDateFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Hasta</label>
                  <input type="date" value={fDateTo} min={fDateFrom || tickerDataMin} max={tickerDataMax} onChange={(e) => setFDateTo(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
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
              {(!weightsOk || !daysOk) && (
                <div className="mt-2 text-xs" style={{ color: "var(--accent-red)" }}>
                  {!weightsOk && `Pesos deben sumar 100% (suman ${totalWeight}%). `}
                  {!daysOk && days > limits.max_hist_days && `${days}d excede máx ${limits.max_hist_days}d del plan.`}
                </div>
              )}
            </div>

            {/* Models */}
            <div className="glass-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Modelos ML</span>
                  <span className="text-[0.65rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>
                    {Object.keys(modelWeights).length} activos
                  </span>
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
                  <button
                    onClick={() => setMlOn(!mlOn)}
                    className="w-8 h-5 rounded-full relative"
                    style={{ background: mlOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: "pointer" }}
                  >
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
                        <span className="flex-1 text-xs" style={{ color: isOn ? "var(--text-primary)" : "var(--text-muted)" }}>
                          {m.label} <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.cat}</span>
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
                              {m.label}
                              <span className="text-[0.6rem] ml-1 px-1 py-0.5 rounded" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>custom</span>
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

            {/* Guardrails */}
            {guardrails.length > 0 && (
              <div className="glass-card p-4 space-y-3">
                <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Guardrails</span>
                {["básico", "técnico", "riesgo"].map((cat) => {
                  const catGds = guardrails.filter((g) => (g.category || "").toLowerCase() === cat);
                  if (catGds.length === 0) return null;
                  return (
                    <div key={cat}>
                      <div className="text-[0.65rem] font-bold capitalize mb-2" style={{ color: "var(--text-muted)" }}>{cat}</div>
                      {catGds.map((g, gi) => {
                        const isAvail = gi < limits.guardrails_count;
                        const isOn = !!guardrailsConfig[g.name];
                        const gParams = Array.isArray(g.params_schema) ? g.params_schema : [];
                        return (
                          <div key={g.name} className="py-1.5" style={{ borderBottom: "1px solid var(--border-glass)", opacity: isAvail ? 1 : 0.35 }}>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => isAvail && toggleGuardrail(g.name)}
                                className="w-8 h-5 rounded-full relative flex-shrink-0"
                                style={{ background: isOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: isAvail ? "pointer" : "default" }}
                              >
                                <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: isOn ? 16 : 2 }} />
                              </button>
                              <div className="flex-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-xs" style={{ fontWeight: isOn ? 600 : 400, color: "var(--text-primary)" }}>{g.label || g.name}</span>
                                  <span className="text-[0.55rem] px-1 py-0.5 rounded" style={{
                                    background: g.phase === "pre" ? "var(--accent-emerald-dim)" : "var(--accent-amber-dim)",
                                    color: g.phase === "pre" ? "var(--accent-emerald)" : "var(--accent-amber)",
                                  }}>
                                    {g.phase === "pre" ? "Pre" : "Post"}
                                  </span>
                                  {!isAvail && <span className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>🔒</span>}
                                </div>
                              </div>
                            </div>
                            {isOn && gParams.length > 0 && (
                              <div className="ml-10 mt-2 space-y-2">
                                {gParams.map((p: Record<string, unknown>) => {
                                  const key = p.key as string;
                                  const label = (p.label || key) as string;
                                  const min = (p.min ?? 0) as number;
                                  const max = (p.max ?? 100) as number;
                                  const step = (p.step ?? 1) as number;
                                  const def = (p.default ?? min) as number;
                                  const cfg = guardrailsConfig[g.name] || {};
                                  const val = (cfg[key] as number) ?? def;
                                  return (
                                    <div key={key} className="flex items-center gap-2">
                                      <span className="text-[0.65rem] w-28 flex-shrink-0" style={{ color: "var(--text-muted)" }}>{label}</span>
                                      <input type="range" min={min} max={max} step={step} value={val}
                                        onChange={(e) => setGuardrailsConfig((prev) => ({ ...prev, [g.name]: { ...prev[g.name], on: true, [key]: parseFloat(e.target.value) } }))}
                                        className="flex-1" style={{ accentColor: "var(--accent-cyan)" }} />
                                      <input type="number" value={val} min={min} max={max} step={step}
                                        onChange={(e) => setGuardrailsConfig((prev) => ({ ...prev, [g.name]: { ...prev[g.name], on: true, [key]: parseFloat(e.target.value) || def } }))}
                                        className="w-16 text-center text-xs rounded py-0.5" style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }} />
                                    </div>
                                  );
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
