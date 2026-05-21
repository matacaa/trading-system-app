// ── Squawk ──────────────────────────────────────────────────────────────────

export interface Squawk {
  id: string;
  ticker: string;
  squawk_type: string;
  title: string;
  body: string;
  audio_url: string | null;
  audio_duration: number | null;
  priority: "high" | "medium" | "low";
  score: number;
  direction: "LONG" | "SHORT";
  market_data: Record<string, unknown> | null;
  model_scores: Record<string, unknown> | null;
  guardrails_result: Record<string, unknown> | null;
  is_read: boolean;
  is_favorite: boolean;
  created_at: string;
}

// ── Backtest ────────────────────────────────────────────────────────────────

export interface Backtest {
  id: string;
  name: string;
  ticker: string;
  direction: string;
  date_from: string;
  date_to: string;
  guardrails_config: Record<string, unknown> | null;
  models_config: Record<string, number> | null;
  models_enabled: boolean;
  status: string;
  created_at: string;
  total_trades: number | null;
  pnl_total: number | null;
  pnl_pct: number | null;
  win_rate: number | null;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
  equity_curve: Array<{ date: string; value: number }> | null;
}

export interface BacktestUsage {
  used_this_month: number;
  limit_month: number;
  remaining_month: number;
  saved_total: number;
  limit_saved: number;
}

// ── Training ────────────────────────────────────────────────────────────────

export interface TrainingJob {
  id: string;
  name: string;
  ticker: string;
  model_type: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  metrics: Record<string, unknown> | null;
}

export interface TrainingUsage {
  used_this_month: number;
  limit_month: number;
  remaining_month: number;
}

// ── Subscription ────────────────────────────────────────────────────────────

export interface Subscription {
  has_subscription: boolean;
  plan: string | null;
  status: string | null;
  period_start: string | null;
  period_end: string | null;
  cancel_at_period_end: boolean;
}

// ── Ticker ──────────────────────────────────────────────────────────────────

export interface Ticker {
  ticker: string;
  name: string;
  sector: string | null;
  market_cap: number | null;
  is_active: boolean;
}

// ── Plan limits (from backend plan_limits.py) ───────────────────────────────

export const PLAN_LIMITS: Record<
  string,
  {
    label: string;
    price: string;
    max_tickers: number;
    max_custom_models: number;
    max_backtests_month: number;
    max_trainings_month: number;
    guardrails_count: number;
  }
> = {
  trial: {
    label: "Trial",
    price: "Gratis (14 días)",
    max_tickers: 1,
    max_custom_models: 0,
    max_backtests_month: 5,
    max_trainings_month: 0,
    guardrails_count: 8,
  },
  starter: {
    label: "Starter",
    price: "9,99 €/mes",
    max_tickers: 3,
    max_custom_models: 3,
    max_backtests_month: 20,
    max_trainings_month: 5,
    guardrails_count: 12,
  },
  pro: {
    label: "Pro",
    price: "29,99 €/mes",
    max_tickers: 10,
    max_custom_models: 12,
    max_backtests_month: 50,
    max_trainings_month: 20,
    guardrails_count: 14,
  },
};
