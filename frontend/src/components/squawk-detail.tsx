"use client";

import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  BookOpen,
  Clock,
  Minus,
  Info,
  Shield,
  Star,
  TrendingUp,
  Trash2,
} from "lucide-react";
import type { Squawk } from "@/lib/types";
import AudioPlayer from "./audio-player";

interface SquawkDetailProps {
  squawk: Squawk;
}

export default function SquawkDetail({ squawk }: SquawkDetailProps) {
  const created = new Date(squawk.created_at);
  const dateStr = created.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const timeStr = created.toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const dir = squawk.direction?.toUpperCase() || squawk.squawk_type?.toUpperCase() || "INFO";
  const isBuy = dir === "LONG" || dir === "BUY";
  const isSell = dir === "SHORT" || dir === "SELL";
  const label = isBuy ? "LONG" : isSell ? "SHORT" : dir === "HOLD" ? "HOLD" : "INFO";

  return (
    <div className="animate-fade-in space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <span
            className="font-mono text-lg font-bold"
            style={{ color: "var(--text-primary)" }}
          >
            {squawk.ticker}
          </span>
          <span
            className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg"
            style={{
              background: isBuy
                ? "var(--accent-emerald-dim)"
                : isSell
                  ? "var(--accent-red-dim)"
                  : "var(--accent-amber-dim)",
              color: isBuy
                ? "var(--accent-emerald)"
                : isSell
                  ? "var(--accent-red)"
                  : "var(--accent-amber)",
            }}
          >
            {isBuy ? <ArrowUp size={14} /> : isSell ? <ArrowDown size={14} /> : <Minus size={14} />}
            {label}
          </span>
          <span className={`badge-${squawk.priority}`}>{squawk.priority}</span>
          <span
            className="text-sm font-mono"
            style={{ color: "var(--text-muted)" }}
          >
            Score {squawk.score}
          </span>
        </div>

        <div
          className="flex items-center gap-3 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {dateStr} · {timeStr}
          </span>
        </div>
      </div>

      {/* Audio player */}
      {squawk.audio_url && (
        <div
          className="p-4 rounded-xl"
          style={{
            background: "rgba(6, 182, 212, 0.05)",
            border: "1px solid rgba(6, 182, 212, 0.1)",
          }}
        >
          <AudioPlayer url={squawk.audio_url} duration={squawk.audio_duration} />
        </div>
      )}

      {/* Body */}
      <div
        className="glass-card p-4 text-sm leading-relaxed whitespace-pre-wrap"
        style={{ color: "var(--text-secondary)" }}
      >
        {squawk.body || squawk.title}
      </div>

      {/* Market Data + Model Scores grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Market Data */}
        {squawk.market_data && Object.keys(squawk.market_data).length > 0 && (
          <div className="glass-card p-4">
            <h3
              className="text-[0.65rem] font-bold uppercase tracking-wider mb-3"
              style={{ color: "var(--text-muted)" }}
            >
              Market Data
            </h3>
            <div className="space-y-1">
              {Object.entries(squawk.market_data).map(([key, val]) => (
                <div
                  key={key}
                  className="flex justify-between text-xs py-0.5"
                >
                  <span style={{ color: "var(--text-muted)" }}>{key}</span>
                  <span className="font-mono" style={{ color: "var(--text-primary)" }}>
                    {typeof val === "number" ? val.toFixed(2) : String(val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Model Scores */}
        {squawk.model_scores && Object.keys(squawk.model_scores).length > 0 && (
          <div className="glass-card p-4">
            <h3
              className="text-[0.65rem] font-bold uppercase tracking-wider mb-3"
              style={{ color: "var(--text-muted)" }}
            >
              Model Scores
            </h3>
            <div className="space-y-2">
              {Object.entries(squawk.model_scores).map(([name, score]) => {
                const v = Number(score);
                return (
                  <div key={name} className="flex items-center justify-between">
                    <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                      {name}
                    </span>
                    <div className="flex items-center gap-2">
                      <div
                        className="w-12 h-1 rounded-full"
                        style={{ background: "rgba(100,116,139,0.15)" }}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.min(100, Math.max(0, v))}%`,
                            background:
                              v >= 65
                                ? "var(--accent-emerald)"
                                : v >= 50
                                  ? "var(--accent-amber)"
                                  : "var(--accent-red)",
                          }}
                        />
                      </div>
                      <span
                        className="text-xs font-mono w-6 text-right"
                        style={{
                          color:
                            v >= 65
                              ? "var(--accent-emerald)"
                              : "var(--accent-amber)",
                        }}
                      >
                        {v.toFixed(0)}
                      </span>
                    </div>
                  </div>
                );
              })}
              <div
                className="flex justify-between pt-2 mt-2"
                style={{ borderTop: "1px solid var(--border-glass)" }}
              >
                <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Ensemble</span>
                <span
                  className="text-lg font-bold font-mono"
                  style={{
                    color:
                      squawk.score >= 65
                        ? "var(--accent-emerald)"
                        : "var(--accent-amber)",
                  }}
                >
                  {squawk.score}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Guardrails */}
      {squawk.guardrails_result && Object.keys(squawk.guardrails_result).length > 0 && (
        <div className="glass-card p-4">
          <h3
            className="text-[0.65rem] font-bold uppercase tracking-wider mb-3"
            style={{ color: "var(--text-muted)" }}
          >
            Guardrails
          </h3>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(squawk.guardrails_result).map(([k, v]) => (
              <span
                key={k}
                className="text-[0.7rem] font-medium px-2 py-1 rounded-md"
                style={{
                  background: v ? "var(--accent-emerald-dim)" : "var(--accent-red-dim)",
                  color: v ? "var(--accent-emerald)" : "var(--accent-red)",
                }}
              >
                {v ? "✓" : "✗"} {k}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          className="btn-primary flex items-center gap-2 text-sm"
          style={{ background: "linear-gradient(135deg, var(--accent-cyan), #0891b2)" }}
        >
          <BookOpen size={14} /> Leído
        </button>
        <button
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <Star size={14} /> Favorito
        </button>
        <button
          className="flex items-center gap-2 text-sm px-4 py-2 rounded-lg"
          style={{
            border: "1px solid rgba(239,68,68,0.2)",
            color: "var(--accent-red)",
            background: "transparent",
            cursor: "pointer",
          }}
        >
          <Trash2 size={14} /> Descartar
        </button>
      </div>
    </div>
  );
}
