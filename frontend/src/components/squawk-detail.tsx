"use client";

import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Clock,
  Shield,
  TrendingUp,
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
              background:
                squawk.direction === "LONG"
                  ? "var(--accent-emerald-dim)"
                  : "var(--accent-red-dim)",
              color:
                squawk.direction === "LONG"
                  ? "var(--accent-emerald)"
                  : "var(--accent-red)",
            }}
          >
            {squawk.direction === "LONG" ? (
              <ArrowUp size={14} />
            ) : (
              <ArrowDown size={14} />
            )}
            {squawk.direction}
          </span>
          <span className={`badge-${squawk.priority}`}>
            {squawk.priority}
          </span>
        </div>

        <h2
          className="text-lg font-semibold mb-1"
          style={{ color: "var(--text-primary)" }}
        >
          {squawk.title}
        </h2>

        <div
          className="flex items-center gap-3 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {dateStr} · {timeStr}
          </span>
          <span>{squawk.squawk_type}</span>
        </div>
      </div>

      {/* Audio player */}
      <div
        className="p-4 rounded-xl"
        style={{
          background: "rgba(6, 182, 212, 0.05)",
          border: "1px solid rgba(6, 182, 212, 0.1)",
        }}
      >
        <AudioPlayer url={squawk.audio_url} duration={squawk.audio_duration} />
      </div>

      {/* Body */}
      <div>
        <p
          className="text-sm leading-relaxed whitespace-pre-wrap"
          style={{ color: "var(--text-secondary)" }}
        >
          {squawk.body}
        </p>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard
          icon={<TrendingUp size={16} />}
          label="Score"
          value={squawk.score.toString()}
          color="var(--accent-cyan)"
        />
        <MetricCard
          icon={<BarChart3 size={16} />}
          label="Modelos"
          value={
            squawk.model_scores
              ? Object.keys(squawk.model_scores).length.toString()
              : "—"
          }
          color="var(--accent-violet)"
        />
        <MetricCard
          icon={<Shield size={16} />}
          label="Guardrails"
          value={
            squawk.guardrails_result
              ? `${Object.values(squawk.guardrails_result).filter(Boolean).length} ok`
              : "—"
          }
          color="var(--accent-emerald)"
        />
        <MetricCard
          icon={<Clock size={16} />}
          label="Audio"
          value={
            squawk.audio_duration
              ? `${Math.round(squawk.audio_duration)}s`
              : "—"
          }
          color="var(--accent-amber)"
        />
      </div>

      {/* Model scores */}
      {squawk.model_scores &&
        Object.keys(squawk.model_scores).length > 0 && (
          <div>
            <h3
              className="text-xs font-semibold uppercase tracking-wider mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Model Scores
            </h3>
            <div className="space-y-2">
              {Object.entries(squawk.model_scores).map(([name, score]) => (
                <div key={name} className="flex items-center justify-between">
                  <span
                    className="text-xs font-mono"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {name}
                  </span>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-24 h-1.5 rounded-full"
                      style={{ background: "rgba(100,116,139,0.15)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.min(100, Math.max(0, Number(score)))}%`,
                          background: "var(--accent-cyan)",
                        }}
                      />
                    </div>
                    <span
                      className="text-xs font-mono"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {typeof score === "number" ? score.toFixed(1) : String(score)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

      {/* Market data */}
      {squawk.market_data && Object.keys(squawk.market_data).length > 0 && (
        <div>
          <h3
            className="text-xs font-semibold uppercase tracking-wider mb-2"
            style={{ color: "var(--text-muted)" }}
          >
            Market Data
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(squawk.market_data).map(([key, val]) => (
              <div
                key={key}
                className="flex justify-between px-3 py-1.5 rounded-lg text-xs"
                style={{ background: "rgba(15,23,42,0.5)" }}
              >
                <span style={{ color: "var(--text-muted)" }}>{key}</span>
                <span
                  className="font-mono"
                  style={{ color: "var(--text-primary)" }}
                >
                  {typeof val === "number" ? val.toFixed(2) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div
      className="p-3 rounded-xl"
      style={{
        background: "rgba(15, 23, 42, 0.5)",
        border: "1px solid var(--border-glass)",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color }}>{icon}</span>
        <span className="text-[0.65rem] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          {label}
        </span>
      </div>
      <span className="text-lg font-bold font-mono" style={{ color }}>
        {value}
      </span>
    </div>
  );
}
