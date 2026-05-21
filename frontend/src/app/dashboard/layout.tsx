"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import Sidebar, { MobileMenuButton } from "@/components/sidebar";
import ToastContainer from "@/components/toast";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, isLoading, hydrate } = useAuthStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="spin-slow w-8 h-8 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex min-h-screen relative z-10">
      <MobileMenuButton onClick={() => setMobileOpen(true)} />
      <Sidebar mobileOpen={mobileOpen} onClose={closeMobile} />
      <main className="flex-1 p-4 lg:p-6 overflow-auto lg:ml-[var(--sidebar-width)]">
        {children}
      </main>
      <ToastContainer />
    </div>
  );
}
