-- ════════════════════════════════════════════════════════════════════════════
-- migration_fase6_alter.sql — Fase 6: ALTER TABLE existentes
-- Fecha: 20 mayo 2026
-- Ejecutar DESPUÉS de migration_fase6_tables.sql.
-- Idempotente: usa IF NOT EXISTS / DO $$ para cada columna.
--
-- 3 ALTER TABLE:
--   1. backtest_runs          +8 columnas
--   2. silver_model_registry  +10 columnas
--   3. user_preferences       +2 columnas
-- ════════════════════════════════════════════════════════════════════════════


-- ─── 1. ALTER BACKTEST_RUNS (+8 columnas) ─────────────────────────────────

ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS ticker           VARCHAR(10),
    ADD COLUMN IF NOT EXISTS direction        VARCHAR(10) DEFAULT 'long',
    ADD COLUMN IF NOT EXISTS date_from        DATE,
    ADD COLUMN IF NOT EXISTS date_to          DATE,
    ADD COLUMN IF NOT EXISTS guardrails_config JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS models_config    JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS models_enabled   BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS equity_curve     JSONB;

-- CHECK constraint para direction (idempotente con DO $$)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_bt_direction' AND conrelid = 'backtest_runs'::regclass
    ) THEN
        ALTER TABLE backtest_runs
            ADD CONSTRAINT chk_bt_direction CHECK (direction IN ('long', 'short'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_bt_user_ticker ON backtest_runs(user_id, ticker);

COMMENT ON COLUMN backtest_runs.direction IS 'long = señales LONG (▲), short = señales SHORT (▼)';
COMMENT ON COLUMN backtest_runs.guardrails_config IS 'Config completa de guardrails usada en este backtest';
COMMENT ON COLUMN backtest_runs.models_config IS 'Modelos + pesos: {"lgbm": 0.6, "aapl_lgbm_v2": 0.4}';
COMMENT ON COLUMN backtest_runs.equity_curve IS 'Serie temporal [{ts, value}] para chart';


-- ─── 2. ALTER SILVER_MODEL_REGISTRY (+10 columnas) ────────────────────────

ALTER TABLE silver_model_registry
    ADD COLUMN IF NOT EXISTS user_id              UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS hyperparameters      JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS train_from           DATE,
    ADD COLUMN IF NOT EXISTS train_to             DATE,
    ADD COLUMN IF NOT EXISTS test_from            DATE,
    ADD COLUMN IF NOT EXISTS test_to              DATE,
    ADD COLUMN IF NOT EXISTS predictions          JSONB,
    ADD COLUMN IF NOT EXISTS blob_path            VARCHAR(500),
    ADD COLUMN IF NOT EXISTS training_duration_s  INTEGER,
    ADD COLUMN IF NOT EXISTS updated_at           TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_smr_user ON silver_model_registry(user_id);

COMMENT ON COLUMN silver_model_registry.user_id IS 'NULL = modelo del sistema. UUID = modelo custom del usuario.';
COMMENT ON COLUMN silver_model_registry.blob_path IS 'Ruta en Azure Blob Storage: system/aapl_lgbm_v1/model.pkl o users/{id}/{tk}/{name}/model.pkl';
COMMENT ON COLUMN silver_model_registry.predictions IS 'Señales del test period: [{ts, signal, price, score}]';
COMMENT ON COLUMN silver_model_registry.training_duration_s IS 'Duración del entrenamiento en segundos';


-- ─── 3. ALTER USER_PREFERENCES (+2 columnas) ─────────────────────────────

ALTER TABLE user_preferences
    ADD COLUMN IF NOT EXISTS models_config     JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS ticker_direction   JSONB DEFAULT '{}';

COMMENT ON COLUMN user_preferences.models_config IS 'Config modelos+pesos por ticker: {"AAPL": {"lgbm": 0.6, "aapl_lgbm_v2": 0.4}}';
COMMENT ON COLUMN user_preferences.ticker_direction IS 'Dirección por ticker: {"AAPL": "long", "TSLA": "short"}';


-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICACIÓN
-- ═══════════════════════════════════════════════════════════════════════════

-- backtest_runs: verificar las 8 columnas nuevas
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'backtest_runs'
    AND column_name IN ('ticker', 'direction', 'date_from', 'date_to',
                        'guardrails_config', 'models_config', 'models_enabled', 'equity_curve')
ORDER BY ordinal_position;

-- silver_model_registry: verificar las 10 columnas nuevas
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'silver_model_registry'
    AND column_name IN ('user_id', 'hyperparameters', 'train_from', 'train_to',
                        'test_from', 'test_to', 'predictions', 'blob_path',
                        'training_duration_s', 'updated_at')
ORDER BY ordinal_position;

-- user_preferences: verificar las 2 columnas nuevas
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'user_preferences'
    AND column_name IN ('models_config', 'ticker_direction')
ORDER BY ordinal_position;

-- Resumen de índices nuevos
SELECT indexname, tablename
FROM pg_indexes
WHERE indexname IN ('idx_bt_user_ticker', 'idx_smr_user')
ORDER BY tablename;
