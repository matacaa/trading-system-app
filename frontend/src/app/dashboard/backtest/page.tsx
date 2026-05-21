"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart3, Play, Plus, RefreshCw, Trash2, TrendingUp, X } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS, PLAN_HIST_LABEL } from "@/lib/types";
import type { Backtest, BacktestUsage, Guardrail, CustomModel } from "@/lib/types";
import EquityCurve from "@/components/equity-curve";

const SYS_MODELS = [
  { id: "transformer", label: "Transformer", cat: "deep_learning" },
  { id: "gru", label: "GRU", cat: "deep_learning" },
  { id: "lstm", label: "LSTM", cat: "deep_learning" },
  { id: "lgbm", label: "LightGBM", cat: "gradient_boosting" },
  { id: "rf", label: "Random Forest", cat: "ensemble" },
  { id: "xgb", label: "XGBoost", cat: "gradient_boosting" },
];

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
  const [fDateFrom, setFDateFrom] = useState("2026-01-01");
  const [fDateTo, setFDateTo] = useState("2026-05-01");
  const [mlOn, setMlOn] = useState(true);
  const [modelWeights, setModelWeights] = useState<Record<string, number>>({ lgbm: 35, rf: 35, xgb: 30 });
  const [guardrailsConfig, setGuardrailsConfig] = useState<Record<string, Record<string, unknown>>>({});
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [customModels, setCustomModels] = useState<CustomModel[]>([]);
  const [launching, setLaunching] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [btRes, usageRes, gdRes, cmRes] = await Promise.all([
        api.get("/api/backtest/list"),
        api.get("/api/backtest/usage"),
        api.get("/api/guardrails/registry").catch(() => ({ data: { guardrails: [] } })),
        api.get("/api/models/custom").catch(() => ({ data: { models: [] } })),
      ]);
      setBacktests(btRes.data.backtests || []);
      setUsage(usageRes.data);
      setGuardrails(gdRes.data.guardrails || []);
      setCustomModels(cmRes.data.models || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const selected = backtests.find((b) => b.id === selectedId);

  const selectBacktest = (bt: Backtest) => {
    setSelectedId(bt.id);
    setShowNew(false);
    setFName(bt.name);
    setFTicker(bt.ticker);
    setFDir(bt.direction as "long" | "short");
    setFDateFrom(bt.date_from);
    setFDateTo(bt.date_to);
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
  const sysAvail = SYS_MODELS.slice(0, maxModels);
  const customAvail = customModels.map((m) => ({
    id: `c_${m.experiment_name}`,
    label: m.experiment_name,
    cat: `custom · ${m.ticker}`,
    custom: true,
  }));

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
    setLaunching(true);
    try {
      const config: Record<string, boolean | Record<string, unknown>> = {};
      for (const [k, v] of Object.entries(guardrailsConfig)) {
        config[k] = v.on !== undefined ? true : v;
      }
      await api.post("/api/backtest", {
        name: fName || undefined,
        ticker: fTicker,
        direction: fDir,
        date_from: fDateFrom,
        date_to: fDateTo,
        models_config: mlOn ? modelWeights : {},
        models_enabled: mlOn,
        guardrails_config: config,
      });
      fetchData();
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
    if (!confirm("¿Eliminar este backtest?")) return;
    try {
      await api.delete(`/api/backtest/${id}`);
      setBacktests((prev) => prev.filter((b) => b.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch { /* ignore */ }
  };

  // Group backtests by ticker
  const grouped: Record<string, Backtest[]> = {};
  backtests.forEach((bt) => {
    if (!grouped[bt.ticker]) grouped[bt.ticker] = [];
    grouped[bt.ticker].push(bt);
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
              onClick={() => { setShowNew(!showNew); setSelectedId(null); setFName(""); setFTicker("AAPL"); setErrors([]); }}
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
            <input type="text" value={fTicker} onChange={(e) => setFTicker(e.target.value.toUpperCase())} placeholder="Ticker" className="input-glass text-xs py-1.5" />
            <input type="text" value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Nombre" className="input-glass text-xs py-1.5" />
            <button
              onClick={() => { setShowNew(false); setSelectedId(null); }}
              className="w-full text-xs py-1.5 rounded-md"
              style={{ background: "var(--accent-cyan)", color: "white", border: "none", cursor: "pointer" }}
            >
              Crear
            </button>
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
                    background: selectedId === bt.id ? "rgba(255,255,255,0.06)" : "transparent",
                    borderLeft: selectedId === bt.id ? "2px solid var(--accent-cyan)" : "2px solid transparent",
                    border: "none",
                    cursor: "pointer",
                    color: selectedId === bt.id ? "var(--text-primary)" : "var(--text-muted)",
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
                    <div className="text-xs truncate" style={{ fontWeight: selectedId === bt.id ? 600 : 400 }}>
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
                <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{fName || "Nuevo backtest"}</span>
                <span className="text-xs px-2 py-0.5 rounded font-mono" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fTicker}</span>
                <span className="text-xs px-2 py-0.5 rounded" style={{
                  background: fDir === "long" ? "var(--accent-emerald-dim)" : "var(--accent-red-dim)",
                  color: fDir === "long" ? "var(--accent-emerald)" : "var(--accent-red)",
                }}>
                  {fDir}
                </span>
              </div>
              {selectedId && (
                <button onClick={() => handleDelete(selectedId)} className="p-1.5 rounded-lg" style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
                  <Trash2 size={14} />
                </button>
              )}
            </div>

            {errors.length > 0 && (
              <div className="px-4 py-3 rounded-lg space-y-1" style={{ background: "var(--accent-red-dim)", border: "1px solid rgba(239,68,68,0.2)" }}>
                {errors.map((e, i) => <p key={i} className="text-xs" style={{ color: "var(--accent-red)" }}>{e}</p>)}
              </div>
            )}

            {/* Metrics (if completed) */}
            {selected && selected.status === "completed" && (
              <>
                <div className="grid grid-cols-5 gap-3">
                  {[
                    { label: "Win Rate", value: selected.win_rate != null ? `${(selected.win_rate * 100).toFixed(1)}%` : "—", color: selected.win_rate != null && selected.win_rate > 0.55 ? "var(--accent-emerald)" : undefined },
                    { label: "Trades", value: selected.total_trades ?? "—" },
                    { label: "PnL", value: selected.pnl_pct != null ? `${selected.pnl_pct >= 0 ? "+" : ""}${selected.pnl_pct.toFixed(1)}%` : "—", color: selected.pnl_pct != null && selected.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)" },
                    { label: "Sharpe", value: selected.sharpe_ratio?.toFixed(2) ?? "—" },
                    { label: "Days", value: `${days}d`, sub: `máx ${PLAN_HIST_LABEL[plan]}` },
                  ].map((m) => (
                    <div key={m.label} className="glass-card p-3 text-center">
                      <div className="text-lg font-bold font-mono" style={{ color: m.color || "var(--text-primary)" }}>
                        {m.value}
                      </div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                    </div>
                  ))}
                </div>
                {selected.id && (
                  <div className="glass-card p-4">
                    <p className="text-[0.65rem] uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>Equity Curve</p>
                    <EquityCurve backtestId={selected.id} />
                  </div>
                )}
              </>
            )}

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
                  <input type="date" value={fDateFrom} onChange={(e) => setFDateFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Hasta</label>
                  <input type="date" value={fDateTo} onChange={(e) => setFDateTo(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
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
                        return (
                          <div key={g.name} className="flex items-center gap-2 py-1.5" style={{ borderBottom: "1px solid var(--border-glass)", opacity: isAvail ? 1 : 0.35 }}>
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
