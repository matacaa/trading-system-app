"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ChevronLeft,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Volume2,
  X,
  Zap,
} from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS } from "@/lib/types";
import type { Squawk, Backtest, TickerInfo } from "@/lib/types";
import { useNotifications, useTabBadge } from "@/hooks/use-notifications";
import SquawkCard from "@/components/squawk-card";
import SquawkDetail from "@/components/squawk-detail";
import PriceChart from "@/components/price-chart";

export default function DashboardPage() {
  const { user, preferences, fetchMe } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;

  // Tickers
  const tickers: string[] = Array.isArray(preferences?.tickers) ? preferences!.tickers : [];
  const [activeTicker, setActiveTicker] = useState<string>(tickers[0] || "");
  const [tickerOn, setTickerOn] = useState<Record<string, boolean>>(() => {
    const s: Record<string, boolean> = {};
    tickers.forEach((t) => (s[t] = true));
    return s;
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Add ticker flow
  const [addOpen, setAddOpen] = useState(false);
  const [addStep, setAddStep] = useState<"search" | "backtests">("search");
  const [addSearch, setAddSearch] = useState("");
  const [addTicker, setAddTicker] = useState<string | null>(null);
  const [universeResults, setUniverseResults] = useState<TickerInfo[]>([]);
  const [addBacktests, setAddBacktests] = useState<Backtest[]>([]);

  // Squawks
  const [squawks, setSquawks] = useState<Squawk[]>([]);
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({});
  const [loadingSquawks, setLoadingSquawks] = useState(false);
  const [selectedSquawk, setSelectedSquawk] = useState<Squawk | null>(null);

  // Notifications
  const { permission, requestPermission, sendNotification } = useNotifications();
  const totalUnread = Object.values(unreadCounts).reduce((a, b) => a + b, 0);
  useTabBadge(totalUnread);

  // Toast
  const [toast, setToast] = useState<string | null>(null);
  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

  // Sync tickers from preferences
  useEffect(() => {
    if (preferences?.tickers && Array.isArray(preferences.tickers)) {
      setTickerOn((prev) => {
        const next: Record<string, boolean> = {};
        preferences.tickers.forEach((t: string) => { next[t] = prev[t] !== undefined ? prev[t] : true; });
        return next;
      });
      if (!activeTicker && preferences.tickers.length > 0) setActiveTicker(preferences.tickers[0]);
    }
  }, [preferences?.tickers, activeTicker]);

  // Fetch squawks for active ticker
  const fetchSquawks = useCallback(async (since?: string) => {
    if (!activeTicker) return;
    if (!since) setLoadingSquawks(true);
    try {
      const params: Record<string, string | number | boolean> = { ticker: activeTicker, limit: 50 };
      if (since) params.since = since;
      const { data } = await api.get("/api/squawks", { params });
      const incoming = data.squawks as Squawk[] || [];
      if (since) {
        setSquawks((prev) => {
          const ids = new Set(prev.map((s) => s.id));
          const fresh = incoming.filter((s) => !ids.has(s.id));
          if (fresh.length === 0) return prev;
          // Notify on high-priority
          if (fresh.some((s) => s.priority === "high")) {
            const hi = fresh.find((s) => s.priority === "high")!;
            sendNotification(`${hi.ticker} — ${hi.direction}`, { body: hi.title || hi.body, tag: hi.id });
          }
          return [...fresh, ...prev];
        });
      } else {
        setSquawks(incoming);
      }
    } catch { /* ignore */ }
    finally { if (!since) setLoadingSquawks(false); }
  }, [activeTicker, sendNotification]);

  useEffect(() => { fetchSquawks(); }, [fetchSquawks]);

  // Polling: unread counts + new squawks
  useEffect(() => {
    const poll = async () => {
      try {
        const { data } = await api.get("/api/squawks/unread");
        setUnreadCounts(data.unread || {});
      } catch { /* ignore */ }
      // Incremental squawk fetch
      if (activeTicker && squawks.length > 0) {
        fetchSquawks(squawks[0].created_at);
      }
    };
    const interval = setInterval(poll, 12_000);
    poll(); // initial
    return () => clearInterval(interval);
  }, [activeTicker, squawks, fetchSquawks]);

  // Search universe
  useEffect(() => {
    if (!addOpen || addStep !== "search") return;
    const search = async () => {
      try {
        const { data } = await api.get("/api/tickers/universe", { params: { search: addSearch || undefined, limit: 30 } });
        setUniverseResults((data.tickers || []).filter((t: TickerInfo) => !tickers.includes(t.ticker)));
      } catch { /* ignore */ }
    };
    const timeout = setTimeout(search, 300);
    return () => clearTimeout(timeout);
  }, [addSearch, addOpen, addStep, tickers]);

  // Fetch backtests for add-ticker
  useEffect(() => {
    if (!addTicker) return;
    api.get("/api/backtest/list", { params: { ticker: addTicker } })
      .then(({ data }) => setAddBacktests(data.backtests || []))
      .catch(() => {});
  }, [addTicker]);

  const activeCount = Object.values(tickerOn).filter(Boolean).length;
  const remaining = limits.max_tickers - activeCount;

  const handleToggleTicker = (t: string) => setTickerOn((prev) => ({ ...prev, [t]: !prev[t] }));

  const handleAddOpen = () => {
    if (remaining <= 0 && !addOpen) { showToast("Límite de tickers alcanzado"); return; }
    setAddOpen(!addOpen); setAddStep("search"); setAddSearch(""); setAddTicker(null);
  };

  const handleActivateWithBacktest = async (backtestId: string, btName: string) => {
    if (!addTicker) return;
    try {
      await api.post(`/api/preferences/tickers/${addTicker}/activate`, { backtest_id: backtestId });
      showToast(`✓ ${addTicker} activado con "${btName}"`);
      setAddOpen(false); setAddTicker(null); setActiveTicker(addTicker); fetchMe();
    } catch { showToast("Error al activar ticker"); }
  };

  // Squawk actions
  const handleSquawkAction = async (id: string, action: "read" | "favorite" | "dismiss") => {
    const body = action === "read" ? { is_read: true } : action === "favorite" ? { is_favorite: true } : { is_dismissed: true };
    try {
      await api.patch(`/api/squawks/${id}`, body);
      setSquawks((prev) => prev.map((s) => s.id === id ? { ...s, ...body } : s));
      if (action === "dismiss") setSquawks((prev) => prev.filter((s) => s.id !== id));
      if (action === "read") showToast("Marcado como leído");
      if (action === "favorite") showToast("Añadido a favoritos");
      if (action === "dismiss") { showToast("Descartado"); setSelectedSquawk(null); }
    } catch { showToast("Error al actualizar"); }
  };

  const unread = (t: string) => unreadCounts[t] || 0;

  // ═══════════ SIDEBAR ═══════════
  const sidebar = (
    <div
      className={`
        fixed lg:relative inset-y-0 left-0 z-40
        w-[220px] min-w-[220px] flex flex-col overflow-hidden
        transition-transform duration-300 lg:translate-x-0
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}
      style={{
        background: "rgba(0,0,0,0.85)",
        backdropFilter: "blur(20px)",
        borderRight: "1px solid var(--border-glass)",
      }}
    >
      {/* Header */}
      <div className="px-3 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border-glass)" }}>
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>Tickers</span>
          <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-mono" style={{ background: "rgba(255,255,255,0.05)", color: "var(--text-muted)" }}>
            {activeCount}/{limits.max_tickers}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {remaining > 0 && (
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded font-semibold" style={{ background: "var(--accent-cyan-dim)", color: "var(--accent-cyan)" }}>
              {remaining} disp.
            </span>
          )}
          <button onClick={handleAddOpen} className="w-6 h-6 rounded-md flex items-center justify-center" style={{ border: "1px solid var(--border-glass-hover)", background: addOpen ? "var(--accent-cyan-dim)" : "transparent", color: remaining <= 0 && !addOpen ? "var(--text-muted)" : "var(--accent-cyan)", cursor: remaining <= 0 && !addOpen ? "default" : "pointer" }}>
            {addOpen ? <X size={12} /> : <Plus size={12} />}
          </button>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden w-6 h-6 flex items-center justify-center" style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Add ticker: search */}
      {addOpen && addStep === "search" && (
        <div className="p-2 space-y-1" style={{ borderBottom: "1px solid var(--border-glass)" }}>
          <div className="relative">
            <input type="text" value={addSearch} onChange={(e) => setAddSearch(e.target.value)} placeholder="Buscar ticker..." className="input-glass text-xs pl-7 py-1.5" autoFocus />
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
          </div>
          <div className="max-h-44 overflow-y-auto">
            {universeResults.map((u) => (
              <button key={u.ticker} onClick={() => { setAddTicker(u.ticker); setAddStep("backtests"); }} className="w-full text-left px-2 py-1.5 text-xs flex justify-between rounded" style={{ color: "var(--text-primary)", background: "transparent", border: "none", cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-glass-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <span><b>{u.ticker}</b> <span style={{ color: "var(--text-muted)" }}>{u.name}</span></span>
                <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>{u.sector}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Add ticker: backtests */}
      {addOpen && addStep === "backtests" && addTicker && (
        <div className="p-2 space-y-2" style={{ borderBottom: "1px solid var(--border-glass)" }}>
          <div className="flex items-center justify-between">
            <button onClick={() => { setAddStep("search"); setAddTicker(null); }} className="text-xs flex items-center gap-1" style={{ color: "var(--accent-cyan)", background: "none", border: "none", cursor: "pointer" }}>
              <ChevronLeft size={12} /> Volver
            </button>
            <span className="text-xs font-bold" style={{ color: "var(--text-primary)" }}>{addTicker}</span>
          </div>
          {addBacktests.length > 0 ? (
            <>
              <p className="text-[0.65rem]" style={{ color: "var(--text-muted)" }}>Selecciona backtest:</p>
              {addBacktests.map((bt) => (
                <button key={bt.id} onClick={() => handleActivateWithBacktest(bt.id, bt.name)} className="w-full text-left glass-card p-2 rounded-lg cursor-pointer" style={{ border: "1px solid var(--border-glass)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")} onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-glass)")}>
                  <div className="flex justify-between text-xs"><b>{bt.name}</b>
                    {bt.pnl_pct != null && <span style={{ color: bt.pnl_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-red)", fontWeight: 600 }}>{bt.pnl_pct >= 0 ? "+" : ""}{bt.pnl_pct.toFixed(1)}%</span>}
                  </div>
                  <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{bt.direction} · {bt.date_from} → {bt.date_to}{bt.win_rate != null && ` · WR ${(bt.win_rate * 100).toFixed(0)}%`}</div>
                </button>
              ))}
              <a href="/dashboard/backtest" className="block w-full text-center text-[0.65rem] py-1.5 rounded-md" style={{ border: "1px dashed var(--border-glass-hover)", color: "var(--accent-cyan)" }}>+ Crear backtest nuevo</a>
            </>
          ) : (
            <div className="text-center py-4">
              <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>No hay backtests para {addTicker}</p>
              <a href="/dashboard/backtest" className="inline-block px-4 py-1.5 rounded-md text-xs font-medium" style={{ background: "var(--accent-cyan)", color: "white" }}>Crear backtest</a>
            </div>
          )}
        </div>
      )}

      {/* Ticker list */}
      <div className="flex-1 overflow-y-auto">
        {tickers.map((t) => {
          const isOn = tickerOn[t] !== false;
          const ur = unread(t);
          const dotColor = !isOn ? "var(--text-muted)" : ur > 0 ? "var(--accent-emerald)" : "var(--text-muted)";
          return (
            <div key={t} className="flex items-center" style={{ background: activeTicker === t ? "rgba(255,255,255,0.06)" : "transparent", borderLeft: activeTicker === t ? "2px solid var(--accent-cyan)" : "2px solid transparent" }}>
              <button onClick={() => { setActiveTicker(t); setSelectedSquawk(null); setSidebarOpen(false); }} className="flex items-center gap-2 flex-1 px-3 py-2.5 text-left" style={{ background: "none", border: "none", cursor: "pointer", color: activeTicker === t ? "var(--text-primary)" : "var(--text-muted)" }}>
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: dotColor }} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs" style={{ fontWeight: activeTicker === t ? 600 : 400 }}>{t}</div>
                  <div className="text-[0.6rem]" style={{ color: "var(--text-muted)" }}>{isOn ? `${ur} sin leer` : "pausado"}</div>
                </div>
                {isOn && ur > 0 && <span className="text-[0.6rem] px-1.5 py-0.5 rounded" style={{ background: "var(--accent-cyan)", color: "white", fontWeight: 600 }}>{ur}</span>}
              </button>
              <div className="pr-2">
                <button onClick={() => handleToggleTicker(t)} className="w-8 h-5 rounded-full relative" style={{ background: isOn ? "var(--accent-cyan)" : "var(--border-glass-hover)", border: "none", cursor: "pointer" }}>
                  <div className="w-3.5 h-3.5 rounded-full bg-white absolute top-[3px] transition-all duration-150" style={{ left: isOn ? 16 : 2 }} />
                </button>
              </div>
            </div>
          );
        })}
        {tickers.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 px-4 gap-2">
            <Zap size={24} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
            <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>Pulsa + para añadir un ticker</p>
          </div>
        )}
      </div>
    </div>
  );

  // ═══════════ OVERLAY ═══════════
  const overlay = sidebarOpen && (
    <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setSidebarOpen(false)} />
  );

  // ═══════════ DETAIL VIEW ═══════════
  if (selectedSquawk) {
    return (
      <div className="h-[calc(100vh-3rem)] flex">
        {overlay}{sidebar}
        <div className="flex-1 overflow-y-auto p-4 lg:p-5">
          <div className="flex items-center gap-2 mb-4">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden p-1" style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}><Menu size={18} /></button>
            <button onClick={() => setSelectedSquawk(null)} className="text-xs flex items-center gap-1" style={{ color: "var(--accent-cyan)", background: "none", border: "none", cursor: "pointer" }}>
              <ChevronLeft size={14} /> {activeTicker}
            </button>
          </div>
          <SquawkDetail squawk={selectedSquawk} onAction={handleSquawkAction} />
        </div>
        {toast && <Toast message={toast} />}
      </div>
    );
  }

  // ═══════════ MAIN FEED ═══════════
  return (
    <div className="h-[calc(100vh-3rem)] flex">
      {overlay}{sidebar}
      <div className="flex-1 overflow-y-auto p-4 lg:p-5 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden p-1" style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}><Menu size={18} /></button>
            <span className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{activeTicker || "Squawks"}</span>
            {activeTicker && <span className="text-xs" style={{ color: "var(--text-muted)" }}>{squawks.length} squawks · {squawks.filter((s) => !s.is_read).length} sin leer</span>}
          </div>
          <div className="flex items-center gap-2">
            {permission !== "granted" && (
              <button onClick={requestPermission} className="text-xs px-2 py-1 rounded-md" style={{ border: "1px solid var(--border-glass)", color: "var(--accent-amber)", background: "transparent", cursor: "pointer" }}>
                Notificaciones
              </button>
            )}
            <button onClick={() => fetchSquawks()} className="p-1.5 rounded-lg" style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
              <RefreshCw size={14} className={loadingSquawks ? "spin-slow" : ""} />
            </button>
          </div>
        </div>

        {!activeTicker ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Zap size={40} style={{ color: "var(--text-muted)", opacity: 0.2 }} />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>Selecciona un ticker o pulsa + para empezar</p>
          </div>
        ) : (
          <>
            {/* Price chart */}
            <PriceChart ticker={activeTicker} />

            {/* Feed */}
            <div className="text-[0.65rem] font-bold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Feed</div>
            <div className="space-y-2">
              {loadingSquawks && squawks.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <div className="spin-slow w-6 h-6 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>Cargando squawks...</span>
                </div>
              ) : squawks.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <Volume2 size={32} style={{ color: "var(--text-muted)", opacity: 0.3 }} />
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>No hay squawks para {activeTicker}</p>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>Aparecerán aquí cuando el pipeline detecte oportunidades</p>
                </div>
              ) : (
                squawks.map((s) => (
                  <SquawkCard key={s.id} squawk={s} selected={false} onSelect={(id) => { const sq = squawks.find((x) => x.id === id); if (sq) setSelectedSquawk(sq); }} />
                ))
              )}
            </div>
          </>
        )}
      </div>
      {toast && <Toast message={toast} />}
    </div>
  );
}

function Toast({ message }: { message: string }) {
  return (
    <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm animate-fade-in" style={{ background: "var(--bg-glass)", backdropFilter: "blur(16px)", border: "1px solid var(--border-glass)", color: "var(--accent-emerald)" }}>
      {message}
    </div>
  );
}
