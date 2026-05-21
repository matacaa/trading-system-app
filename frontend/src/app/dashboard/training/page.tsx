"use client";

import { useState, useEffect, useCallback } from "react";
import { Brain, CheckCircle, Clock, Loader2, Plus, XCircle } from "lucide-react";
import api from "@/lib/api";
import type { TrainingJob, TrainingUsage } from "@/lib/types";
import TrainingForm from "@/components/training-form";

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <Clock size={14} />,
  running: <Loader2 size={14} className="spin-slow" />,
  completed: <CheckCircle size={14} />,
  failed: <XCircle size={14} />,
};

const STATUS_COLOR: Record<string, string> = {
  pending: "var(--accent-amber)",
  running: "var(--accent-cyan)",
  completed: "var(--accent-emerald)",
  failed: "var(--accent-red)",
};

export default function TrainingPage() {
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [usage, setUsage] = useState<TrainingUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [jobsRes, usageRes] = await Promise.all([
        api.get("/api/training/jobs"),
        api.get("/api/training/usage"),
      ]);
      setJobs(jobsRes.data.jobs || []);
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

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain size={22} style={{ color: "var(--accent-violet)" }} />
          <h1
            className="text-lg font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            Training
          </h1>
        </div>
        <div className="flex items-center gap-4">
        {usage && (
          <div className="flex items-center gap-3">
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {usage.used_this_month}/{usage.limit_month} este mes
            </div>
            <div
              className="w-24 h-1.5 rounded-full"
              style={{ background: "rgba(100,116,139,0.15)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(100, (usage.used_this_month / Math.max(usage.limit_month, 1)) * 100)}%`,
                  background: "var(--accent-violet)",
                }}
              />
            </div>
          </div>
        )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="btn-primary flex items-center gap-1.5 text-xs"
            style={{ background: "linear-gradient(135deg, var(--accent-violet), #7c3aed)" }}
          >
            <Plus size={14} />
            Nuevo Training
          </button>
        </div>
      </div>

      {/* Form */}
      {showForm && (
        <TrainingForm
          onSuccess={() => { setShowForm(false); fetchData(); }}
          onClose={() => setShowForm(false)}
        />
      )}

      {/* Jobs list */}
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-violet)] border-t-transparent rounded-full" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Brain
              size={32}
              style={{ color: "var(--text-muted)", opacity: 0.3 }}
            />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Aún no tienes entrenamientos
            </p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Entrena modelos custom para mejorar tus predicciones
            </p>
          </div>
        ) : (
          <div
            className="divide-y"
            style={{ borderColor: "var(--border-glass)" }}
          >
            {jobs.map((job) => (
              <div
                key={job.id}
                className="px-5 py-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{
                      background: `${STATUS_COLOR[job.status]}20`,
                      color: STATUS_COLOR[job.status],
                    }}
                  >
                    {STATUS_ICON[job.status] || <Clock size={14} />}
                  </div>
                  <div>
                    <p
                      className="text-sm font-medium"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {job.name}
                    </p>
                    <p
                      className="text-xs"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {job.ticker} · {job.model_type} ·{" "}
                      {new Date(job.created_at).toLocaleDateString("es-ES")}
                    </p>
                  </div>
                </div>
                <span
                  className="text-xs font-medium px-2.5 py-1 rounded-lg"
                  style={{
                    background: `${STATUS_COLOR[job.status]}15`,
                    color: STATUS_COLOR[job.status],
                  }}
                >
                  {job.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
