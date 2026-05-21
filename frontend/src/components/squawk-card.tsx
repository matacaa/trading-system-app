"use client";

import { ArrowDown, ArrowUp, Minus, Info, Volume2, Star } from "lucide-react";
import type { Squawk } from "@/lib/types";
import AudioPlayer from "./audio-player";

interface SquawkCardProps {
  squawk: Squawk;
  selected: boolean;
  onSelect: (id: string) => void;
}

export default function SquawkCard({
  squawk,
  selected,
  onSelect,
}: SquawkCardProps) {
  const timeAgo = getTimeAgo(squawk.created_at);
  const dir = squawk.direction?.toUpperCase() || squawk.squawk_type?.toUpperCase() || "INFO";
  const isBuy = dir === "LONG" || dir === "BUY";
  const isSell = dir === "SHORT" || dir === "SELL";
  const label = isBuy ? "LONG" : isSell ? "SHORT" : dir === "HOLD" ? "HOLD" : "INFO";

  return (
    <button
      onClick={() => onSelect(squawk.id)}
      className="w-full text-left p-4 rounded-xl transition-all duration-200 animate-fade-in"
      style={{
        background: selected ? "var(--bg-glass-hover)" : "transparent",
        border: `1px solid ${selected ? "var(--accent-cyan)" : "var(--border-glass)"}`,
        borderLeft: `3px solid ${isBuy ? "var(--accent-emerald)" : isSell ? "var(--accent-red)" : "transparent"}`,
        opacity: squawk.is_read && !selected ? 0.6 : 1,
      }}
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-0.5 text-[0.65rem] font-semibold px-1.5 py-0.5 rounded"
            style={{
              background: isBuy
                ? "var(--accent-emerald-dim)"
                : isSell
                  ? "var(--accent-red-dim)"
                  : label === "HOLD"
                    ? "var(--accent-amber-dim)"
                    : "var(--accent-cyan-dim)",
              color: isBuy
                ? "var(--accent-emerald)"
                : isSell
                  ? "var(--accent-red)"
                  : label === "HOLD"
                    ? "var(--accent-amber)"
                    : "var(--accent-cyan)",
            }}
          >
            {isBuy ? <ArrowUp size={10} /> : isSell ? <ArrowDown size={10} /> : label === "HOLD" ? <Minus size={10} /> : <Info size={10} />}
            {label}
          </span>
          <span className="text-xs font-mono font-semibold" style={{ color: "var(--text-primary)" }}>
            Score {squawk.score}
          </span>
          <span className={`badge-${squawk.priority}`}>
            {squawk.priority}
          </span>
          {squawk.audio_url && (
            <Volume2 size={11} style={{ color: "var(--accent-cyan)" }} />
          )}
          {squawk.is_favorite && (
            <Star size={11} style={{ color: "var(--accent-amber)" }} fill="var(--accent-amber)" />
          )}
        </div>
        <span className="text-[0.65rem]" style={{ color: "var(--text-muted)" }}>
          {timeAgo}
        </span>
      </div>

      {/* Body snippet */}
      <p className="text-xs line-clamp-2 mb-2" style={{ color: "var(--text-secondary)" }}>
        {squawk.body || squawk.title}
      </p>

      {/* Guardrails mini */}
      {squawk.guardrails_result && (
        <div className="flex gap-1 flex-wrap">
          {Object.entries(squawk.guardrails_result).map(([k, v]) => (
            <span
              key={k}
              className="text-[0.55rem] px-1 py-0.5 rounded"
              style={{
                background: v ? "var(--accent-emerald-dim)" : "var(--accent-red-dim)",
                color: v ? "var(--accent-emerald)" : "var(--accent-red)",
              }}
            >
              {v ? "✓" : "✗"}{k}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function getTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "ahora";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
