"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
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

  return (
    <button
      onClick={() => onSelect(squawk.id)}
      className="w-full text-left p-4 rounded-xl transition-all duration-200 animate-fade-in"
      style={{
        background: selected
          ? "var(--bg-glass-hover)"
          : "transparent",
        border: `1px solid ${selected ? "var(--accent-cyan)" : "var(--border-glass)"}`,
        opacity: squawk.is_read && !selected ? 0.7 : 1,
      }}
    >
      {/* Top row: ticker + direction + priority + time */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="font-mono text-sm font-bold"
            style={{ color: "var(--text-primary)" }}
          >
            {squawk.ticker}
          </span>
          <span
            className="inline-flex items-center gap-0.5 text-[0.65rem] font-semibold px-1.5 py-0.5 rounded"
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
              <ArrowUp size={10} />
            ) : (
              <ArrowDown size={10} />
            )}
            {squawk.direction}
          </span>
          <span className={`badge-${squawk.priority}`}>
            {squawk.priority}
          </span>
        </div>
        <span
          className="text-[0.65rem]"
          style={{ color: "var(--text-muted)" }}
        >
          {timeAgo}
        </span>
      </div>

      {/* Title */}
      <p
        className="text-sm font-medium mb-1 line-clamp-1"
        style={{ color: "var(--text-primary)" }}
      >
        {squawk.title}
      </p>

      {/* Body snippet */}
      <p
        className="text-xs line-clamp-2 mb-3"
        style={{ color: "var(--text-secondary)" }}
      >
        {squawk.body}
      </p>

      {/* Audio + score */}
      <div className="flex items-center justify-between">
        <AudioPlayer
          url={squawk.audio_url}
          duration={squawk.audio_duration}
          compact
        />
        <span
          className="text-xs font-mono"
          style={{ color: "var(--text-muted)" }}
        >
          Score {squawk.score}
        </span>
      </div>
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
