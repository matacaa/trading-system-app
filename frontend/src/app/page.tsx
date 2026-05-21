"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = getAccessToken();
    router.replace(token ? "/dashboard" : "/login");
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="spin-slow w-8 h-8 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
    </div>
  );
}
