-- ════════════════════════════════════════════════════════════════════════════
-- migration_fase5_squawks.sql — Fase 5: Squawk engine
-- Fecha: 16 mayo 2026
-- Ejecutar en Azure PostgreSQL (Cloud Shell → psql).
-- Idempotente: se puede ejecutar varias veces sin romper nada.
-- ════════════════════════════════════════════════════════════════════════════


-- ─── 1. TABLA GOLD_SQUAWKS ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gold_squawks (
    -- Identidad
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker          VARCHAR(10) NOT NULL,

    -- Alerta
    squawk_type     VARCHAR(10) NOT NULL
                    CHECK (squawk_type IN ('BUY', 'SELL', 'HOLD', 'INFO', 'WARNING')),
    priority        VARCHAR(10) DEFAULT 'medium'
                    CHECK (priority IN ('high', 'medium', 'low')),
    score           NUMERIC(5,2),                -- Score del ensemble 0-100
    decision        VARCHAR(10),                 -- Decisión original del pipeline
    motivo          TEXT,                        -- Texto explicativo legible
    motivo_rechazo  VARCHAR(255),                -- Si fue HOLD, por qué

    -- Guardrails aplicados
    guardrails_passed   JSONB DEFAULT '{}',      -- {"score_minimo": true, "rsi": false, ...}
    guardrails_config   JSONB DEFAULT '{}',      -- Config del usuario que se usó

    -- Audio TTS (Fase 5.3)
    audio_url       VARCHAR(500),                -- URL al MP3 en Blob Storage
    audio_duration  INTEGER,                     -- Duración en segundos
    audio_locale    VARCHAR(10),                 -- Locale usado para generar (es-ES, en-US)

    -- Estado del usuario
    is_read         BOOLEAN DEFAULT false,
    is_dismissed    BOOLEAN DEFAULT false,
    is_starred      BOOLEAN DEFAULT false,       -- Favoritos

    -- Contexto de mercado (snapshot al momento del squawk)
    market_data     JSONB DEFAULT '{}',          -- {"rsi": 42, "macd_line": 0.5, "price": 185.2, ...}
    model_scores    JSONB DEFAULT '{}',          -- {"transformer": 72, "gru": 68, "lgbm": 81, ...}

    -- Tiempos
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '4 hours',
    read_at         TIMESTAMPTZ,
    dismissed_at    TIMESTAMPTZ,

    -- Referencia al pipeline
    run_id          VARCHAR(20),                 -- run_id del pipeline que lo generó
    decision_ts     TIMESTAMPTZ,                 -- ts de gold_decisions original

    -- Comodín
    metadata        JSONB DEFAULT '{}'
);

-- Índice principal: feed del usuario ordenado por fecha
CREATE INDEX IF NOT EXISTS idx_squawks_user_created
    ON gold_squawks(user_id, created_at DESC);

-- Filtrar squawks activos (no leídos, no descartados, no expirados)
CREATE INDEX IF NOT EXISTS idx_squawks_user_active
    ON gold_squawks(user_id, is_read, is_dismissed)
    WHERE is_read = false AND is_dismissed = false;

-- Buscar por ticker
CREATE INDEX IF NOT EXISTS idx_squawks_ticker
    ON gold_squawks(ticker, created_at DESC);

-- Buscar por prioridad (para push notifications)
CREATE INDEX IF NOT EXISTS idx_squawks_priority
    ON gold_squawks(priority, created_at DESC)
    WHERE priority = 'high';

-- Limpiar squawks expirados (job periódico)
CREATE INDEX IF NOT EXISTS idx_squawks_expires
    ON gold_squawks(expires_at)
    WHERE expires_at IS NOT NULL;


-- ─── 2. VERIFICACIÓN ───────────────────────────────────────────────────────

SELECT '✅ gold_squawks' AS tabla, COUNT(*) AS filas FROM gold_squawks
UNION ALL
SELECT '✅ índices', COUNT(*)::bigint
    FROM pg_indexes WHERE tablename = 'gold_squawks';


COMMENT ON TABLE gold_squawks IS 'Alertas de trading personalizadas por usuario. Generadas por el pipeline live.';
COMMENT ON COLUMN gold_squawks.expires_at IS 'Default 4h. Squawks viejos pierden relevancia.';
COMMENT ON COLUMN gold_squawks.audio_url IS 'Fase 5.3: URL al MP3 en Azure Blob Storage.';
COMMENT ON COLUMN gold_squawks.guardrails_passed IS 'Qué guardrails pasaron/fallaron con la config del usuario.';
