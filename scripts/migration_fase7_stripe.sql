-- =============================================================================
-- Squawks ML — Fase 7: Stripe + Rate Limiting
-- migration_fase7_stripe.sql
-- =============================================================================
-- Ejecutar en Azure PostgreSQL (Supabase dashboard o psql).
-- Idempotente: se puede ejecutar varias veces sin error.
-- =============================================================================

-- ─── 7.1a: Fix plan names en users ──────────────────────────────────────────

-- Renombrar 'premium' → 'starter' (si existe algún usuario con ese plan)
UPDATE users SET plan = 'starter' WHERE plan = 'premium';

-- Eliminar el CHECK antiguo y crear el nuevo con los 5 tiers + admin
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_plan_check;
ALTER TABLE users ADD CONSTRAINT users_plan_check
    CHECK (plan IN ('trial', 'starter', 'pro', 'elite', 'enterprise', 'admin'));

-- Actualizar el comentario
COMMENT ON COLUMN users.plan IS
    'trial (14d gratis) → starter (9.99€/mes) → pro (29.99€/mes) → elite (WIP) → enterprise (WIP). admin = interno';

-- ─── 7.1b: Añadir stripe_customer_id a users ───────────────────────────────

ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_users_stripe_customer
    ON users(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- ─── 7.1c: Recrear tabla subscriptions (Stripe-focused) ────────────────────
-- La tabla original de Fase 4 era genérica. Esta es específica para Stripe.

DROP TABLE IF EXISTS subscriptions;

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_customer_id      VARCHAR(255) NOT NULL,
    stripe_subscription_id  VARCHAR(255) UNIQUE,
    plan                    VARCHAR(20) NOT NULL
                            CHECK (plan IN ('trial', 'starter', 'pro', 'elite', 'enterprise')),
    status                  VARCHAR(20) NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'past_due', 'canceled', 'trialing', 'incomplete')),
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user
    ON subscriptions(user_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_sub
    ON subscriptions(stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

COMMENT ON TABLE subscriptions IS
    'Suscripciones Stripe. 1 registro activo por usuario. Fuente de verdad = Stripe.';

-- ─── 7.1d: Crear tabla stripe_events (idempotencia webhooks) ────────────────

CREATE TABLE IF NOT EXISTS stripe_events (
    event_id        VARCHAR(255) PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,
    processed_at    TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE stripe_events IS
    'Idempotencia para webhooks de Stripe. Evita procesar el mismo evento 2 veces.';

-- ─── 7.1e: Fix plan CHECK en subscriptions antigua de plan_config ───────────
-- (plan_config ya tiene los 5 tiers correctos, no necesita cambios)

-- ─── Verificación final ─────────────────────────────────────────────────────

SELECT '✅ users.plan CHECK' AS check_name,
       pg_get_constraintdef(c.oid) AS constraint_def
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
WHERE t.relname = 'users' AND c.conname = 'users_plan_check';

SELECT '✅ users.stripe_customer_id' AS check_name,
       column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users' AND column_name = 'stripe_customer_id';

SELECT '✅ subscriptions', COUNT(*) FROM subscriptions;
SELECT '✅ stripe_events', COUNT(*) FROM stripe_events;

SELECT '🎉 Fase 7.1 completada' AS status;
