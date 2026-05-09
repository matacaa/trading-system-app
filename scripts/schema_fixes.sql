-- ════════════════════════════════════════════════════════════════════════════
-- schema_fixes.sql — Fixes de Supabase para trading-system
-- Generado: 26 abril 2026
-- Ejecutar en el panel SQL de Supabase en orden.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── F-19: Crear tabla config para circuit breaker ───────────────────────────
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY,
    trading_enabled BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO config (id, trading_enabled) VALUES (1, true)
ON CONFLICT (id) DO NOTHING;

-- ─── D-14: Índices críticos en gold_trades ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gold_trades_ts_salida_null
    ON gold_trades (ticker) WHERE ts_salida IS NULL;
CREATE INDEX IF NOT EXISTS idx_gold_trades_ts_entrada
    ON gold_trades (ts_entrada);
CREATE INDEX IF NOT EXISTS idx_gold_trades_alpaca_order_id
    ON gold_trades (alpaca_order_id);

-- ─── D-17: UNIQUE en alpaca_order_id ─────────────────────────────────────────
-- Descomentar cuando estés seguro de que no hay duplicados:
-- ALTER TABLE gold_trades ADD CONSTRAINT uq_gold_trades_alpaca_order_id
--     UNIQUE (alpaca_order_id);

-- ─── D-15: Índices en otras tablas GOLD ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gold_signals_experiment
    ON gold_signals (experiment_name);
CREATE INDEX IF NOT EXISTS idx_gold_signals_ts_ticker
    ON gold_signals (ts, ticker);
CREATE INDEX IF NOT EXISTS idx_gold_decisions_ts_ticker
    ON gold_decisions (ts, ticker);
CREATE INDEX IF NOT EXISTS idx_gold_logs_run_at
    ON gold_logs (run_at DESC);
CREATE INDEX IF NOT EXISTS idx_gold_pipeline_timings_run_id
    ON gold_pipeline_timings (run_id);

-- ─── D-18: UNIQUE en backtest_runs.name ──────────────────────────────────────
-- ALTER TABLE backtest_runs ADD CONSTRAINT uq_backtest_runs_name UNIQUE (name);

-- ─── N-08: Añadir run_id a gold_logs si no existe ───────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'gold_logs' AND column_name = 'run_id'
    ) THEN
        ALTER TABLE gold_logs ADD COLUMN run_id TEXT DEFAULT '';
    END IF;
END $$;

-- ─── D-01/D-06: Eliminar tablas legacy (opcional, descomentar) ──────────────
-- DROP TABLE IF EXISTS kpis;
-- DROP TABLE IF EXISTS ml_models;

-- ─── D-20: Índice para queries por experiment_name ──────────────────────────
CREATE INDEX IF NOT EXISTS idx_registry_experiment_active
    ON silver_model_registry (experiment_name, is_active);

-- ─── F-80: UNIQUE constraint en silver_features_rt ──────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_silver_features_rt_ticker_ts'
    ) THEN
        ALTER TABLE silver_features_rt
            ADD CONSTRAINT uq_silver_features_rt_ticker_ts UNIQUE (ticker, ts);
    END IF;
END $$;

-- ─── N-07: Verificar nombre de tabla ─────────────────────────────────────────
-- Ejecuta esta query para verificar:
-- SELECT table_name FROM information_schema.tables
--     WHERE table_name IN ('ingestion_log', 'ingestion_logs');
-- Si es 'ingestion_logs' (plural), renombrar:
-- ALTER TABLE ingestion_logs RENAME TO ingestion_log;

-- ─── D-09: id autoincremental en silver_features_rt ─────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'silver_features_rt' AND column_name = 'id'
    ) THEN
        ALTER TABLE silver_features_rt ADD COLUMN id SERIAL;
    END IF;
END $$;

-- ─── R-01: sentiment_label_encoded en tablas históricas (paridad con RT) ─────
ALTER TABLE silver_features_1m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_5m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;
ALTER TABLE silver_features_15m ADD COLUMN IF NOT EXISTS sentiment_label_encoded INTEGER DEFAULT 0;

-- ─── I-02: news_count en silver_features_rt (paridad con históricas) ─────────
ALTER TABLE silver_features_rt ADD COLUMN IF NOT EXISTS news_count_1h INTEGER DEFAULT 0;
ALTER TABLE silver_features_rt ADD COLUMN IF NOT EXISTS news_count_24h INTEGER DEFAULT 0;
ALTER TABLE silver_features_rt ADD COLUMN IF NOT EXISTS has_news INTEGER DEFAULT 0;

-- ─── Verificación final ──────────────────────────────────────────────────────
SELECT 'config' AS tabla, COUNT(*) AS filas FROM config
UNION ALL
SELECT 'gold_trades_indices', COUNT(*)::bigint FROM pg_indexes WHERE tablename = 'gold_trades'
UNION ALL
SELECT 'gold_signals_indices', COUNT(*)::bigint FROM pg_indexes WHERE tablename = 'gold_signals';
