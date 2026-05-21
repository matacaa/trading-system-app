"use client";

import { useState, useEffect } from "react";
import { Brain, Search, X } from "lucide-react";
import api from "@/lib/api";

interface ModelType {
  name: string;
  label: string;
  description: string;
  params_schema: Record<string, unknown>;
}

interface TrainingFormProps {
  onSuccess: () => void;
  onClose: () => void;
}

export default function TrainingForm({ onSuccess, onClose }: TrainingFormProps) {
  const [name, setName] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickers, setTickers] = useState<{ ticker: string; name: string }[]>(
    []
  );
  const [showTickerDropdown, setShowTickerDropdown] = useState(false);
  const [modelTypes, setModelTypes] = useState<ModelType[]>([]);
  const [selectedModelType, setSelectedModelType] = useState("");
  const [trainFrom, setTrainFrom] = useState("2023-01-01");
  const [trainTo, setTrainTo] = useState("2024-06-30");
  const [testFrom, setTestFrom] = useState("2024-07-01");
  const [testTo, setTestTo] = useState("2024-12-31");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [tickerRes, mtRes] = await Promise.all([
          api.get("/api/tickers/universe", { params: { limit: 100 } }),
          api.get("/api/model-types"),
        ]);
        setTickers(tickerRes.data.tickers || []);
        const types = mtRes.data.model_types || [];
        setModelTypes(types);
        if (types.length > 0) setSelectedModelType(types[0].name);
      } catch {
        /* ignore */
      }
    };
    fetchData();
  }, []);

  const filteredTickers = tickers.filter(
    (t) =>
      t.ticker.toLowerCase().includes(tickerSearch.toLowerCase()) ||
      (t.name && t.name.toLowerCase().includes(tickerSearch.toLowerCase()))
  );

  const handleSubmit = async () => {
    setErrors([]);
    setLoading(true);

    try {
      await api.post("/api/train", {
        name: name || `${selectedModelType}_${ticker}_${Date.now()}`,
        ticker,
        model_type: selectedModelType,
        hyperparameters: {},
        train_from: trainFrom,
        train_to: trainTo,
        test_from: testFrom,
        test_to: testTo,
      });
      onSuccess();
    } catch (err: unknown) {
      const resp = (
        err as {
          response?: { data?: { detail?: { errors?: string[] } | string } };
        }
      ).response?.data?.detail;
      if (typeof resp === "object" && resp?.errors) {
        setErrors(resp.errors);
      } else if (typeof resp === "string") {
        setErrors([resp]);
      } else {
        setErrors(["Error al lanzar training"]);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card p-5 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h3
          className="text-sm font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          Nuevo Entrenamiento
        </h3>
        <button onClick={onClose} style={{ color: "var(--text-muted)" }}>
          <X size={16} />
        </button>
      </div>

      {errors.length > 0 && (
        <div
          className="px-4 py-3 rounded-lg space-y-1"
          style={{
            background: "var(--accent-red-dim)",
            border: "1px solid rgba(239,68,68,0.2)",
          }}
        >
          {errors.map((e, i) => (
            <p
              key={i}
              className="text-xs"
              style={{ color: "var(--accent-red)" }}
            >
              {e}
            </p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Name */}
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Nombre (opcional)
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input-glass"
            placeholder="Mi modelo"
          />
        </div>

        {/* Ticker */}
        <div className="relative">
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Ticker
          </label>
          <div className="relative">
            <input
              type="text"
              value={showTickerDropdown ? tickerSearch : ticker}
              onChange={(e) => {
                setTickerSearch(e.target.value);
                setShowTickerDropdown(true);
              }}
              onFocus={() => setShowTickerDropdown(true)}
              className="input-glass pl-8"
              placeholder="Buscar..."
            />
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2"
              style={{ color: "var(--text-muted)" }}
            />
          </div>
          {showTickerDropdown && (
            <div
              className="absolute z-50 top-full left-0 right-0 mt-1 max-h-48 overflow-y-auto rounded-lg"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-glass)",
                boxShadow: "var(--shadow-glass)",
              }}
            >
              {filteredTickers.slice(0, 20).map((t) => (
                <button
                  key={t.ticker}
                  onClick={() => {
                    setTicker(t.ticker);
                    setTickerSearch("");
                    setShowTickerDropdown(false);
                  }}
                  className="w-full text-left px-3 py-2 text-xs flex justify-between transition-colors"
                  style={{ color: "var(--text-primary)" }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background =
                      "var(--bg-glass-hover)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "transparent")
                  }
                >
                  <span className="font-mono font-medium">{t.ticker}</span>
                  <span style={{ color: "var(--text-muted)" }}>{t.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Model type */}
        <div className="col-span-2">
          <label
            className="block text-xs font-medium mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            Tipo de modelo
          </label>
          <div className="grid grid-cols-3 gap-2">
            {modelTypes.map((mt) => (
              <button
                key={mt.name}
                onClick={() => setSelectedModelType(mt.name)}
                className="text-left p-3 rounded-lg transition-all"
                style={{
                  background:
                    selectedModelType === mt.name
                      ? "var(--accent-violet-dim)"
                      : "rgba(15,23,42,0.5)",
                  border: `1px solid ${
                    selectedModelType === mt.name
                      ? "rgba(139,92,246,0.3)"
                      : "var(--border-glass)"
                  }`,
                }}
              >
                <p
                  className="text-xs font-semibold"
                  style={{
                    color:
                      selectedModelType === mt.name
                        ? "var(--accent-violet)"
                        : "var(--text-primary)",
                  }}
                >
                  {mt.label || mt.name}
                </p>
                {mt.description && (
                  <p
                    className="text-[0.6rem] mt-0.5 line-clamp-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {mt.description}
                  </p>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Date ranges */}
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Train: desde
          </label>
          <input
            type="date"
            value={trainFrom}
            onChange={(e) => setTrainFrom(e.target.value)}
            className="input-glass"
          />
        </div>
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Train: hasta
          </label>
          <input
            type="date"
            value={trainTo}
            onChange={(e) => setTrainTo(e.target.value)}
            className="input-glass"
          />
        </div>
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Test: desde
          </label>
          <input
            type="date"
            value={testFrom}
            onChange={(e) => setTestFrom(e.target.value)}
            className="input-glass"
          />
        </div>
        <div>
          <label
            className="block text-xs font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Test: hasta
          </label>
          <input
            type="date"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            className="input-glass"
          />
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading || !selectedModelType}
        className="btn-primary w-full flex items-center justify-center gap-2"
        style={{
          background:
            "linear-gradient(135deg, var(--accent-violet), #7c3aed)",
        }}
      >
        {loading ? (
          <div className="spin-slow w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
        ) : (
          <Brain size={14} />
        )}
        {loading ? "Entrenando..." : "Lanzar Training"}
      </button>
    </div>
  );
}
