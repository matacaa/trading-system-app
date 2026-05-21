-- ════════════════════════════════════════════════════════════════════════════
-- migration_fase4_auth.sql — Fase 4: Auth + multi-tenant
-- Fecha: 16 mayo 2026
-- Ejecutar en Azure PostgreSQL (pgAdmin o psql).
-- Idempotente: se puede ejecutar varias veces sin romper nada.
-- ════════════════════════════════════════════════════════════════════════════


-- ─── 1. TABLA USERS ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    -- Identidad
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email             VARCHAR(255) UNIQUE NOT NULL,
    password_hash     VARCHAR(255) NOT NULL,
    display_name      VARCHAR(100),
    avatar_url        VARCHAR(500),
    phone             VARCHAR(20),

    -- Localización
    country           VARCHAR(3),              -- ISO 3166-1 alpha-3: ESP, USA, GBR
    locale            VARCHAR(10) DEFAULT 'es',
    timezone          VARCHAR(50) DEFAULT 'Europe/Madrid',

    -- Plan y estado
    plan              VARCHAR(20) DEFAULT 'trial'
                      CHECK (plan IN ('trial', 'premium', 'pro', 'admin')),
    trial_end         TIMESTAMPTZ DEFAULT NOW() + INTERVAL '14 days',
    is_active         BOOLEAN DEFAULT true,
    email_verified    BOOLEAN DEFAULT false,
    last_login_at     TIMESTAMPTZ,

    -- Referidos
    referral_code     VARCHAR(20) UNIQUE,
    referred_by       UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Auditoría
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    -- Comodín
    metadata          JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

COMMENT ON TABLE users IS 'Usuarios registrados en Squawks ML';
COMMENT ON COLUMN users.plan IS 'trial (14d gratis) → premium (14.99€/mes) → pro (39.99€/mes). admin = interno';
COMMENT ON COLUMN users.metadata IS 'Comodín JSONB para campos futuros sin ALTER TABLE';


-- ─── 2. TABLA SUBSCRIPTIONS ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Qué compró
    plan                    VARCHAR(20) NOT NULL
                            CHECK (plan IN ('trial', 'premium', 'pro')),
    payment_provider        VARCHAR(20)
                            CHECK (payment_provider IN ('stripe', 'apple', 'google', 'revenucat', 'manual')),
    interval                VARCHAR(20)
                            CHECK (interval IN ('monthly', 'yearly')),
    currency                VARCHAR(3) DEFAULT 'EUR',
    amount_cents            INTEGER,             -- 1499 = 14.99€

    -- Estado
    status                  VARCHAR(20) DEFAULT 'active'
                            CHECK (status IN ('active', 'cancelled', 'expired', 'past_due', 'trialing')),
    auto_renew              BOOLEAN DEFAULT true,
    trial_used              BOOLEAN DEFAULT false,

    -- Fechas
    started_at              TIMESTAMPTZ DEFAULT NOW(),
    expires_at              TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ,
    cancellation_reason     VARCHAR(255),

    -- IDs de proveedores de pago (se rellenan en Fase 7)
    stripe_customer_id      VARCHAR(255),
    stripe_subscription_id  VARCHAR(255),
    revenucat_app_user_id   VARCHAR(255),
    apple_transaction_id    VARCHAR(255),
    google_purchase_token   VARCHAR(255),

    -- Auditoría
    created_at              TIMESTAMPTZ DEFAULT NOW(),

    -- Comodín
    metadata                JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);

COMMENT ON TABLE subscriptions IS 'Historial de suscripciones. 1 registro por cambio de plan. Vacía hasta Fase 7';


-- ─── 3. TABLA USER_PREFERENCES ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_preferences (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,

    -- Tickers y señales
    tickers                 JSONB DEFAULT '["AAPL"]',
    signal_configs          JSONB DEFAULT '{}',
    guardrail_overrides     JSONB DEFAULT '{}',

    -- Notificaciones
    notification_prefs      JSONB DEFAULT '{"push": true, "audio": false, "urgent_only": false}',
    sound_enabled           BOOLEAN DEFAULT true,
    email_digest            VARCHAR(10) DEFAULT 'daily'
                            CHECK (email_digest IN ('daily', 'weekly', 'none')),

    -- UI
    theme                   VARCHAR(10) DEFAULT 'dark'
                            CHECK (theme IN ('dark', 'light', 'auto')),
    language                VARCHAR(5) DEFAULT 'es',
    onboarding_completed    BOOLEAN DEFAULT false,

    -- Defaults para backtest/training
    risk_profile            VARCHAR(20) DEFAULT 'moderate'
                            CHECK (risk_profile IN ('conservative', 'moderate', 'aggressive')),
    default_capital         INTEGER DEFAULT 100000,
    default_timeframe       VARCHAR(5) DEFAULT '1m',
    max_tickers             INTEGER DEFAULT 5,

    -- Auditoría
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    -- Comodín
    metadata                JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_user_prefs_user ON user_preferences(user_id);

COMMENT ON TABLE user_preferences IS '1 registro por usuario. Se crea en /auth/register';
COMMENT ON COLUMN user_preferences.guardrail_overrides IS 'Fase 6: config por ticker {"AAPL":{"score_minimo":70},"TSLA":{"rsi":{"compra_max":65}}}';


-- ─── 4. ALTER TABLE BACKTEST_RUNS ──────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_runs' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE backtest_runs
            ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_backtest_runs_user ON backtest_runs(user_id);

COMMENT ON COLUMN backtest_runs.user_id IS 'NULL = backtest legacy (pre-auth). Nuevos siempre tienen user_id';


-- ─── 5. FUNCIÓN HELPER: ACTUALIZAR updated_at AUTOMÁTICAMENTE ─────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger en users
DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Trigger en user_preferences
DROP TRIGGER IF EXISTS trg_user_prefs_updated_at ON user_preferences;
CREATE TRIGGER trg_user_prefs_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ─── 6. VERIFICACIÓN ───────────────────────────────────────────────────────

SELECT '✅ users' AS tabla, COUNT(*) AS filas FROM users
UNION ALL
SELECT '✅ subscriptions', COUNT(*) FROM subscriptions
UNION ALL
SELECT '✅ user_preferences', COUNT(*) FROM user_preferences
UNION ALL
SELECT '✅ backtest_runs.user_id existe',
    CASE WHEN EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_runs' AND column_name = 'user_id'
    ) THEN 1 ELSE 0 END
UNION ALL
SELECT '✅ triggers', COUNT(*)::bigint FROM information_schema.triggers
    WHERE trigger_name LIKE 'trg_%_updated_at';
