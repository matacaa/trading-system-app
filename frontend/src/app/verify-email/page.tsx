"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle, XCircle } from "lucide-react";
import api from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"loading" | "success" | "already" | "error">("loading");
  const [email, setEmail] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMsg("No se proporcionó token de verificación.");
      return;
    }

    const verify = async () => {
      try {
        const { data } = await api.get("/auth/verify-email", { params: { token } });
        if (data.already_verified) {
          setStatus("already");
        } else {
          setStatus("success");
        }
        setEmail(data.email || "");
      } catch (err: unknown) {
        setStatus("error");
        const axErr = err as { response?: { data?: { detail?: string } } };
        setErrorMsg(axErr.response?.data?.detail || "Token inválido o expirado.");
      }
    };

    verify();
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative z-10">
      <div className="glass-card w-full max-w-md p-8 animate-fade-in text-center">
        {status === "loading" && (
          <>
            <div className="flex justify-center mb-6">
              <div className="spin-slow w-12 h-12 border-3 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
            </div>
            <h1 className="text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>
              Verificando email...
            </h1>
          </>
        )}

        {status === "success" && (
          <>
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: "var(--accent-emerald-dim)" }}>
              <CheckCircle size={32} style={{ color: "var(--accent-emerald)" }} />
            </div>
            <h1 className="text-xl font-bold mb-2" style={{ color: "var(--accent-emerald)" }}>Email verificado</h1>
            <p className="text-sm mb-2" style={{ color: "var(--text-muted)" }}>Tu cuenta está activa.</p>
            {email && <p className="text-sm font-medium mb-6" style={{ color: "var(--text-primary)" }}>{email}</p>}
            <Link href="/login" className="btn-primary w-full flex items-center justify-center">Iniciar sesión</Link>
          </>
        )}

        {status === "already" && (
          <>
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: "var(--accent-cyan-dim)" }}>
              <CheckCircle size={32} style={{ color: "var(--accent-cyan)" }} />
            </div>
            <h1 className="text-lg font-bold mb-2" style={{ color: "var(--text-primary)" }}>Email ya verificado</h1>
            <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>Tu cuenta ya estaba verificada. Puedes iniciar sesión.</p>
            <Link href="/login" className="btn-primary w-full flex items-center justify-center">Iniciar sesión</Link>
          </>
        )}

        {status === "error" && (
          <>
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: "var(--accent-red-dim)" }}>
              <XCircle size={32} style={{ color: "var(--accent-red)" }} />
            </div>
            <h1 className="text-lg font-bold mb-2" style={{ color: "var(--accent-red)" }}>Verificación fallida</h1>
            <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>{errorMsg}</p>
            <Link href="/login" className="btn-primary w-full flex items-center justify-center">Ir a login</Link>
            <p className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>Puedes solicitar un nuevo enlace desde la pantalla de login.</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="spin-slow w-10 h-10 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  );
}
