"use client";

import { create } from "zustand";
import { useEffect } from "react";
import { CheckCircle, X, XCircle, Info } from "lucide-react";

// ── Store ──────────────────────────────────────────────────────────────────

interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

interface ToastState {
  toasts: Toast[];
  addToast: (message: string, type?: Toast["type"]) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type = "info") => {
    const id = `${Date.now()}-${Math.random()}`;
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    // Auto-remove after 4s
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

// ── Component ──────────────────────────────────────────────────────────────

const ICONS = {
  success: <CheckCircle size={16} />,
  error: <XCircle size={16} />,
  info: <Info size={16} />,
};

const COLORS = {
  success: {
    bg: "var(--accent-emerald-dim)",
    border: "rgba(16,185,129,0.2)",
    text: "var(--accent-emerald)",
  },
  error: {
    bg: "var(--accent-red-dim)",
    border: "rgba(239,68,68,0.2)",
    text: "var(--accent-red)",
  },
  info: {
    bg: "var(--accent-cyan-dim)",
    border: "rgba(6,182,212,0.2)",
    text: "var(--accent-cyan)",
  },
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 space-y-2" style={{ maxWidth: 360 }}>
      {toasts.map((toast) => {
        const c = COLORS[toast.type];
        return (
          <div
            key={toast.id}
            className="flex items-center gap-3 px-4 py-3 rounded-xl animate-fade-in"
            style={{
              background: c.bg,
              border: `1px solid ${c.border}`,
              backdropFilter: "blur(16px)",
            }}
          >
            <span style={{ color: c.text }}>{ICONS[toast.type]}</span>
            <p className="text-sm flex-1" style={{ color: c.text }}>
              {toast.message}
            </p>
            <button
              onClick={() => removeToast(toast.id)}
              style={{ color: c.text, opacity: 0.6 }}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
