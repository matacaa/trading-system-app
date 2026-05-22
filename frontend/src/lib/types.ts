// ── Plan limits (from backend plan_limits.py) ───────────────────────────────

export const PLAN_LIMITS: Record<
  string,
  {
    label: string;
    price: string;
    max_tickers: number;
    max_custom_models: number;
    max_backtests_month: number;
    max_backtests_saved: number;
    max_trainings_month: number;
    max_hist_days: number;
    max_training_days: number;
    max_models_backtest: number;
    guardrails_count: number;
  }
> = {
  trial: {
    label: "Trial",
    price: "Gratis (14 días)",
    max_tickers: 1,
    max_custom_models: 0,
    max_backtests_month: 5,
    max_backtests_saved: 5,
    max_trainings_month: 0,
    max_hist_days: 14,
    max_training_days: 0,
    max_models_backtest: 1,
    guardrails_count: 8,
  },
  starter: {
    label: "Starter",
    price: "9,99 €/mes",
    max_tickers: 3,
    max_custom_models: 3,
    max_backtests_month: 20,
    max_backtests_saved: 10,
    max_trainings_month: 5,
    max_hist_days: 90,
    max_training_days: 7,
    max_models_backtest: 3,
    guardrails_count: 12,
  },
  pro: {
    label: "Pro",
    price: "29,99 €/mes",
    max_tickers: 10,
    max_custom_models: 12,
    max_backtests_month: 50,
    max_backtests_saved: 30,
    max_trainings_month: 20,
    max_hist_days: 365,
    max_training_days: 90,
    max_models_backtest: 6,
    guardrails_count: 14,
  },
};

export const PLAN_HIST_LABEL: Record<string, string> = {
  trial: "2 semanas",
  starter: "3 meses",
  pro: "1 año",
};

export const PLAN_TRAIN_LABEL: Record<string, string> = {
  trial: "—",
  starter: "1 semana",
  pro: "3 meses",
};

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
  direction: string;
  market_data: Record<string, unknown> | null;
  model_scores: Record<string, unknown> | null;
  guardrails_result: Record<string, unknown> | null;
  is_read: boolean;
  is_favorite: boolean;
  is_dismissed?: boolean;
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
  model_name: string;
  ticker: string;
  model_type: string;
  status: string;
  progress_pct: number | null;
  hyperparameters: Record<string, unknown> | null;
  columns: string[] | null;
  context_tickers: string[] | null;
  metrics: Record<string, unknown> | null;
  error: string | null;
  train_from: string | null;
  train_to: string | null;
  test_from: string | null;
  test_to: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TrainingUsage {
  used_this_month: number;
  limit_month: number;
  remaining_month: number;
  custom_models?: number;
  limit_custom_models?: number;
}

// ── Model ───────────────────────────────────────────────────────────────────

export interface CustomModel {
  experiment_name: string;
  model_name: string;
  version: number;
  ticker: string;
  metrics_summary: Record<string, unknown> | null;
  hyperparameters: Record<string, unknown> | null;
  training_duration: string | null;
  train_from: string | null;
  train_to: string | null;
  test_from: string | null;
  test_to: string | null;
  blob_path: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ModelType {
  type_id: string;
  label: string;
  category: string;
  description?: string;
  params_schema: ParamDef[];
  // Backwards-compat: some code may reference .name
  name?: string;
}

export interface ParamDef {
  key: string;
  label: string;
  type?: string;
  default: number;
  min?: number;
  max?: number;
  step?: number;
}

/** @deprecated Use ParamDef instead — kept for compat with guardrails */
export interface ParamSchema {
  type: string;
  label: string;
  default: number;
  min?: number;
  max?: number;
  step?: number;
}

// ── Guardrail ───────────────────────────────────────────────────────────────

export interface Guardrail {
  name: string;
  label: string;
  category: string;
  phase: string;
  description?: string;
  params_schema?: Record<string, ParamSchema>;
}

// ── Subscription ────────────────────────────────────────────────────────────

export interface Subscription {
  has_subscription: boolean;
  plan: string | null;
  status: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

// ── Ticker ──────────────────────────────────────────────────────────────────

export interface TickerInfo {
  ticker: string;
  name: string;
  sector: string | null;
  exchange: string | null;
  model_coverage: string | null;
  // Extras from /tickers/silver-available
  data_from?: string;
  data_to?: string;
  row_count?: number;
}
