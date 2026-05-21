"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, Volume2 } from "lucide-react";

interface AudioPlayerProps {
  url: string | null;
  duration?: number | null;
  compact?: boolean;
}

export default function AudioPlayer({
  url,
  duration,
  compact = false,
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    // Reset when URL changes
    setPlaying(false);
    setProgress(0);
    setCurrentTime(0);
  }, [url]);

  const toggle = useCallback(() => {
    if (!audioRef.current || !url) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  }, [playing, url]);

  const handleTimeUpdate = useCallback(() => {
    const a = audioRef.current;
    if (!a || !a.duration) return;
    setProgress((a.currentTime / a.duration) * 100);
    setCurrentTime(a.currentTime);
  }, []);

  const handleEnded = useCallback(() => {
    setPlaying(false);
    setProgress(0);
    setCurrentTime(0);
  }, []);

  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const a = audioRef.current;
      if (!a || !a.duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      a.currentTime = pct * a.duration;
    },
    []
  );

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (!url) {
    return (
      <div
        className="flex items-center gap-2 text-xs"
        style={{ color: "var(--text-muted)" }}
      >
        <Volume2 size={14} />
        Sin audio
      </div>
    );
  }

  const totalDuration = duration || audioRef.current?.duration || 0;

  return (
    <div className="flex items-center gap-3">
      {url && <audio ref={audioRef} src={url} onTimeUpdate={handleTimeUpdate} onEnded={handleEnded} preload="metadata" />}

      <button
        onClick={toggle}
        className="flex-shrink-0 flex items-center justify-center rounded-full transition-colors"
        style={{
          width: compact ? 28 : 34,
          height: compact ? 28 : 34,
          background: playing
            ? "var(--accent-cyan)"
            : "var(--accent-cyan-dim)",
          color: playing ? "white" : "var(--accent-cyan)",
        }}
      >
        {playing ? (
          <Pause size={compact ? 12 : 14} />
        ) : (
          <Play size={compact ? 12 : 14} style={{ marginLeft: 1 }} />
        )}
      </button>

      {!compact && (
        <>
          {/* Progress bar */}
          <div
            className="flex-1 h-1.5 rounded-full cursor-pointer"
            style={{ background: "rgba(100,116,139,0.2)" }}
            onClick={handleSeek}
          >
            <div
              className="h-full rounded-full transition-all duration-100"
              style={{
                width: `${progress}%`,
                background: "var(--accent-cyan)",
              }}
            />
          </div>

          {/* Time */}
          <span
            className="text-[0.65rem] tabular-nums flex-shrink-0"
            style={{ color: "var(--text-muted)" }}
          >
            {formatTime(currentTime)} / {formatTime(totalDuration)}
          </span>
        </>
      )}
    </div>
  );
}
