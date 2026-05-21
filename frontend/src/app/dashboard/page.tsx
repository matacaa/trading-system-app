"use client";

import { useEffect, useState } from "react";
import { Bell, BellRing, Filter, RefreshCw, Zap } from "lucide-react";
import { useSquawks } from "@/hooks/use-squawks";
import { useNotifications, useTabBadge } from "@/hooks/use-notifications";
import SquawkCard from "@/components/squawk-card";
import SquawkDetail from "@/components/squawk-detail";

const PRIORITIES = ["all", "high", "medium", "low"] as const;

export default function DashboardPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [showDetail, setShowDetail] = useState(false);

  const { squawks, loading, error, newCount, clearNewCount, refresh } =
    useSquawks({
      priority: filterPriority === "all" ? undefined : filterPriority,
      pollInterval: 10_000,
    });

  const { permission, requestPermission, sendNotification } = useNotifications();
  useTabBadge(newCount);

  // Send browser notification when new high-priority squawks arrive
  useEffect(() => {
    if (newCount > 0) {
      const latest = squawks[0];
      if (latest?.priority === "high") {
        sendNotification(`${latest.ticker} — ${latest.direction}`, {
          body: latest.title,
          tag: latest.id,
        });
      }
    }
  }, [newCount, squawks, sendNotification]);

  const selected = squawks.find((s) => s.id === selectedId) || null;

  const handleSelect = (id: string) => {
    setSelectedId(id);
    setShowDetail(true);
  };

  const handleRefresh = () => {
    clearNewCount();
    refresh();
  };

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col lg:flex-row gap-4 lg:gap-5">
      {/* ── Left: Squawk List ──────────────────────────────────────────────── */}
      <div
        className={`w-full lg:w-[400px] flex-shrink-0 flex flex-col glass-card overflow-hidden ${showDetail ? "hidden lg:flex" : "flex"}`}
        style={{ maxHeight: "100%" }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: "1px solid var(--border-glass)" }}
        >
          <div className="flex items-center gap-2">
            <Zap size={18} style={{ color: "var(--accent-cyan)" }} />
            <h2
              className="text-sm font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              Squawks
            </h2>
            {newCount > 0 && (
              <span
                className="text-[0.6rem] font-bold px-1.5 py-0.5 rounded-full"
                style={{
                  background: "var(--accent-cyan)",
                  color: "white",
                }}
              >
                {newCount}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {permission !== "granted" && (
              <button
                onClick={requestPermission}
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: "var(--accent-amber)" }}
                title="Activar notificaciones"
              >
                <BellRing size={14} />
              </button>
            )}
            <button
              onClick={handleRefresh}
              className="p-1.5 rounded-lg transition-colors"
              style={{ color: "var(--text-muted)" }}
              title="Refrescar"
            >
              <RefreshCw size={14} className={loading ? "spin-slow" : ""} />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div
          className="flex items-center gap-1.5 px-4 py-2"
          style={{ borderBottom: "1px solid var(--border-glass)" }}
        >
          <Filter
            size={12}
            style={{ color: "var(--text-muted)" }}
          />
          {PRIORITIES.map((p) => (
            <button
              key={p}
              onClick={() => setFilterPriority(p)}
              className="text-[0.65rem] font-medium px-2.5 py-1 rounded-md transition-all"
              style={{
                background:
                  filterPriority === p
                    ? "var(--accent-cyan-dim)"
                    : "transparent",
                color:
                  filterPriority === p
                    ? "var(--accent-cyan)"
                    : "var(--text-muted)",
              }}
            >
              {p === "all" ? "Todos" : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {loading && squawks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
              <span
                className="text-xs"
                style={{ color: "var(--text-muted)" }}
              >
                Cargando squawks...
              </span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2">
              <p
                className="text-sm"
                style={{ color: "var(--accent-red)" }}
              >
                {error}
              </p>
              <button onClick={handleRefresh} className="btn-secondary text-xs">
                Reintentar
              </button>
            </div>
          ) : squawks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <Bell
                size={32}
                style={{ color: "var(--text-muted)", opacity: 0.3 }}
              />
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                No hay squawks todavía
              </p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                Aparecerán aquí cuando el sistema detecte oportunidades
              </p>
            </div>
          ) : (
            squawks.map((s) => (
              <SquawkCard
                key={s.id}
                squawk={s}
                selected={selectedId === s.id}
                onSelect={handleSelect}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Right: Detail Panel ────────────────────────────────────────────── */}
      <div className={`flex-1 glass-card overflow-y-auto p-4 lg:p-6 ${showDetail ? "flex flex-col" : "hidden lg:flex lg:flex-col"}`}>
        {selected ? (
          <>
            <button
              onClick={() => setShowDetail(false)}
              className="lg:hidden mb-3 text-xs flex items-center gap-1"
              style={{ color: "var(--accent-cyan)" }}
            >
              ← Volver a la lista
            </button>
            <SquawkDetail squawk={selected} />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Zap
              size={40}
              style={{ color: "var(--text-muted)", opacity: 0.2 }}
            />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Selecciona un squawk para ver el detalle
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
