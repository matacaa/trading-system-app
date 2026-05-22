"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, Check, Eye, EyeOff, Mail, X } from "lucide-react";
import api from "@/lib/api";
import { AxiosError } from "axios";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // Post-register state
  const [registered, setRegistered] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  const [devToken, setDevToken] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  // Password strength
  const checks = useMemo(() => ({
    length: password.length >= 8,
    upper: /[A-Z]/.test(password),
    lower: /[a-z]/.test(password),
    symbol: /[^A-Za-z0-9]/.test(password),
  }), [password]);

  const allValid = checks.length && checks.upper && checks.lower && checks.symbol;
  const strength = [checks.length, checks.upper, checks.lower, checks.symbol].filter(Boolean).length;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setErrors([]);

    if (!allValid) {
      setError("La contraseña no cumple los requisitos");
      return;
    }

    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", {
        email: email.toLowerCase(),
        password,
        display_name: displayName || undefined,
      });
      setRegisteredEmail(data.email);
      setDevToken(data.verification_token || null);
      setRegistered(true);
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string | { errors?: string[] } }>;
      const detail = axErr.response?.data?.detail;
      if (typeof detail === "object" && detail?.errors) {
        setErrors(detail.errors);
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Error al crear la cuenta");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    try {
      await api.post("/auth/resend-verify", { email: registeredEmail });
      setResent(true);
      setTimeout(() => setResent(false), 5000);
    } catch {
      /* ignore */
    } finally {
      setResending(false);
    }
  };

  // ═══════════ POST-REGISTER: CHECK YOUR EMAIL ═══════════
  if (registered) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 relative z-10">
        <div className="glass-card w-full max-w-md p-8 animate-fade-in text-center">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6"
            style={{ background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))" }}
          >
            <Mail size={32} className="text-white" />
          </div>

          <h1 className="text-xl font-bold mb-2" style={{ color: "var(--text-primary)" }}>
            Revisa tu email
          </h1>

          <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
            Hemos enviado un enlace de verificación a
          </p>

          <p
            className="text-sm font-semibold mb-6 px-4 py-2 rounded-lg inline-block"
            style={{ background: "rgba(6, 182, 212, 0.1)", color: "var(--accent-cyan)" }}
          >
            {registeredEmail}
          </p>

          <p className="text-xs mb-6" style={{ color: "var(--text-muted)" }}>
            Haz click en el enlace del email para activar tu cuenta.
            El enlace expira en 24 horas.
          </p>

          <div className="space-y-3">
            <button
              onClick={handleResend}
              disabled={resending || resent}
              className="btn-secondary w-full flex items-center justify-center gap-2"
            >
              {resending ? (
                <div className="spin-slow w-4 h-4 border-2 border-current border-t-transparent rounded-full" />
              ) : resent ? (
                <>
                  <Check size={16} /> Enviado
                </>
              ) : (
                "Reenviar email"
              )}
            </button>

            <Link
              href="/login"
              className="btn-primary w-full flex items-center justify-center"
            >
              Ir a iniciar sesión
            </Link>
          </div>

          {/* Dev mode: show token when SMTP not configured */}
          {devToken && (
            <div
              className="mt-6 p-3 rounded-lg text-left"
              style={{
                background: "rgba(251, 191, 36, 0.1)",
                border: "1px solid rgba(251, 191, 36, 0.2)",
              }}
            >
              <p className="text-[0.65rem] font-bold mb-1" style={{ color: "var(--accent-amber)" }}>
                ⚠ Dev mode (SMTP no configurado)
              </p>
              <p className="text-[0.6rem] break-all font-mono" style={{ color: "var(--text-muted)" }}>
                Verificar manualmente:
              </p>
              <a
                href={`/verify-email?token=${devToken}`}
                className="text-[0.6rem] break-all"
                style={{ color: "var(--accent-cyan)" }}
              >
                /verify-email?token={devToken}
              </a>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ═══════════ REGISTER FORM ═══════════
  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative z-10">
      <div className="glass-card w-full max-w-md p-8 animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))" }}
          >
            <Activity size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>Squawks ML</h1>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>ML-powered trading alerts</p>
          </div>
        </div>

        <h2 className="text-lg font-semibold mb-6" style={{ color: "var(--text-primary)" }}>
          Crear cuenta
        </h2>

        {error && (
          <div
            className="mb-4 px-4 py-3 rounded-lg text-sm"
            style={{ background: "var(--accent-red-dim)", color: "var(--accent-red)", border: "1px solid rgba(239, 68, 68, 0.2)" }}
          >
            {error}
          </div>
        )}

        {errors.length > 0 && (
          <div
            className="mb-4 px-4 py-3 rounded-lg space-y-1"
            style={{ background: "var(--accent-red-dim)", border: "1px solid rgba(239, 68, 68, 0.2)" }}
          >
            {errors.map((e, i) => (
              <p key={i} className="text-sm" style={{ color: "var(--accent-red)" }}>{e}</p>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
              Nombre (opcional)
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="input-glass"
              placeholder="Tu nombre"
              autoComplete="name"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-glass"
              placeholder="tu@email.com"
              required
              autoComplete="email"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text-secondary)" }}>
              Contraseña
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-glass pr-10"
                placeholder="••••••••"
                required
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
                style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            {/* Strength bar */}
            {password.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="flex gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="h-1 flex-1 rounded-full transition-all duration-300"
                      style={{
                        background:
                          i < strength
                            ? strength <= 1
                              ? "var(--accent-red)"
                              : strength <= 2
                                ? "var(--accent-amber)"
                                : strength <= 3
                                  ? "var(--accent-cyan)"
                                  : "var(--accent-emerald)"
                            : "rgba(100,116,139,0.15)",
                      }}
                    />
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    { ok: checks.length, label: "8+ caracteres" },
                    { ok: checks.upper, label: "Mayúscula (A-Z)" },
                    { ok: checks.lower, label: "Minúscula (a-z)" },
                    { ok: checks.symbol, label: "Símbolo (!@#$...)" },
                  ].map((c) => (
                    <div key={c.label} className="flex items-center gap-1.5">
                      {c.ok ? (
                        <Check size={12} style={{ color: "var(--accent-emerald)" }} />
                      ) : (
                        <X size={12} style={{ color: "var(--text-muted)" }} />
                      )}
                      <span
                        className="text-[0.65rem]"
                        style={{ color: c.ok ? "var(--accent-emerald)" : "var(--text-muted)" }}
                      >
                        {c.label}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !allValid}
            className="btn-primary w-full flex items-center justify-center gap-2"
            style={{ opacity: allValid ? 1 : 0.5 }}
          >
            {loading && (
              <div className="spin-slow w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            )}
            {loading ? "Creando cuenta..." : "Crear cuenta"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="font-medium" style={{ color: "var(--accent-cyan)" }}>
            Iniciar sesión
          </Link>
        </p>
      </div>
    </div>
  );
}
