import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import type { Squawk } from "@/lib/types";

interface UseSquawksOptions {
  ticker?: string;
  priority?: string;
  pollInterval?: number; // ms, 0 to disable
  limit?: number;
}

export function useSquawks(opts: UseSquawksOptions = {}) {
  const { ticker, priority, pollInterval = 10_000, limit = 50 } = opts;
  const [squawks, setSquawks] = useState<Squawk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newCount, setNewCount] = useState(0);
  const lastTimestamp = useRef<string | null>(null);

  const fetchSquawks = useCallback(
    async (since?: string) => {
      try {
        const params: Record<string, string | number | boolean> = { limit };
        if (ticker) params.ticker = ticker;
        if (priority) params.priority = priority;
        if (since) params.since = since;

        const { data } = await api.get("/api/squawks", { params });
        return data.squawks as Squawk[];
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Error cargando squawks";
        setError(msg);
        return [];
      }
    },
    [ticker, priority, limit]
  );

  // Initial load
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchSquawks().then((data) => {
      if (cancelled) return;
      setSquawks(data);
      if (data.length > 0) {
        lastTimestamp.current = data[0].created_at;
      }
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [fetchSquawks]);

  // Polling for new squawks
  useEffect(() => {
    if (pollInterval <= 0) return;

    const interval = setInterval(async () => {
      if (!lastTimestamp.current) return;

      const newSquawks = await fetchSquawks(lastTimestamp.current);
      if (newSquawks.length > 0) {
        setSquawks((prev) => {
          // Dedupe by id
          const existingIds = new Set(prev.map((s) => s.id));
          const fresh = newSquawks.filter((s) => !existingIds.has(s.id));
          if (fresh.length === 0) return prev;
          return [...fresh, ...prev];
        });
        lastTimestamp.current = newSquawks[0].created_at;
        setNewCount((c) => c + newSquawks.length);
      }
    }, pollInterval);

    return () => clearInterval(interval);
  }, [pollInterval, fetchSquawks]);

  const clearNewCount = useCallback(() => setNewCount(0), []);

  const refresh = useCallback(async () => {
    setLoading(true);
    const data = await fetchSquawks();
    setSquawks(data);
    if (data.length > 0) {
      lastTimestamp.current = data[0].created_at;
    }
    setLoading(false);
  }, [fetchSquawks]);

  return { squawks, loading, error, newCount, clearNewCount, refresh };
}
