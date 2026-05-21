"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Brain,
  CreditCard,
  LogOut,
  Menu,
  Settings,
  X,
  Zap,
} from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { useState, useEffect } from "react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Squawks", icon: Zap },
  { href: "/dashboard/backtest", label: "Backtest", icon: BarChart3 },
  { href: "/dashboard/training", label: "Training", icon: Brain },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
];

export function MobileMenuButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg"
      style={{
        background: "var(--bg-glass)",
        border: "1px solid var(--border-glass)",
        color: "var(--text-primary)",
      }}
    >
      <Menu size={20} />
    </button>
  );
}

export default function Sidebar({
  mobileOpen,
  onClose,
}: {
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  // Close on route change
  useEffect(() => {
    onClose();
  }, [pathname, onClose]);

  const planColor: Record<string, string> = {
    trial: "var(--accent-amber)",
    starter: "var(--accent-cyan)",
    pro: "var(--accent-violet)",
  };

  return (
    <>
      {/* Overlay for mobile */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed left-0 top-0 bottom-0 w-[var(--sidebar-width)] glass flex flex-col z-50
          transition-transform duration-300 ease-in-out
          lg:translate-x-0
          ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
        style={{ borderRight: "1px solid var(--border-glass)", borderRadius: 0 }}
      >
        {/* Logo + close on mobile */}
        <div className="px-5 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{
                background:
                  "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))",
              }}
            >
              <Activity size={18} className="text-white" />
            </div>
            <div>
              <h1
                className="text-sm font-bold tracking-tight"
                style={{ color: "var(--text-primary)" }}
              >
                Squawks ML
              </h1>
              <span
                className="text-[0.65rem] font-medium uppercase tracking-widest"
                style={{
                  color:
                    planColor[user?.plan || "trial"] || "var(--text-muted)",
                }}
              >
                {user?.plan || "trial"}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden p-1"
            style={{ color: "var(--text-muted)" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-2 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200"
                style={{
                  background: isActive
                    ? "var(--accent-cyan-dim)"
                    : "transparent",
                  color: isActive
                    ? "var(--accent-cyan)"
                    : "var(--text-secondary)",
                }}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div
          className="px-3 py-4 space-y-2"
          style={{ borderTop: "1px solid var(--border-glass)" }}
        >
          <div className="px-3 py-2">
            <p
              className="text-xs font-medium truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {user?.display_name || user?.email || "—"}
            </p>
            <p
              className="text-[0.65rem] truncate"
              style={{ color: "var(--text-muted)" }}
            >
              {user?.email}
            </p>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.color = "var(--accent-red)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.color = "var(--text-muted)")
            }
          >
            <LogOut size={16} />
            Cerrar sesión
          </button>
        </div>
      </aside>
    </>
  );
}
