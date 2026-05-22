-- ════════════════════════════════════════════════════════════════════════════
-- migration_email_verification.sql — Tabla de tokens de verificación de email
-- Idempotente: se puede ejecutar varias veces sin romper nada.
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       VARCHAR(128) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evt_token ON email_verification_tokens(token);
CREATE INDEX IF NOT EXISTS idx_evt_user ON email_verification_tokens(user_id);

COMMENT ON TABLE email_verification_tokens IS 'Tokens de un solo uso para verificar email tras registro';

-- Verificación
SELECT '✅ email_verification_tokens' AS tabla, COUNT(*) AS filas FROM email_verification_tokens;
