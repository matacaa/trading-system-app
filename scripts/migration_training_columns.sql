-- ════════════════════════════════════════════════════════════════════════════
-- migration_training_columns.sql — Añadir columns y context_tickers a training_jobs
-- Fecha: 22 mayo 2026
-- Ejecutar DESPUÉS de migration_fase6_tables.sql.
-- Idempotente: usa IF NOT EXISTS.
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE training_jobs
    ADD COLUMN IF NOT EXISTS columns          JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS context_tickers  JSONB DEFAULT '[]';

COMMENT ON COLUMN training_jobs.columns IS 'Features seleccionadas para el entrenamiento (lista de strings)';
COMMENT ON COLUMN training_jobs.context_tickers IS 'Tickers de contexto cuyas features se incluyen como correlación';

-- Verificación
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'training_jobs'
    AND column_name IN ('columns', 'context_tickers')
ORDER BY ordinal_position;
