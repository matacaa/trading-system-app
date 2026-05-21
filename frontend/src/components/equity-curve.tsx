"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import api from "@/lib/api";

interface EquityCurveProps {
  backtestId: string;
}

interface DataPoint {
  date: string;
  value: number;
}

export default function EquityCurve({ backtestId }: EquityCurveProps) {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCurve = async () => {
      setLoading(true);
      try {
        const { data: res } = await api.get(
          `/api/backtest/${backtestId}/equity`
        );
        setData(res.equity_curve || []);
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    };
    fetchCurve();
  }, [backtestId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="spin-slow w-5 h-5 border-2 border-[var(--accent-cyan)] border-t-transparent rounded-full" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-48 text-xs"
        style={{ color: "var(--text-muted)" }}
      >
        Sin datos de equity curve
      </div>
    );
  }

  const startVal = data[0]?.value ?? 0;
  const endVal = data[data.length - 1]?.value ?? 0;
  const isPositive = endVal >= startVal;
  const color = isPositive ? "#10b981" : "#ef4444";

  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`gradient-${backtestId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="rgba(100,116,139,0.1)"
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: "rgba(100,116,139,0.15)" }}
            tickFormatter={(v) => {
              const d = new Date(String(v));
              return `${d.getMonth() + 1}/${d.getDate()}`;
            }}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: "#64748b", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={55}
            tickFormatter={(v) => `${Number(v).toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              background: "rgba(17,24,39,0.95)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "8px",
              fontSize: "12px",
              color: "#f1f5f9",
            }}
            labelFormatter={(v) =>
              new Date(String(v)).toLocaleDateString("es-ES")
            }
            formatter={(v) => [`${Number(v).toFixed(2)}`, "Equity"]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#gradient-${backtestId})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
