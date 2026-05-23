"use client";

import { useState } from "react";
import { Settings, User, Bell, Shield, Volume2 } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { PLAN_LIMITS } from "@/lib/types";

function playTestNotification() {
  const ctx = new AudioContext();

  // Tone 1: ascending notification
  const osc1 = ctx.createOscillator();
  const gain1 = ctx.createGain();
  osc1.type = "sine";
  osc1.frequency.setValueAtTime(587, ctx.currentTime); // D5
  osc1.frequency.setValueAtTime(784, ctx.currentTime + 0.15); // G5
  gain1.gain.setValueAtTime(0.3, ctx.currentTime);
  gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
  osc1.connect(gain1);
  gain1.connect(ctx.destination);
  osc1.start(ctx.currentTime);
  osc1.stop(ctx.currentTime + 0.4);

  // Tone 2: confirmation
  const osc2 = ctx.createOscillator();
  const gain2 = ctx.createGain();
  osc2.type = "sine";
  osc2.frequency.setValueAtTime(988, ctx.currentTime + 0.2); // B5
  gain2.gain.setValueAtTime(0.25, ctx.currentTime + 0.2);
  gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
  osc2.connect(gain2);
  gain2.connect(ctx.destination);
  osc2.start(ctx.currentTime + 0.2);
  osc2.stop(ctx.currentTime + 0.6);

  // Tone 3: final chime
  const osc3 = ctx.createOscillator();
  const gain3 = ctx.createGain();
  osc3.type = "sine";
  osc3.frequency.setValueAtTime(1175, ctx.currentTime + 0.35); // D6
  gain3.gain.setValueAtTime(0.2, ctx.currentTime + 0.35);
  gain3.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);
  osc3.connect(gain3);
  gain3.connect(ctx.destination);
  osc3.start(ctx.currentTime + 0.35);
  osc3.stop(ctx.currentTime + 0.8);

  setTimeout(() => ctx.close(), 1500);
}

function playTestSquawk() {
  const utterance = new SpeechSynthesisUtterance(
    "Squawk alert. AAPL long signal detected. Confidence 72 percent. RSI oversold at 28."
  );
  utterance.rate = 1.1;
  utterance.pitch = 1.0;
  utterance.volume = 1.0;
  utterance.lang = "en-US";
  speechSynthesis.speak(utterance);
}

export default function SettingsPage() {
  const { user } = useAuthStore();
  const plan = user?.plan || "trial";
  const limits = PLAN_LIMITS[plan] || PLAN_LIMITS.trial;
  const [audioStatus, setAudioStatus] = useState<"idle" | "ok" | "error">("idle");
  const [ttsStatus, setTtsStatus] = useState<"idle" | "playing" | "ok" | "error">("idle");

  const handleTestAudio = () => {
    try {
      playTestNotification();
      setAudioStatus("ok");
      setTimeout(() => setAudioStatus("idle"), 3000);
    } catch {
      setAudioStatus("error");
      setTimeout(() => setAudioStatus("idle"), 3000);
    }
  };

  const handleTestTTS = () => {
    try {
      setTtsStatus("playing");
      playTestSquawk();
      setTimeout(() => { setTtsStatus("ok"); }, 4000);
      setTimeout(() => { setTtsStatus("idle"); }, 7000);
    } catch {
      setTtsStatus("error");
      setTimeout(() => setTtsStatus("idle"), 3000);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <Settings size={22} style={{ color: "var(--accent-cyan)" }} />
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Configuración
        </h1>
      </div>

      {/* Profile */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-2">
          <User size={16} style={{ color: "var(--accent-cyan)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Perfil</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            { label: "Email", value: user?.email },
            { label: "Nombre", value: user?.display_name || "—" },
            { label: "Plan", value: user?.plan, color: "var(--accent-cyan)" },
            { label: "Miembro desde", value: user?.created_at ? new Date(user.created_at).toLocaleDateString("es-ES") : "—" },
          ].map((item) => (
            <div key={item.label}>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{item.label}</span>
              <p className="font-medium capitalize" style={{ color: item.color || "var(--text-primary)" }}>
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Notifications + Audio Test */}
      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Bell size={16} style={{ color: "var(--accent-amber)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Notificaciones</h2>
        </div>

        {/* Audio test section */}
        <div className="rounded-lg p-4 space-y-3" style={{ background: "rgba(15,23,42,0.5)", border: "1px solid var(--border-glass)" }}>
          <div className="flex items-center gap-2">
            <Volume2 size={14} style={{ color: "var(--accent-cyan)" }} />
            <span className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>Test de audio</span>
          </div>
          <p className="text-[0.7rem]" style={{ color: "var(--text-muted)" }}>
            Verifica que tu navegador puede reproducir sonidos de alerta y voz TTS para los squawks.
          </p>
          <div className="flex gap-3">
            <button
              onClick={handleTestAudio}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium"
              style={{
                background: audioStatus === "ok" ? "var(--accent-emerald-dim)" : "transparent",
                border: `1px solid ${audioStatus === "ok" ? "var(--accent-emerald)" : audioStatus === "error" ? "var(--accent-red)" : "var(--border-glass-hover)"}`,
                color: audioStatus === "ok" ? "var(--accent-emerald)" : audioStatus === "error" ? "var(--accent-red)" : "var(--accent-cyan)",
                cursor: "pointer",
              }}
            >
              <Volume2 size={14} />
              {audioStatus === "ok" ? "✓ Audio OK" : audioStatus === "error" ? "✗ Error" : "Probar sonido"}
            </button>
            <button
              onClick={handleTestTTS}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium"
              style={{
                background: ttsStatus === "ok" ? "var(--accent-emerald-dim)" : ttsStatus === "playing" ? "var(--accent-violet-dim)" : "transparent",
                border: `1px solid ${ttsStatus === "ok" ? "var(--accent-emerald)" : ttsStatus === "error" ? "var(--accent-red)" : ttsStatus === "playing" ? "var(--accent-violet)" : "var(--border-glass-hover)"}`,
                color: ttsStatus === "ok" ? "var(--accent-emerald)" : ttsStatus === "error" ? "var(--accent-red)" : ttsStatus === "playing" ? "var(--accent-violet)" : "var(--accent-cyan)",
                cursor: "pointer",
              }}
            >
              {ttsStatus === "playing" && <div className="spin-slow w-3 h-3 border-2 border-[var(--accent-violet)] border-t-transparent rounded-full" />}
              {ttsStatus === "playing" ? "Reproduciendo..." : ttsStatus === "ok" ? "✓ TTS OK" : ttsStatus === "error" ? "✗ Error TTS" : "Probar squawk TTS"}
            </button>
          </div>
          {audioStatus === "error" && (
            <p className="text-[0.65rem]" style={{ color: "var(--accent-red)" }}>
              Tu navegador bloqueó el audio. Revisa los permisos de sonido en la barra de direcciones.
            </p>
          )}
        </div>
      </div>

      {/* Plan limits */}
      <div className="glass-card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Shield size={16} style={{ color: "var(--accent-violet)" }} />
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Límites del plan {limits.label}
          </h2>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Tickers RT", value: limits.max_tickers },
            { label: "Custom models", value: limits.max_custom_models },
            { label: "Backtests/mes", value: limits.max_backtests_month },
            { label: "Trainings/mes", value: limits.max_trainings_month },
            { label: "Guardrails", value: limits.guardrails_count },
            { label: "Hist. máx (backtest)", value: `${limits.max_hist_days}d` },
            { label: "Modelos por backtest", value: limits.max_models_backtest },
            { label: "Ventana training", value: `${limits.max_training_days}d` },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center justify-between px-3 py-2 rounded-lg"
              style={{ background: "rgba(15,23,42,0.5)" }}
            >
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{item.label}</span>
              <span className="text-sm font-mono font-medium" style={{ color: "var(--text-primary)" }}>
                {item.value}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Los tickers se gestionan desde la pestaña Squawks (botón +).
        </p>
      </div>
    </div>
  );
}
