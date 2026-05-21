"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Brain,
  CheckCircle,
  Clock,
  Loader2,
  Plus,
  Play,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS, PLAN_TRAIN_LABEL } from "@/lib/types";
import type { TrainingJob, TrainingUsage, ModelType } from "@/lib/types";

export default function TrainingPage() {
  const { user } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;

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
  const [fTrainFrom, setFTrainFrom] = useState("2025-10-01");
  const [fTrainTo, setFTrainTo] = useState("2026-03-01");
  const [fTestFrom, setFTestFrom] = useState("2026-03-01");
  const [fTestTo, setFTestTo] = useState("2026-05-01");
  const [training, setTraining] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

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
      const types = mtRes.data.model_types || [];
      setModelTypes(types);
      if (types.length > 0 && !fModelType) setFModelType(types[0].name);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [fModelType]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Update hyperparams when model type changes
  useEffect(() => {
    if (!fModelType) return;
    const mt = modelTypes.find((m) => m.name === fModelType);
    if (!mt?.params_schema) return;
    const defaults: Record<string, number> = {};
    for (const [k, v] of Object.entries(mt.params_schema)) {
      defaults[k] = typeof v === "object" && v !== null && "default" in v ? (v as { default: number }).default : 0;
    }
    setFHyperparams(defaults);
  }, [fModelType, modelTypes]);

  const selected = jobs.find((j) => j.id === selectedId);
  const selectedMt = selected ? modelTypes.find((m) => m.name === selected.model_type) : null;

  const selectJob = (job: TrainingJob) => {
    setSelectedId(job.id);
    setShowNew(false);
    setFName(job.model_name);
    setFTicker(job.ticker);
    setFModelType(job.model_type);
    setFTrainFrom(job.train_from || "2025-10-01");
    setFTrainTo(job.train_to || "2026-03-01");
    setFTestFrom(job.test_from || "2026-03-01");
    setFTestTo(job.test_to || "2026-05-01");
    if (job.hyperparameters && typeof job.hyperparameters === "object") {
      const hp: Record<string, number> = {};
      for (const [k, v] of Object.entries(job.hyperparameters)) hp[k] = Number(v);
      setFHyperparams(hp);
    }
  };

  const trainDays = fTrainFrom && fTrainTo ? Math.round((new Date(fTrainTo).getTime() - new Date(fTrainFrom).getTime()) / 86400000) : 0;
  const testDays = fTestFrom && fTestTo ? Math.round((new Date(fTestTo).getTime() - new Date(fTestFrom).getTime()) / 86400000) : 0;
  const totalDays = trainDays + testDays;
  const maxDays = limits.max_training_days;
  const daysOk = trainDays > 0 && testDays > 0 && (maxDays === 0 || totalDays <= maxDays);

  const mt = modelTypes.find((m) => m.name === fModelType);

  const handleTrain = async () => {
    setErrors([]);
    setTraining(true);
    try {
      await api.post("/api/train", {
        name: fName || `${fModelType}_${fTicker}_${Date.now()}`,
        ticker: fTicker,
        model_type: fModelType,
        hyperparameters: fHyperparams,
        train_from: fTrainFrom,
        train_to: fTrainTo,
        test_from: fTestFrom,
        test_to: fTestTo,
      });
      fetchData();
    } catch (err: unknown) {
      const resp = (err as { response?: { data?: { detail?: { errors?: string[] } | string } } }).response?.data?.detail;
      if (typeof resp === "object" && resp?.errors) setErrors(resp.errors);
      else if (typeof resp === "string") setErrors([resp]);
      else setErrors(["Error al lanzar training"]);
    } finally {
      setTraining(false);
    }
  };

  // Group jobs by ticker
  const grouped: Record<string, TrainingJob[]> = {};
  jobs.forEach((j) => {
    if (!grouped[j.ticker]) grouped[j.ticker] = [];
    grouped[j.ticker].push(j);
  });

  const STATUS_COLOR: Record<string, string> = {
    pending: "var(--accent-amber)",
    running: "var(--accent-cyan)",
    completed: "var(--accent-emerald)",
    failed: "var(--accent-red)",
  };

  const metrics = selected?.metrics as Record<string, number> | null;

  return (
    <div className="h-[calc(100vh-3rem)] flex">
      {/* Sidebar */}
      <div className="w-[220px] min-w-[220px] flex flex-col overflow-hidden"
        style={{ background: "rgba(0,0,0,0.4)", backdropFilter: "blur(20px)", borderRight: "1px solid var(--border-glass)" }}>
        <div className="px-3 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border-glass)" }}>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Modelos</span>
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-mono" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>
              {jobs.length}/{limits.max_custom_models}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {usage && (
              <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-semibold" style={{
                background: usage.remaining_month > 0 ? "var(--accent-violet-dim)" : "var(--accent-red-dim)",
                color: usage.remaining_month > 0 ? "var(--accent-violet)" : "var(--accent-red)",
              }}>
                {usage.remaining_month} train.
              </span>
            )}
            <button
              onClick={() => { setShowNew(!showNew); setSelectedId(null); setFName(""); setErrors([]); }}
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ border: "1px solid var(--border-glass-hover)", background: showNew ? "var(--accent-violet-dim)" : "transparent", color: "var(--accent-violet)", cursor: "pointer" }}
            >
              {showNew ? <X size={12} /> : <Plus size={12} />}
            </button>
          </div>
        </div>

        {showNew && (
          <div className="p-2 space-y-2" style={{ borderBottom: "1px solid var(--border-glass)" }}>
            <p className="text-[0.65rem] font-bold" style={{ color: "var(--text-primary)" }}>Nuevo modelo</p>
            <input type="text" value={fTicker} onChange={(e) => setFTicker(e.target.value.toUpperCase())} placeholder="Ticker" className="input-glass text-xs py-1.5" />
            <input type="text" value={fName} onChange={(e) => setFName(e.target.value)} placeholder="nombre_modelo_v1" className="input-glass text-xs py-1.5" />
            <select value={fModelType} onChange={(e) => setFModelType(e.target.value)} className="input-glass text-xs py-1.5">
              <option value="">Seleccionar tipo...</option>
              {modelTypes.map((m) => <option key={m.name} value={m.name}>{m.label || m.name} ({m.category})</option>)}
            </select>
            <button
              onClick={() => { if (fModelType) setShowNew(false); }}
              className="w-full text-xs py-1.5 rounded-md"
              style={{ background: fModelType ? "var(--accent-violet)" : "var(--text-muted)", color: "white", border: "none", cursor: fModelType ? "pointer" : "default" }}
            >
              Crear
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {Object.entries(grouped).map(([ticker, tjobs]) => (
            <div key={ticker}>
              <div className="px-3 py-1.5 text-[0.6rem] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>{ticker}</div>
              {tjobs.map((j) => (
                <button key={j.id} onClick={() => selectJob(j)}
                  className="w-full text-left flex items-center gap-2 px-3 py-2"
                  style={{
                    background: selectedId === j.id ? "rgba(255,255,255,0.06)" : "transparent",
                    borderLeft: selectedId === j.id ? "2px solid var(--accent-violet)" : "2px solid transparent",
                    border: "none", cursor: "pointer",
                    color: selectedId === j.id ? "var(--text-primary)" : "var(--text-muted)",
                  }}>
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: STATUS_COLOR[j.status] || "var(--text-muted)" }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs truncate" style={{ fontWeight: selectedId === j.id ? 600 : 400 }}>{j.model_name}</div>
                    <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>
                      {j.model_type} · {j.status}
                      {metrics && j.id === selectedId && metrics.accuracy ? ` · ${(Number(metrics.accuracy) * 100).toFixed(0)}%` : ""}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ))}
          {jobs.length === 0 && !loading && (
            <div className="flex flex-col items-center py-8 gap-2">
              <Brain size={24} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>Sin modelos aún</p>
            </div>
          )}
        </div>
      </div>

      {/* Main */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-violet)] border-t-transparent rounded-full" />
          </div>
        ) : !selectedId && !showNew ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Brain size={40} style={{ color: "var(--text-muted)", opacity: 0.2 }} />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>Selecciona un modelo o crea uno nuevo</p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{fName || "Nuevo modelo"}</span>
              <span className="text-xs px-2 py-0.5 rounded font-mono" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>{fTicker}</span>
              <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>{fModelType}</span>
            </div>

            {errors.length > 0 && (
              <div className="px-4 py-3 rounded-lg space-y-1" style={{ background: "var(--accent-red-dim)", border: "1px solid rgba(239,68,68,0.2)" }}>
                {errors.map((e, i) => <p key={i} className="text-xs" style={{ color: "var(--accent-red)" }}>{e}</p>)}
              </div>
            )}

            {/* Metrics */}
            {metrics ? (
              <>
                <div className="grid grid-cols-5 gap-3">
                  {[
                    { label: "Accuracy", value: metrics.accuracy != null ? `${(Number(metrics.accuracy) * 100).toFixed(1)}%` : "—" },
                    { label: "F1", value: metrics.f1 != null ? `${(Number(metrics.f1) * 100).toFixed(1)}%` : "—" },
                    { label: "Sharpe", value: metrics.sharpe_ratio?.toFixed(2) ?? metrics.sharpe?.toFixed(2) ?? "—", color: Number(metrics.sharpe_ratio || metrics.sharpe || 0) > 1 ? "var(--accent-emerald)" : Number(metrics.sharpe_ratio || metrics.sharpe || 0) > 0 ? "var(--accent-amber)" : "var(--accent-red)" },
                    { label: "Señales", value: metrics.total_signals ?? metrics.signals ?? "—" },
                    { label: "Long/Short", value: `${metrics.buys ?? "—"}/${metrics.sells ?? "—"}` },
                  ].map((m) => (
                    <div key={m.label} className="glass-card p-3 text-center">
                      <div className="text-lg font-bold font-mono" style={{ color: m.color || "var(--text-primary)" }}>{m.value}</div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: "Prec Long", value: metrics.precision_long != null ? `${(Number(metrics.precision_long) * 100).toFixed(1)}%` : "—", color: "var(--accent-emerald)" },
                    { label: "Rec Long", value: metrics.recall_long != null ? `${(Number(metrics.recall_long) * 100).toFixed(1)}%` : "—", color: "var(--accent-emerald)" },
                    { label: "Prec Short", value: metrics.precision_short != null ? `${(Number(metrics.precision_short) * 100).toFixed(1)}%` : "—", color: "var(--accent-red)" },
                    { label: "Rec Short", value: metrics.recall_short != null ? `${(Number(metrics.recall_short) * 100).toFixed(1)}%` : "—", color: "var(--accent-red)" },
                  ].map((m) => (
                    <div key={m.label} className="glass-card p-3 text-center">
                      <div className="text-base font-bold font-mono" style={{ color: m.color }}>{m.value}</div>
                      <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{m.label}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="grid grid-cols-5 gap-3">
                {["Accuracy", "F1", "Sharpe", "Señales", "Long/Short"].map((l) => (
                  <div key={l} className="glass-card p-3 text-center">
                    <div className="text-lg font-bold font-mono" style={{ color: "var(--text-muted)" }}>—</div>
                    <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{l}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Train bar + Dates */}
            <div className="glass-card p-4">
              <div className="flex gap-3 items-end flex-wrap">
                <button onClick={handleTrain} disabled={!daysOk || training}
                  className="flex items-center gap-2 text-sm h-9 px-4 rounded-lg font-semibold"
                  style={{ background: "linear-gradient(135deg, var(--accent-violet), #7c3aed)", color: "white", border: "none", cursor: daysOk && !training ? "pointer" : "default", opacity: daysOk && !training ? 1 : 0.5 }}>
                  {training ? <div className="spin-slow w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" /> : <Play size={14} />}
                  {selected?.status === "completed" ? "Re-train" : "Entrenar"}
                </button>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Train desde</label>
                  <input type="date" value={fTrainFrom} onChange={(e) => setFTrainFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Train hasta</label>
                  <input type="date" value={fTrainTo} onChange={(e) => { setFTrainTo(e.target.value); setFTestFrom(e.target.value); }} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Test desde</label>
                  <input type="date" value={fTestFrom} onChange={(e) => setFTestFrom(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
                <div>
                  <label className="block text-[0.65rem] mb-1" style={{ color: "var(--text-muted)" }}>Test hasta</label>
                  <input type="date" value={fTestTo} onChange={(e) => setFTestTo(e.target.value)} className="input-glass text-xs py-1.5 h-9 w-36" />
                </div>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs">
                <span style={{ color: daysOk ? "var(--text-muted)" : "var(--accent-red)" }}>
                  Train {trainDays}d + Test {testDays}d = {totalDays}d
                  {maxDays > 0 && totalDays > maxDays && ` (máx ${maxDays}d)`}
                </span>
                <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>
                  Plan {plan}: máx {PLAN_TRAIN_LABEL[plan]}
                </span>
              </div>
            </div>

            {/* Hyperparameters */}
            {mt && mt.params_schema && Object.keys(mt.params_schema).length > 0 && (
              <div className="glass-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>
                    Configuración {mt.label || mt.name}
                  </span>
                  <span className="text-[0.6rem] px-2 py-0.5 rounded" style={{ background: "var(--accent-violet-dim)", color: "var(--accent-violet)" }}>
                    {mt.category}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  {Object.entries(mt.params_schema).map(([key, schema]) => {
                    const s = schema as { label?: string; default?: number };
                    const val = fHyperparams[key] ?? s.default ?? 0;
                    return (
                      <div key={key}>
                        <div className="flex justify-between mb-1">
                          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{s.label || key}</span>
                          <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>{val}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="range"
                            min={0}
                            max={(s.default || 1) * 4}
                            step={(s.default || 1) < 1 ? 0.01 : 1}
                            value={val}
                            onChange={(e) => setFHyperparams((p) => ({ ...p, [key]: parseFloat(e.target.value) }))}
                            className="flex-1"
                            style={{ accentColor: "var(--accent-violet)" }}
                          />
                          <input
                            type="number"
                            value={val}
                            onChange={(e) => setFHyperparams((p) => ({ ...p, [key]: parseFloat(e.target.value) || (s.default ?? 0) }))}
                            className="w-16 text-center text-xs rounded py-1"
                            style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-glass)", color: "var(--text-primary)" }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
