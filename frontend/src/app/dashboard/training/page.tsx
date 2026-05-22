"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Brain,
  Play,
  Plus,
  X,
  Lock,
  AlertTriangle,
  Trash2,
  RefreshCw,
  Search,
} from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS, PLAN_TRAIN_LABEL } from "@/lib/types";
import type { TrainingJob, TrainingUsage, ModelType, ParamDef, TickerInfo } from "@/lib/types";

/* ── Helpers ────────────────────────────────────────────────────────────── */

function mtId(m: ModelType): string { return m.type_id || m.name || ""; }

function mtParams(m: ModelType | undefined | null): ParamDef[] {
  if (!m) return [];
  const ps = m.params_schema;
  if (Array.isArray(ps)) return ps;
  if (ps && typeof ps === "object") {
    return Object.entries(ps).map(([key, v]) => ({
      key, label: (v as { label?: string }).label || key,
      default: (v as { default?: number }).default ?? 0,
      type: (v as { type?: string }).type || "number",
      min: (v as { min?: number }).min, max: (v as { max?: number }).max,
    }));
  }
  return [];
}

function defaultHyperparams(m: ModelType | undefined | null): Record<string, number> {
  const params = mtParams(m);
  const d: Record<string, number> = {};
  params.forEach((p) => { d[p.key] = p.default; });
  return d;
}

function fmtDate(d: Date): string { return d.toISOString().slice(0, 10); }

function clampDateMin(planMaxDays: number): string {
  if (planMaxDays <= 0) return fmtDate(new Date());
  const d = new Date();
  d.setDate(d.getDate() - planMaxDays);
  return fmtDate(d);
}

/* ── Available features for training ────────────────────────────────────── */

const ALL_FEATURES = [
  { key: "ema_9", label: "EMA 9", cat: "Tendencia" },
  { key: "ema_12", label: "EMA 12", cat: "Tendencia" },
  { key: "ema_21", label: "EMA 21", cat: "Tendencia" },
  { key: "rsi_14", label: "RSI (14)", cat: "Momentum" },
  { key: "macd_line", label: "MACD Line", cat: "Momentum" },
  { key: "macd_signal", label: "MACD Signal", cat: "Momentum" },
  { key: "bb_pct", label: "Bollinger %B", cat: "Volatilidad" },
  { key: "bb_width", label: "Bollinger Width", cat: "Volatilidad" },
  { key: "vwap", label: "VWAP", cat: "Volumen" },
  { key: "atr_14", label: "ATR (14)", cat: "Volatilidad" },
  { key: "returns_5", label: "Returns 5m", cat: "Precio" },
  { key: "volume_norm", label: "Volumen norm.", cat: "Volumen" },
];

const DEFAULT_FEATURES = ALL_FEATURES.map((f) => f.key);

/* ── Component ──────────────────────────────────────────────────────────── */

export default function TrainingPage() {
  const { user } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;
  const isTrial = plan === "trial";

  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [usage, setUsage] = useState<TrainingUsage | null>(null);
  const [modelTypes, setModelTypes] = useState<ModelType[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  // Form state
  const [fName, setFName] = useState("");
  const [fTicker, setFTicker] = useState("AAPL");
  const [fModelType, setFModelType] = useState("");
  const [fHyperparams, setFHyperparams] = useState<Record<string, number>>({});
  const [fTrainFrom, setFTrainFrom] = useState("2026-04-10");
  const [fTrainTo, setFTrainTo] = useState("2026-04-20");
  const [fTestFrom, setFTestFrom] = useState("2026-04-20");
  const [fTestTo, setFTestTo] = useState("2026-04-24");
  const [fFeatures, setFFeatures] = useState<string[]>(DEFAULT_FEATURES);
  const [fContextTickers, setFContextTickers] = useState<string[]>([]);
  const [trainingName, setTrainingName] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Ticker search state
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerResults, setTickerResults] = useState<TickerInfo[]>([]);
  const [tickerDropdownOpen, setTickerDropdownOpen] = useState(false);
  const [searchingTickers, setSearchingTickers] = useState(false);

  // Context ticker search
  const [ctxSearch, setCtxSearch] = useState("");
  const [ctxResults, setCtxResults] = useState<TickerInfo[]>([]);
  const [ctxDropdownOpen, setCtxDropdownOpen] = useState(false);


  // Ref to prevent useEffect from resetting hyperparams when selectJob sets model type
  const skipHyperReset = useRef(false);

  /* ── Data fetch ──────────────────────────────────────────────────────── */

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, usageRes, mtRes] = await Promise.all([
        api.get("/api/training/jobs"),
        api.get("/api/training/usage"),
        api.get("/api/model-types").catch(() => ({ data: { model_types: [] } })),
      ]);
      setJobs(jobsRes.data.jobs || []);
      setUsage(usageRes.data);
      const types: ModelType[] = (mtRes.data.model_types || []).map((t: Record<string, unknown>) => ({
        type_id: t.type_id || t.name || "",
        label: t.label || t.type_id || t.name || "",
        category: t.category || "",
        params_schema: t.params_schema || [],
      }));
      setModelTypes(types);
      if (types.length > 0 && !fModelType) setFModelType(mtId(types[0]));
    } catch { /* ignore */ } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  /* ── Auto-update hyperparams when model type changes ────────────────── */

  useEffect(() => {
    if (!fModelType || modelTypes.length === 0) return;
    if (skipHyperReset.current) { skipHyperReset.current = false; return; }
    const mt = modelTypes.find((m) => mtId(m) === fModelType);
    setFHyperparams(defaultHyperparams(mt));
  }, [fModelType, modelTypes]);

  /* ── Ticker search with debounce ────────────────────────────────────── */

  useEffect(() => {
    if (!tickerSearch || tickerSearch.length < 1) { setTickerResults([]); return; }
    const timer = setTimeout(async () => {
      setSearchingTickers(true);
      try {
        const res = await api.get(`/api/tickers/universe?search=${encodeURIComponent(tickerSearch)}&limit=10`);
        setTickerResults(res.data.tickers || []);
      } catch { setTickerResults([]); } finally { setSearchingTickers(false); }
    }, 250);
    return () => clearTimeout(timer);
  }, [tickerSearch]);

  /* ── Context ticker search (only tickers with silver data) ──────────── */

  const [silverTickers, setSilverTickers] = useState<TickerInfo[]>([]);

  useEffect(() => {
    // Fetch all tickers available in silver_features_1m (small list)
    api.get("/api/tickers/silver-available?limit=100")
      .then((res) => setSilverTickers(res.data.tickers || []))
      .catch(() => setSilverTickers([]));
  }, []);

  useEffect(() => {
    // Filter silver tickers by search term, exclude current ticker and already-selected
    const available = silverTickers.filter(
      (t) => t.ticker !== fTicker && !fContextTickers.includes(t.ticker)
    );
    if (!ctxSearch) { setCtxResults(available); return; }
    const q = ctxSearch.toUpperCase();
    setCtxResults(available.filter((t) =>
      t.ticker.includes(q) || (t.name || "").toUpperCase().includes(q)
    ));
  }, [ctxSearch, fTicker, fContextTickers, silverTickers]);

  /* ── Derived state ──────────────────────────────────────────────────── */

  const selected = jobs.find((j) => j.id === selectedId);
  const mt = modelTypes.find((m) => mtId(m) === fModelType);

  const trainDays = fTrainFrom && fTrainTo ? Math.round((new Date(fTrainTo).getTime() - new Date(fTrainFrom).getTime()) / 86400000) : 0;
  const testDays = fTestFrom && fTestTo ? Math.round((new Date(fTestTo).getTime() - new Date(fTestFrom).getTime()) / 86400000) : 0;
  const totalDays = trainDays + testDays;
  const maxDays = limits.max_training_days;
  const daysOk = trainDays > 0 && testDays > 0 && (maxDays === 0 ? false : totalDays <= maxDays);
  const today = fmtDate(new Date());
  const dateMin = clampDateMin(maxDays);
  const modelsRemaining = (usage?.limit_custom_models ?? limits.max_custom_models) - (usage?.custom_models ?? jobs.length);
  const trainingsRemaining = usage?.remaining_month ?? limits.max_trainings_month;
  const isTrainingThis = trainingName !== null && trainingName === fName;

  /* ── Actions ────────────────────────────────────────────────────────── */

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type }); setTimeout(() => setToast(null), 3000);
  };

  const selectJob = (job: TrainingJob) => {
    setSelectedId(job.id);
    setShowNew(false);
    setErrors([]);
    setFName(job.model_name);
    setFTicker(job.ticker);
    // Skip hyperparams reset from useEffect — we restore job's own hyperparams below
    skipHyperReset.current = true;
    setFModelType(job.model_type);
    // Always restore dates from job
    setFTrainFrom(job.train_from || fTrainFrom);
    setFTrainTo(job.train_to || fTrainTo);
    setFTestFrom(job.test_from || fTestFrom);
    setFTestTo(job.test_to || fTestTo);
    // Restore features (columns) — fall back to all if not stored
    if (job.columns && job.columns.length > 0) {
      setFFeatures(job.columns);
    } else {
      setFFeatures(DEFAULT_FEATURES);
    }
    // Restore context tickers
    setFContextTickers(job.context_tickers || []);
    // Restore hyperparameters
    if (job.hyperparameters && typeof job.hyperparameters === "object") {
      const hp: Record<string, number> = {};
      for (const [k, v] of Object.entries(job.hyperparameters)) hp[k] = Number(v);
      setFHyperparams(hp);
    }
  };

  const handleTrain = async () => {
    setErrors([]);
    if (trainingsRemaining <= 0) { showToast("Sin trainings restantes. Compra un pack extra.", "err"); return; }
    setTrainingName(fName || `${fModelType}_${fTicker}`);
    try {
      const res = await api.post("/api/train", {
        name: fName || `${fModelType}_${fTicker}_${Date.now()}`,
        ticker: fTicker,
        model_type: fModelType,
        hyperparameters: fHyperparams,
        train_from: fTrainFrom,
        train_to: fTrainTo,
        test_from: fTestFrom,
        test_to: fTestTo,
        context_tickers: fContextTickers,
        columns: fFeatures,
      }, { timeout: 600_000 });
      showToast(`✓ Training ${res.data.status === "completed" ? "completado" : "lanzado"}`);
      // Update selectedId to the (possibly new) job row, keep form state intact
      if (res.data.job_id) setSelectedId(res.data.job_id);
      setShowNew(false);
      await fetchData();
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: unknown }; status?: number }; message?: string };
      const detail = axErr.response?.data?.detail;
      const status = axErr.response?.status;
      if (typeof detail === "object" && detail !== null && "errors" in detail) setErrors((detail as { errors: string[] }).errors);
      else if (typeof detail === "string") setErrors([detail]);
      else if (status) setErrors([`Error ${status}: ${axErr.message || "Error del servidor"}`]);
      else setErrors([axErr.message || "Error de conexión al backend"]);
    } finally { setTrainingName(null); }
  };

  const handleDelete = async (jobId: string, modelName: string) => {
    try {
      await api.delete(`/api/models/${modelName}`);
      showToast("Modelo eliminado");
      if (selectedId === jobId) { setSelectedId(null); setShowNew(false); }
      fetchData();
    } catch { showToast("Error al eliminar modelo", "err"); }
  };

  const toggleFeature = (key: string) => {
    setFFeatures((prev) => prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key]);
  };

  const removeContextTicker = (t: string) => {
    setFContextTickers((prev) => prev.filter((x) => x !== t));
  };

  /* ── Group jobs by ticker ───────────────────────────────────────────── */

  const grouped = useMemo(() => {
    const g: Record<string, TrainingJob[]> = {};
    jobs.forEach((j) => { if (!g[j.ticker]) g[j.ticker] = []; g[j.ticker].push(j); });
    return g;
  }, [jobs]);

  const STATUS_COLOR: Record<string, string> = { pending: "var(--accent-amber)", running: "var(--accent-cyan)", completed: "var(--accent-emerald)", failed: "var(--accent-red)" };
  const STATUS_LABEL: Record<string, string> = { pending: "Pendiente", running: "Entrenando…", completed: "Completado", failed: "Error" };
  const metrics = selected?.metrics as Record<string, number> | null;
  const params = mtParams(mt);
  const featuresByCategory = useMemo(() => {
    const cats: Record<string, typeof ALL_FEATURES> = {};
    ALL_FEATURES.forEach((f) => { if (!cats[f.cat]) cats[f.cat] = []; cats[f.cat].push(f); });
    return cats;
  }, []);

  /* ── Render ─────────────────────────────────────────────────────────── */

  return (
    <div className="h-[calc(100vh-3rem)] flex">
      {toast && (
        <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 px-5 py-2 rounded-xl text-sm font-medium"
          style={{ background: "var(--bg-glass)", backdropFilter: "blur(16px)", border: `1px solid ${toast.type === "err" ? "rgba(239,68,68,0.3)" : "rgba(16,185,129,0.3)"}`, color: toast.type === "err" ? "var(--accent-red)" : "var(--accent-emerald)" }}>
          {toast.msg}
        </div>
      )}

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <div className="w-[220px] min-w-[220px] flex flex-col overflow-hidden"
        style={{ background: "rgba(0,0,0,0.4)", backdropFilter: "blur(20px)", borderRight: "1px solid var(--border-glass)" }}>
        <div className="px-3 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border-glass)" }}>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Modelos</span>
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-mono" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>{jobs.length}/{limits.max_custom_models}</span>
          </div>
          <div className="flex items-center gap-1.5">
            {usage && <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-semibold" style={{ background: trainingsRemaining > 0 ? "var(--accent-violet-dim)" : "var(--accent-red-dim)", color: trainingsRemaining > 0 ? "var(--accent-violet)" : "var(--accent-red)" }}>{trainingsRemaining} train.</span>}
            <button onClick={() => { if (isTrial) { showToast("Training no disponible en Trial", "err"); return; } if (modelsRemaining <= 0 && !showNew) { showToast("Límite de modelos alcanzado", "err"); return; } setShowNew(!showNew); setSelectedId(null); setFName(""); setErrors([]); }}
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ border: "1px solid var(--border-glass-hover)", background: showNew ? "var(--accent-violet-dim)" : "transparent", color: isTrial || modelsRemaining <= 0 ? "var(--text-muted)" : "var(--accent-violet)", cursor: "pointer" }}>
              {showNew ? <X size={12} /> : <Plus size={12} />}
            </button>
          </div>
        </div>

        {modelsRemaining <= 0 && !isTrial && (
          <div className="px-3 py-2 text-[0.6rem]" style={{ color: "var(--accent-red)", borderBottom: "1px solid var(--border-glass)" }}>Límite alcanzado. Compra un pack extra o elimina uno.</div>
        )}

        {showNew && (
          <div className="p-2 space-y-2" style={{ borderBottom: "1px solid var(--border-glass)" }}>
            <p className="text-[0.65rem] font-bold" style={{ color: "var(--text-primary)" }}>Nuevo modelo</p>
            <div className="relative">
              <div className="flex items-center" style={{ background: "rgba(15,23,42,0.8)", border: "1px solid var(--border-glass)", borderRadius: 8 }}>
                <Search size={12} className="ml-2 flex-shrink-0" style={{ color: "var(--text-muted)" }} />
                <input type="text" value={tickerDropdownOpen ? tickerSearch : fTicker}
                  onChange={(e) => { setTickerSearch(e.target.value.toUpperCase()); setTickerDropdownOpen(true); }}
                  onFocus={() => { setTickerSearch(fTicker); setTickerDropdownOpen(true); }}
                  onBlur={() => { setTimeout(() => setTickerDropdownOpen(false), 200); }}
                  placeholder="Buscar ticker..." className="w-full text-xs py-1.5 px-2 bg-transparent outline-none" style={{ color: "var(--text-primary)", border: "none" }} />
                {fTicker && <span className="text-[0.6rem] px-1.5 py-0.5 rounded mr-1 flex-shrink-0" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fTicker}</span>}
              </div>
              {tickerDropdownOpen && (
                <div className="absolute left-0 right-0 mt-1 rounded-lg overflow-hidden z-20 max-h-40 overflow-y-auto" style={{ background: "rgba(15,23,42,0.95)", border: "1px solid var(--border-glass)", backdropFilter: "blur(12px)" }}>
                  {searchingTickers && <div className="px-3 py-2 text-[0.6rem]" style={{ color: "var(--text-muted)" }}>Buscando...</div>}
                  {!searchingTickers && tickerResults.length === 0 && tickerSearch.length > 0 && <div className="px-3 py-2 text-[0.6rem]" style={{ color: "var(--text-muted)" }}>Sin resultados</div>}
                  {tickerResults.map((t) => (
                    <button key={t.ticker} onClick={() => { setFTicker(t.ticker); setTickerSearch(""); setTickerDropdownOpen(false); }}
                      className="w-full text-left px-3 py-1.5 flex justify-between items-center hover:bg-white/5" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-primary)" }}>
                      <span className="text-xs"><b>{t.ticker}</b> <span style={{ color: "var(--text-muted)" }}>{t.name}</span></span>
                      <span className="text-[0.55rem]" style={{ color: "var(--text-muted)" }}>{t.sector}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input type="text" value={fName} onChange={(e) => setFName(e.target.value)} placeholder="nombre_modelo_v1" className="input-glass text-xs py-1.5" />
            <select value={fModelType} onChange={(e) => setFModelType(e.target.value)} className="input-glass text-xs py-1.5">
              <option value="">Seleccionar tipo...</option>
              {modelTypes.map((m) => <option key={mtId(m)} value={mtId(m)}>{m.label || mtId(m)} ({m.category})</option>)}
            </select>
            {fModelType && mtParams(modelTypes.find((m) => mtId(m) === fModelType)).length > 0 && (
              <div className="rounded-lg p-2" style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)" }}>
                <div className="text-[0.6rem] font-semibold mb-1" style={{ color: "var(--text-muted)" }}>Config {modelTypes.find((m) => mtId(m) === fModelType)?.label}</div>
                {mtParams(modelTypes.find((m) => mtId(m) === fModelType)).map((p) => (
                  <div key={p.key} className="flex justify-between items-center text-[0.6rem] py-0.5"><span style={{ color: "var(--text-muted)" }}>{p.label}</span><span style={{ color: "var(--text-primary)" }}>{p.default}</span></div>
                ))}
              </div>
            )}
            <button onClick={() => { if (fModelType && fName && fTicker) setShowNew(false); }}
              className="w-full text-xs py-1.5 rounded-md" style={{ background: fModelType && fName ? "var(--accent-violet)" : "var(--text-muted)", color: "white", border: "none", cursor: fModelType && fName ? "pointer" : "default", opacity: fModelType && fName ? 1 : 0.5 }}>
              Crear
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {Object.entries(grouped).map(([ticker, tjobs]) => (
            <div key={ticker}>
              <div className="px-3 py-1.5 text-[0.6rem] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{ticker}</div>
              {tjobs.map((j) => {
                const jMetrics = j.metrics as Record<string, number> | null;
                const jAcc = jMetrics?.accuracy;
                return (
                  <button key={j.id} onClick={() => selectJob(j)} className="w-full text-left flex items-center gap-2 px-3 py-2"
                    style={{ background: selectedId === j.id ? "rgba(255,255,255,0.06)" : "transparent", borderTop: "none", borderRight: "none", borderBottom: "none", borderLeft: selectedId === j.id ? "2px solid var(--accent-violet)" : "2px solid transparent", cursor: "pointer", color: selectedId === j.id ? "var(--text-primary)" : "var(--text-secondary)" }}>
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: STATUS_COLOR[j.status] || "var(--text-muted)" }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs truncate" style={{ fontWeight: selectedId === j.id ? 600 : 400 }}>{j.model_name}</div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{j.model_type}{j.status === "completed" && jAcc != null ? ` · ${(Number(jAcc) * 100).toFixed(0)}%` : ` · ${STATUS_LABEL[j.status] || j.status}`}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          ))}
          {jobs.length === 0 && !loading && (
            <div className="flex flex-col items-center py-8 gap-2"><Brain size={24} style={{ color: "var(--text-muted)", opacity: 0.3 }} /><p className="text-xs" style={{ color: "var(--text-muted)" }}>Sin modelos aún</p></div>
          )}
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-20"><div className="spin-slow w-6 h-6 border-2 border-[var(--accent-violet)] border-t-transparent rounded-full" /></div>
        ) : isTrial ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Lock size={40} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Training no disponible en Trial</p>
            <p className="text-xs text-center max-w-sm" style={{ color: "var(--text-muted)" }}>Entrena modelos custom para mejorar predicciones. Disponible desde Starter.</p>
            <a href="/dashboard/billing" className="text-xs px-4 py-2 rounded-lg font-semibold" style={{ background: "var(--accent-violet)", color: "white", textDecoration: "none" }}>Ver planes</a>
          </div>
        ) : !selectedId && !showNew ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3"><Brain size={40} style={{ color: "var(--text-muted)", opacity: 0.2 }} /><p className="text-sm" style={{ color: "var(--text-muted)" }}>Selecciona un modelo o crea uno nuevo</p></div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{fName || "Nuevo modelo"}</span>
                <span className="text-xs px-2 py-0.5 rounded font-mono" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fTicker}</span>
                <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>{mt?.label || fModelType}</span>
                {selected?.status && <span className="text-xs px-2 py-0.5 rounded font-semibold" style={{ background: `${STATUS_COLOR[selected.status]}22`, color: STATUS_COLOR[selected.status] }}>{STATUS_LABEL[selected.status] || selected.status}</span>}
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs" style={{ background: "var(--bg-glass)", border: "1px solid var(--border-glass)" }}>
                  <span style={{ color: "var(--text-muted)" }}>Trainings:</span>
                  <span style={{ fontWeight: 700, color: trainingsRemaining <= 0 ? "var(--accent-red)" : trainingsRemaining <= 3 ? "var(--accent-amber)" : "var(--accent-emerald)" }}>{trainingsRemaining}</span>
                  <span style={{ color: "var(--text-muted)" }}>/{usage?.limit_month ?? limits.max_trainings_month}</span>
                </div>
                {selected && <button onClick={() => handleDelete(selected.id, selected.model_name)} className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs" style={{ border: "1px solid rgba(239,68,68,0.2)", background: "transparent", color: "var(--accent-red)", cursor: "pointer" }}><Trash2 size={12} /> Eliminar</button>}
              </div>
            </div>

            {/* Errors */}
            {errors.length > 0 && (
              <div className="px-4 py-3 rounded-lg space-y-1" style={{ background: "var(--accent-red-dim)", border: "1px solid rgba(239,68,68,0.2)" }}>
                <div className="flex items-center gap-2 mb-1"><AlertTriangle size={14} style={{ color: "var(--accent-red)" }} /><span className="text-xs font-semibold" style={{ color: "var(--accent-red)" }}>Errores</span></div>
                {errors.map((e, i) => <p key={i} className="text-xs" style={{ color: "var(--accent-red)" }}>• {e}</p>)}
              </div>
            )}

            {/* Metrics */}
            {metrics ? (
              <>
                <div className="grid grid-cols-5 gap-3">
                  {[
                    { label: "Accuracy", value: metrics.accuracy != null ? `${(Number(metrics.accuracy) * 100).toFixed(1)}%` : "—" },
                    { label: "F1", value: metrics.f1 != null ? `${(Number(metrics.f1) * 100).toFixed(1)}%` : "—" },
                    { label: "Precision", value: metrics.precision != null ? `${(Number(metrics.precision) * 100).toFixed(1)}%` : "—", color: "var(--accent-emerald)" },
                    { label: "Recall", value: metrics.recall != null ? `${(Number(metrics.recall) * 100).toFixed(1)}%` : "—", color: "var(--accent-cyan)" },
                    { label: "ROC AUC", value: metrics.roc_auc != null ? `${(Number(metrics.roc_auc) * 100).toFixed(1)}%` : "—", color: Number(metrics.roc_auc || 0) > 0.9 ? "var(--accent-emerald)" : "var(--accent-amber)" },
                  ].map((m) => (
                    <div key={m.label} className="glass-card p-3 text-center">
                      <div className="text-lg font-bold font-mono" style={{ color: m.color || "var(--text-primary)" }}>{m.value}</div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                    </div>
                  ))}
                </div>
                {metrics.training_duration_s != null && (
                  <div className="grid grid-cols-1 max-w-[200px]">
                    <div className="glass-card p-3 text-center">
                      <div className="text-base font-bold font-mono">{Number(metrics.training_duration_s).toFixed(0)}s</div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>Duración</div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="grid grid-cols-5 gap-3">
                {["Accuracy", "F1", "Precision", "Recall", "ROC AUC"].map((l) => (
                  <div key={l} className="glass-card p-3 text-center"><div className="text-lg font-bold font-mono" style={{ color: "var(--text-muted)" }}>—</div><div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{l}</div></div>
                ))}
              </div>
            )}

            {/* Train bar + Dates */}
            <div className="glass-card p-4">
              <div className="flex gap-3 items-end flex-wrap">
                <button onClick={handleTrain} disabled={!daysOk || isTrainingThis || trainingsRemaining <= 0}
                  className="flex items-center gap-2 text-sm h-9 px-4 rounded-lg font-semibold"
                  style={{ background: "linear-gradient(135deg, var(--accent-violet), #7c3aed)", color: "white", border: "none", cursor: daysOk && !isTrainingThis && trainingsRemaining > 0 ? "pointer" : "default", opacity: daysOk && !isTrainingThis && trainingsRemaining > 0 ? 1 : 0.5 }}>
                  {isTrainingThis ? <div className="spin-slow w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" /> : selected?.status === "completed" ? <RefreshCw size={14} /> : <Play size={14} />}
                  {selected?.status === "completed" ? "Re-train" : "Entrenar"}
                </button>
                <div><label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Train desde</label><input type="date" value={fTrainFrom} min={dateMin} max={fTrainTo || today} onChange={(e) => setFTrainFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" /></div>
                <div><label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Train hasta</label><input type="date" value={fTrainTo} min={fTrainFrom || dateMin} max={today} onChange={(e) => { setFTrainTo(e.target.value); setFTestFrom(e.target.value); }} className="input-glass text-xs py-1.5 h-9 w-36" /></div>
                <div><label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Test desde</label><input type="date" value={fTestFrom} min={fTrainTo || dateMin} max={fTestTo || today} onChange={(e) => setFTestFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" /></div>
                <div><label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Test hasta</label><input type="date" value={fTestTo} min={fTestFrom || dateMin} max={today} onChange={(e) => setFTestTo(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" /></div>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs flex-wrap">
                <span style={{ color: daysOk ? "var(--text-muted)" : "var(--accent-red)" }}>
                  Train {trainDays}d + Test {testDays}d = {totalDays}d
                  {maxDays > 0 && totalDays > maxDays && ` (máx ${maxDays}d)`}
                </span>
                <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>Plan {plan}: máx {PLAN_TRAIN_LABEL[plan] || "—"}</span>
              </div>
            </div>

            {/* Features / Columns */}
            <div className="glass-card p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Features</span>
                  <span className="text-[0.6rem] px-2 py-0.5 rounded font-semibold" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fFeatures.length}/{ALL_FEATURES.length}</span>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setFFeatures(DEFAULT_FEATURES)} className="text-[0.6rem] px-2 py-0.5 rounded" style={{ border: "1px solid var(--border-glass)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>Todas</button>
                  <button onClick={() => setFFeatures([])} className="text-[0.6rem] px-2 py-0.5 rounded" style={{ border: "1px solid var(--border-glass)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>Ninguna</button>
                </div>
              </div>
              {Object.entries(featuresByCategory).map(([cat, feats]) => (
                <div key={cat} className="mb-2">
                  <div className="text-[0.6rem] font-bold uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>{cat}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {feats.map((f) => {
                      const isOn = fFeatures.includes(f.key);
                      return (
                        <button key={f.key} onClick={() => toggleFeature(f.key)}
                          className="text-[0.65rem] px-2 py-1 rounded-md"
                          style={{ border: `1px solid ${isOn ? "var(--accent-cyan)" : "var(--border-glass)"}`, background: isOn ? "var(--accent-cyan-dim)" : "transparent", color: isOn ? "var(--accent-cyan)" : "var(--text-muted)", cursor: "pointer" }}>
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Context Tickers */}
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Tickers contexto</span>
                <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>correlación</span>
              </div>
              <p className="text-[0.65rem] mb-2" style={{ color: "var(--text-muted)" }}>Otros tickers cuyas features se incluyen como contexto para mejorar predicciones.</p>
              {fContextTickers.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {fContextTickers.map((t) => (
                    <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-md" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)", border: "1px solid rgba(139,92,246,0.2)" }}>
                      {t}
                      <button onClick={() => removeContextTicker(t)} style={{ background: "none", border: "none", color: "var(--accent-violet)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }}>×</button>
                    </span>
                  ))}
                </div>
              )}
              <div className="relative">
                <input type="text" value={ctxSearch}
                  onChange={(e) => { setCtxSearch(e.target.value.toUpperCase()); setCtxDropdownOpen(true); }}
                  onFocus={() => setCtxDropdownOpen(true)}
                  onBlur={() => setTimeout(() => setCtxDropdownOpen(false), 200)}
                  placeholder="Buscar ticker para añadir..." className="input-glass text-xs py-1.5 w-56" />
                {ctxDropdownOpen && ctxResults.length > 0 && (
                  <div className="absolute left-0 mt-1 rounded-lg overflow-hidden z-20 max-h-32 overflow-y-auto w-56" style={{ background: "rgba(15,23,42,0.95)", border: "1px solid var(--border-glass)" }}>
                    {ctxResults.map((t) => (
                      <button key={t.ticker} onClick={() => { setFContextTickers((p) => [...p, t.ticker]); setCtxSearch(""); setCtxDropdownOpen(false); }}
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-white/5" style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-primary)" }}>
                        <b>{t.ticker}</b> <span style={{ color: "var(--text-muted)" }}>{t.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Hyperparameters */}
            {mt && params.length > 0 && (
              <div className="glass-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>Configuración {mt.label || mtId(mt)}</span>
                  <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>{mt.category}</span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {params.map((p) => {
                    const val = fHyperparams[p.key] ?? p.default;
                    const sliderMax = p.max ?? (p.default || 1) * 4;
                    const sliderStep = p.step ?? ((p.default || 1) < 1 ? 0.01 : 1);
                    return (
                      <div key={p.key}>
                        <div className="flex justify-between mb-1"><span className="text-xs" style={{ color: "var(--text-muted)" }}>{p.label || p.key}</span><span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{val}</span></div>
                        <div className="flex items-center gap-2">
                          <input type="range" min={p.min ?? 0} max={sliderMax} step={sliderStep} value={val} onChange={(e) => setFHyperparams((prev) => ({ ...prev, [p.key]: parseFloat(e.target.value) }))} className="flex-1" style={{ accentColor: "var(--accent-violet)" }} />
                          <input type="number" value={val} step={sliderStep} onChange={(e) => setFHyperparams((prev) => ({ ...prev, [p.key]: parseFloat(e.target.value) || p.default }))} className="w-16 text-center text-xs rounded py-1" style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {!mt && fModelType && modelTypes.length > 0 && (
              <div className="glass-card p-4 text-center"><AlertTriangle size={20} className="mx-auto mb-2" style={{ color: "var(--accent-amber)" }} /><p className="text-xs" style={{ color: "var(--text-muted)" }}>Tipo &quot;{fModelType}&quot; no encontrado. Disponibles: {modelTypes.map((m) => mtId(m)).join(", ")}</p></div>
            )}
            {modelTypes.length === 0 && !loading && (
              <div className="glass-card p-4 text-center"><AlertTriangle size={20} className="mx-auto mb-2" style={{ color: "var(--accent-amber)" }} /><p className="text-xs" style={{ color: "var(--text-muted)" }}>No se encontraron tipos de modelo. Verifica <code>model_type_registry</code>.</p></div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
