-- ════════════════════════════════════════════════════════════════════════════
-- migration_fase6_tables.sql — Fase 6: Backend completo
-- Fecha: 20 mayo 2026
-- Ejecutar en Azure PostgreSQL (Cloud Shell → psql).
-- Idempotente: se puede ejecutar varias veces sin romper nada.
--
-- 6 tablas nuevas:
--   1. ticker_universe        — Catálogo 500 tickers
--   2. guardrail_registry     — Metadatos 14 guardrails
--   3. plan_config            — Límites por plan
--   4. training_jobs          — Cola de entrenamiento
--   5. model_type_registry    — 6 tipos de modelo
--   6. user_credits           — Créditos extra de packs
-- ════════════════════════════════════════════════════════════════════════════


-- ─── 1. TICKER_UNIVERSE ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ticker_universe (
    ticker          VARCHAR(10) PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    sector          VARCHAR(50) NOT NULL,
    exchange        VARCHAR(20) NOT NULL,
    model_coverage  VARCHAR(20) NOT NULL DEFAULT 'none'
                    CHECK (model_coverage IN ('ml', 'rules_only', 'none')),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tu_sector ON ticker_universe(sector);
CREATE INDEX IF NOT EXISTS idx_tu_active ON ticker_universe(is_active) WHERE is_active = true;

COMMENT ON TABLE ticker_universe IS 'Catálogo de ~500 tickers US. Seed inicial + ampliable.';
COMMENT ON COLUMN ticker_universe.model_coverage IS 'ml = modelos sistema entrenados, rules_only = solo señales técnicas, none = sin cobertura aún.';


-- ─── 2. GUARDRAIL_REGISTRY ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS guardrail_registry (
    name            VARCHAR(50) PRIMARY KEY,
    label           VARCHAR(100) NOT NULL,
    category        VARCHAR(20) NOT NULL
                    CHECK (category IN ('básico', 'técnico', 'riesgo')),
    phase           VARCHAR(10) NOT NULL
                    CHECK (phase IN ('pre', 'post')),
    description     TEXT,
    params_schema   JSONB,
    is_active       BOOLEAN NOT NULL DEFAULT true
);

COMMENT ON TABLE guardrail_registry IS '14 guardrails con metadatos. Consumida por pestaña Backtest para renderizar sliders dinámicamente.';
COMMENT ON COLUMN guardrail_registry.params_schema IS 'Array de {key, label, type, min, max, default, step} para generar UI dinámica.';


-- ─── 3. PLAN_CONFIG ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS plan_config (
    plan                    VARCHAR(20) PRIMARY KEY,
    guardrails_available    JSONB NOT NULL,
    max_models              INTEGER NOT NULL,
    max_hist_days           INTEGER NOT NULL,
    max_backtests_month     INTEGER NOT NULL,
    max_backtests_saved     INTEGER NOT NULL,
    max_trainings_month     INTEGER NOT NULL,
    max_training_days       INTEGER NOT NULL,
    max_custom_models       INTEGER NOT NULL,
    max_tickers             INTEGER NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE plan_config IS 'Límites por plan. Customizable sin deploy. Cacheable en memoria con TTL 5 min.';


-- ─── 4. TRAINING_JOBS ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS training_jobs (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_name          VARCHAR(255) NOT NULL,
    model_type          VARCHAR(30) NOT NULL,
    ticker              VARCHAR(10) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    progress_pct        INTEGER NOT NULL DEFAULT 0
                        CHECK (progress_pct BETWEEN 0 AND 100),
    train_from          DATE NOT NULL,
    train_to            DATE NOT NULL,
    test_from           DATE NOT NULL,
    test_to             DATE NOT NULL,
    hyperparameters     JSONB NOT NULL DEFAULT '{}',
    metrics             JSONB,
    error               TEXT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tj_user ON training_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tj_status ON training_jobs(status);

COMMENT ON TABLE training_jobs IS 'Cola de trabajos de entrenamiento. Polling de progreso desde pestaña Training.';


-- ─── 5. MODEL_TYPE_REGISTRY ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS model_type_registry (
    type_id         VARCHAR(30) PRIMARY KEY,
    label           VARCHAR(100) NOT NULL,
    category        VARCHAR(30) NOT NULL
                    CHECK (category IN ('gradient_boosting', 'ensemble', 'deep_learning')),
    params_schema   JSONB NOT NULL,
    is_available    BOOLEAN NOT NULL DEFAULT true
);

COMMENT ON TABLE model_type_registry IS '6 tipos de modelo con hiperparámetros. Formulario dinámico en pestaña Training.';


-- ─── 6. USER_CREDITS ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_credits (
    user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    extra_backtests     INTEGER NOT NULL DEFAULT 0,
    extra_trainings     INTEGER NOT NULL DEFAULT 0,
    extra_tickers       JSONB NOT NULL DEFAULT '[]',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE user_credits IS 'Créditos extra de packs comprados via Stripe. Se decrementan al usar.';
COMMENT ON COLUMN user_credits.extra_tickers IS 'Array de {ticker, expires_at}. Ticker extra válido 1 mes.';


-- ═══════════════════════════════════════════════════════════════════════════
-- SEEDS
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── SEED: guardrail_registry (14 guardrails) ────────────────────────────

INSERT INTO guardrail_registry (name, label, category, phase, description, params_schema) VALUES
('horario_mercado',   'Horario de mercado',   'básico',   'pre',  'Solo opera durante horario regular de mercado (9:30-16:00 ET).',
    '[]'),
('posicion_abierta',  'Posición abierta',     'básico',   'pre',  'Bloquea compra si ya hay posición abierta en el ticker.',
    '[]'),
('rsi',               'RSI',                  'básico',   'pre',  'Bloquea si RSI está en sobrecompra/sobreventa según umbral.',
    '[{"key":"compra_max","label":"RSI máx compra","type":"number","min":50,"max":95,"default":70,"step":5},{"key":"venta_min","label":"RSI mín venta","type":"number","min":5,"max":50,"default":30,"step":5}]'),
('macd',              'MACD',                 'básico',   'pre',  'Requiere MACD alcista para compra, bajista para venta.',
    '[]'),
('bollinger',         'Bollinger Bands',      'básico',   'pre',  'Bloquea si precio está por encima del %B máximo.',
    '[{"key":"compra_max","label":"Máx %B compra","type":"number","min":0.5,"max":1.0,"default":0.95,"step":0.05}]'),
('volumen',           'Volumen mínimo',       'básico',   'pre',  'Requiere volumen normalizado por encima del mínimo.',
    '[{"key":"min_volume_norm","label":"Volumen mín normalizado","type":"number","min":0.1,"max":2.0,"default":0.5,"step":0.1}]'),
('ema_tendencia',     'EMA Tendencia',        'básico',   'pre',  'Requiere alineación de EMAs para confirmar tendencia.',
    '[]'),
('atr_volatilidad',   'ATR Volatilidad',      'técnico',  'pre',  'Bloquea si ATR como porcentaje del precio supera el máximo.',
    '[{"key":"max_atr_pct","label":"Máx ATR %","type":"number","min":0.5,"max":5.0,"default":2.0,"step":0.5}]'),
('vwap_spread',       'VWAP Spread',          'técnico',  'pre',  'Bloquea si el spread entre precio y VWAP es excesivo.',
    '[{"key":"max_spread_pct","label":"Máx spread %","type":"number","min":0.5,"max":5.0,"default":2.0,"step":0.5}]'),
('sentiment',         'Sentiment',            'técnico',  'pre',  'Requiere sentiment de noticias por encima del mínimo.',
    '[{"key":"min_score","label":"Sentiment mín","type":"number","min":-1.0,"max":1.0,"default":0,"step":0.1}]'),
('max_posiciones',    'Máx posiciones',       'técnico',  'pre',  'Limita el número total de posiciones abiertas simultáneas.',
    '[{"key":"valor","label":"Máx posiciones","type":"integer","min":1,"max":20,"default":3,"step":1}]'),
('ordenes_diarias_max','Órdenes diarias máx', 'riesgo',   'pre',  'Limita el número de órdenes ejecutadas por día.',
    '[{"key":"valor","label":"Máx órdenes/día","type":"integer","min":1,"max":50,"default":5,"step":1}]'),
('circuit_breaker',   'Circuit Breaker',      'riesgo',   'pre',  'Detiene operaciones si se detecta caída brusca en el mercado.',
    '[]'),
('score_minimo',      'Score mínimo',         'básico',   'post', 'Requiere que el score final del usuario supere un umbral.',
    '[{"key":"valor","label":"Score mínimo","type":"number","min":30,"max":95,"default":65,"step":5}]')
ON CONFLICT (name) DO NOTHING;


-- ─── SEED: plan_config (5 planes) ────────────────────────────────────────

INSERT INTO plan_config (plan, guardrails_available, max_models, max_hist_days, max_backtests_month, max_backtests_saved, max_trainings_month, max_training_days, max_custom_models, max_tickers) VALUES
('trial',       '["horario_mercado","posicion_abierta","rsi","macd","bollinger","volumen","ema_tendencia","score_minimo"]',
                1, 14, 5, 5, 0, 0, 0, 1),
('starter',     '["horario_mercado","posicion_abierta","rsi","macd","bollinger","volumen","ema_tendencia","score_minimo","atr_volatilidad","vwap_spread","sentiment","max_posiciones"]',
                3, 90, 20, 10, 5, 7, 3, 3),
('pro',         '"*"',
                6, 365, 50, 30, 20, 90, 12, 10),
('elite',       '"*"',
                6, 1095, 150, 100, 50, 730, 30, 50),
('enterprise',  '"*"',
                6, 9999, 400, 500, 150, 9999, 999, 999)
ON CONFLICT (plan) DO NOTHING;


-- ─── SEED: model_type_registry (6 tipos) ─────────────────────────────────

INSERT INTO model_type_registry (type_id, label, category, params_schema) VALUES
('lightgbm', 'LightGBM', 'gradient_boosting',
    '[{"key":"n_estimators","label":"Árboles","type":"integer","default":200,"min":50,"max":1000,"step":50},{"key":"max_depth","label":"Profundidad","type":"integer","default":6,"min":2,"max":15,"step":1},{"key":"learning_rate","label":"Learning rate","type":"number","default":0.05,"min":0.001,"max":0.3,"step":0.01},{"key":"num_leaves","label":"Hojas","type":"integer","default":31,"min":8,"max":128,"step":1}]'),
('xgboost', 'XGBoost', 'gradient_boosting',
    '[{"key":"n_estimators","label":"Árboles","type":"integer","default":200,"min":50,"max":1000,"step":50},{"key":"max_depth","label":"Profundidad","type":"integer","default":6,"min":2,"max":15,"step":1},{"key":"learning_rate","label":"Learning rate","type":"number","default":0.05,"min":0.001,"max":0.3,"step":0.01},{"key":"min_child_weight","label":"Min child weight","type":"integer","default":1,"min":1,"max":10,"step":1}]'),
('random_forest', 'Random Forest', 'ensemble',
    '[{"key":"n_estimators","label":"Árboles","type":"integer","default":200,"min":50,"max":1000,"step":50},{"key":"max_depth","label":"Profundidad","type":"integer","default":10,"min":2,"max":30,"step":1},{"key":"min_samples_split","label":"Min samples split","type":"integer","default":5,"min":2,"max":20,"step":1}]'),
('transformer', 'Transformer', 'deep_learning',
    '[{"key":"d_model","label":"Dimensión modelo","type":"integer","default":64,"min":16,"max":256,"step":16},{"key":"n_heads","label":"Attention heads","type":"integer","default":4,"min":1,"max":8,"step":1},{"key":"n_layers","label":"Capas","type":"integer","default":2,"min":1,"max":6,"step":1},{"key":"epochs","label":"Épocas","type":"integer","default":50,"min":10,"max":200,"step":10},{"key":"lr","label":"Learning rate","type":"number","default":0.001,"min":0.0001,"max":0.01,"step":0.0001}]'),
('gru', 'GRU', 'deep_learning',
    '[{"key":"hidden_size","label":"Hidden size","type":"integer","default":64,"min":16,"max":256,"step":16},{"key":"n_layers","label":"Capas","type":"integer","default":2,"min":1,"max":4,"step":1},{"key":"epochs","label":"Épocas","type":"integer","default":50,"min":10,"max":200,"step":10},{"key":"lr","label":"Learning rate","type":"number","default":0.001,"min":0.0001,"max":0.01,"step":0.0001},{"key":"dropout","label":"Dropout","type":"number","default":0.2,"min":0.0,"max":0.5,"step":0.05}]'),
('lstm', 'LSTM', 'deep_learning',
    '[{"key":"hidden_size","label":"Hidden size","type":"integer","default":64,"min":16,"max":256,"step":16},{"key":"n_layers","label":"Capas","type":"integer","default":2,"min":1,"max":4,"step":1},{"key":"epochs","label":"Épocas","type":"integer","default":50,"min":10,"max":200,"step":10},{"key":"lr","label":"Learning rate","type":"number","default":0.001,"min":0.0001,"max":0.01,"step":0.0001},{"key":"dropout","label":"Dropout","type":"number","default":0.2,"min":0.0,"max":0.5,"step":0.05}]')
ON CONFLICT (type_id) DO NOTHING;


-- ─── SEED: ticker_universe (~100 tickers principales + expansión) ─────────
-- Seed inicial con los tickers más relevantes de NASDAQ/NYSE.
-- Los 500 restantes se pueden añadir incrementalmente con INSERT.

INSERT INTO ticker_universe (ticker, name, sector, exchange, model_coverage) VALUES
-- Technology
('AAPL',  'Apple Inc.',                       'Technology', 'NASDAQ', 'ml'),
('MSFT',  'Microsoft Corp.',                  'Technology', 'NASDAQ', 'rules_only'),
('NVDA',  'NVIDIA Corp.',                     'Technology', 'NASDAQ', 'rules_only'),
('GOOGL', 'Alphabet Inc. (Class A)',           'Technology', 'NASDAQ', 'rules_only'),
('META',  'Meta Platforms Inc.',               'Technology', 'NASDAQ', 'rules_only'),
('AMZN',  'Amazon.com Inc.',                   'Technology', 'NASDAQ', 'rules_only'),
('TSLA',  'Tesla Inc.',                        'Technology', 'NASDAQ', 'rules_only'),
('AVGO',  'Broadcom Inc.',                     'Technology', 'NASDAQ', 'rules_only'),
('ORCL',  'Oracle Corp.',                      'Technology', 'NYSE',   'rules_only'),
('CRM',   'Salesforce Inc.',                   'Technology', 'NYSE',   'rules_only'),
('AMD',   'Advanced Micro Devices Inc.',       'Technology', 'NASDAQ', 'rules_only'),
('ADBE',  'Adobe Inc.',                        'Technology', 'NASDAQ', 'rules_only'),
('INTC',  'Intel Corp.',                       'Technology', 'NASDAQ', 'rules_only'),
('CSCO',  'Cisco Systems Inc.',                'Technology', 'NASDAQ', 'rules_only'),
('QCOM',  'Qualcomm Inc.',                     'Technology', 'NASDAQ', 'rules_only'),
('TXN',   'Texas Instruments Inc.',            'Technology', 'NASDAQ', 'rules_only'),
('NFLX',  'Netflix Inc.',                      'Technology', 'NASDAQ', 'rules_only'),
('UBER',  'Uber Technologies Inc.',            'Technology', 'NYSE',   'rules_only'),
('SHOP',  'Shopify Inc.',                      'Technology', 'NYSE',   'rules_only'),
('NOW',   'ServiceNow Inc.',                   'Technology', 'NYSE',   'rules_only'),
('SNOW',  'Snowflake Inc.',                    'Technology', 'NYSE',   'rules_only'),
('PLTR',  'Palantir Technologies Inc.',        'Technology', 'NYSE',   'rules_only'),
('NET',   'Cloudflare Inc.',                   'Technology', 'NYSE',   'rules_only'),
('PANW',  'Palo Alto Networks Inc.',           'Technology', 'NASDAQ', 'rules_only'),
('CRWD',  'CrowdStrike Holdings Inc.',         'Technology', 'NASDAQ', 'rules_only'),
-- Finance
('JPM',   'JPMorgan Chase & Co.',              'Finance',    'NYSE',   'rules_only'),
('V',     'Visa Inc.',                         'Finance',    'NYSE',   'rules_only'),
('MA',    'Mastercard Inc.',                   'Finance',    'NYSE',   'rules_only'),
('BAC',   'Bank of America Corp.',             'Finance',    'NYSE',   'rules_only'),
('WFC',   'Wells Fargo & Co.',                 'Finance',    'NYSE',   'rules_only'),
('GS',    'Goldman Sachs Group Inc.',           'Finance',    'NYSE',   'rules_only'),
('MS',    'Morgan Stanley',                    'Finance',    'NYSE',   'rules_only'),
('AXP',   'American Express Co.',              'Finance',    'NYSE',   'rules_only'),
('BLK',   'BlackRock Inc.',                    'Finance',    'NYSE',   'rules_only'),
('SCHW',  'Charles Schwab Corp.',              'Finance',    'NYSE',   'rules_only'),
('C',     'Citigroup Inc.',                    'Finance',    'NYSE',   'rules_only'),
('PYPL',  'PayPal Holdings Inc.',              'Finance',    'NASDAQ', 'rules_only'),
('SQ',    'Block Inc.',                        'Finance',    'NYSE',   'rules_only'),
('COIN',  'Coinbase Global Inc.',              'Finance',    'NASDAQ', 'rules_only'),
('SOFI',  'SoFi Technologies Inc.',            'Finance',    'NASDAQ', 'rules_only'),
-- Healthcare
('UNH',   'UnitedHealth Group Inc.',           'Healthcare', 'NYSE',   'rules_only'),
('JNJ',   'Johnson & Johnson',                'Healthcare', 'NYSE',   'rules_only'),
('LLY',   'Eli Lilly and Co.',                'Healthcare', 'NYSE',   'rules_only'),
('ABBV',  'AbbVie Inc.',                       'Healthcare', 'NYSE',   'rules_only'),
('MRK',   'Merck & Co. Inc.',                 'Healthcare', 'NYSE',   'rules_only'),
('PFE',   'Pfizer Inc.',                       'Healthcare', 'NYSE',   'rules_only'),
('TMO',   'Thermo Fisher Scientific Inc.',     'Healthcare', 'NYSE',   'rules_only'),
('ABT',   'Abbott Laboratories',               'Healthcare', 'NYSE',   'rules_only'),
('BMY',   'Bristol-Myers Squibb Co.',          'Healthcare', 'NYSE',   'rules_only'),
('MRNA',  'Moderna Inc.',                      'Healthcare', 'NASDAQ', 'rules_only'),
-- Consumer
('WMT',   'Walmart Inc.',                     'Consumer',   'NYSE',   'rules_only'),
('PG',    'Procter & Gamble Co.',              'Consumer',   'NYSE',   'rules_only'),
('KO',    'Coca-Cola Co.',                     'Consumer',   'NYSE',   'rules_only'),
('PEP',   'PepsiCo Inc.',                     'Consumer',   'NYSE',   'rules_only'),
('COST',  'Costco Wholesale Corp.',            'Consumer',   'NASDAQ', 'rules_only'),
('MCD',   'McDonald''s Corp.',                 'Consumer',   'NYSE',   'rules_only'),
('NKE',   'Nike Inc.',                         'Consumer',   'NYSE',   'rules_only'),
('SBUX',  'Starbucks Corp.',                   'Consumer',   'NASDAQ', 'rules_only'),
('TGT',   'Target Corp.',                      'Consumer',   'NYSE',   'rules_only'),
('HD',    'Home Depot Inc.',                   'Consumer',   'NYSE',   'rules_only'),
('LOW',   'Lowe''s Companies Inc.',            'Consumer',   'NYSE',   'rules_only'),
-- Energy
('XOM',   'Exxon Mobil Corp.',                 'Energy',     'NYSE',   'rules_only'),
('CVX',   'Chevron Corp.',                     'Energy',     'NYSE',   'rules_only'),
('COP',   'ConocoPhillips',                    'Energy',     'NYSE',   'rules_only'),
('SLB',   'Schlumberger N.V.',                 'Energy',     'NYSE',   'rules_only'),
('EOG',   'EOG Resources Inc.',                'Energy',     'NYSE',   'rules_only'),
-- Industrial
('CAT',   'Caterpillar Inc.',                  'Industrial', 'NYSE',   'rules_only'),
('BA',    'Boeing Co.',                        'Industrial', 'NYSE',   'rules_only'),
('HON',   'Honeywell International Inc.',      'Industrial', 'NASDAQ', 'rules_only'),
('UPS',   'United Parcel Service Inc.',        'Industrial', 'NYSE',   'rules_only'),
('RTX',   'RTX Corp.',                         'Industrial', 'NYSE',   'rules_only'),
('GE',    'GE Aerospace',                      'Industrial', 'NYSE',   'rules_only'),
('DE',    'Deere & Co.',                       'Industrial', 'NYSE',   'rules_only'),
('LMT',   'Lockheed Martin Corp.',             'Industrial', 'NYSE',   'rules_only'),
-- Communication
('DIS',   'Walt Disney Co.',                   'Communication', 'NYSE',   'rules_only'),
('CMCSA', 'Comcast Corp.',                     'Communication', 'NASDAQ', 'rules_only'),
('T',     'AT&T Inc.',                         'Communication', 'NYSE',   'rules_only'),
('VZ',    'Verizon Communications Inc.',       'Communication', 'NYSE',   'rules_only'),
('TMUS',  'T-Mobile US Inc.',                  'Communication', 'NASDAQ', 'rules_only'),
-- Real Estate
('AMT',   'American Tower Corp.',              'Real Estate', 'NYSE',   'rules_only'),
('PLD',   'Prologis Inc.',                     'Real Estate', 'NYSE',   'rules_only'),
('CCI',   'Crown Castle Inc.',                 'Real Estate', 'NYSE',   'rules_only'),
-- Materials
('LIN',   'Linde plc',                         'Materials',  'NASDAQ', 'rules_only'),
('APD',   'Air Products & Chemicals Inc.',     'Materials',  'NYSE',   'rules_only'),
('FCX',   'Freeport-McMoRan Inc.',             'Materials',  'NYSE',   'rules_only'),
-- Utilities
('NEE',   'NextEra Energy Inc.',               'Utilities',  'NYSE',   'rules_only'),
('DUK',   'Duke Energy Corp.',                 'Utilities',  'NYSE',   'rules_only'),
('SO',    'Southern Co.',                      'Utilities',  'NYSE',   'rules_only'),
-- Crypto-adjacent / Fintech
('MSTR',  'MicroStrategy Inc.',                'Technology', 'NASDAQ', 'rules_only'),
('MARA',  'Marathon Digital Holdings Inc.',     'Technology', 'NASDAQ', 'rules_only'),
('RIOT',  'Riot Platforms Inc.',                'Technology', 'NASDAQ', 'rules_only'),
-- Semiconductors
('MU',    'Micron Technology Inc.',             'Technology', 'NASDAQ', 'rules_only'),
('AMAT',  'Applied Materials Inc.',             'Technology', 'NASDAQ', 'rules_only'),
('LRCX',  'Lam Research Corp.',                'Technology', 'NASDAQ', 'rules_only'),
('KLAC',  'KLA Corp.',                         'Technology', 'NASDAQ', 'rules_only'),
('MRVL',  'Marvell Technology Inc.',            'Technology', 'NASDAQ', 'rules_only'),
('ARM',   'Arm Holdings plc',                  'Technology', 'NASDAQ', 'rules_only'),
('SMCI',  'Super Micro Computer Inc.',          'Technology', 'NASDAQ', 'rules_only'),
-- High-growth / Meme
('RIVN',  'Rivian Automotive Inc.',             'Consumer',   'NASDAQ', 'rules_only'),
('LCID',  'Lucid Group Inc.',                   'Consumer',   'NASDAQ', 'rules_only'),
('GME',   'GameStop Corp.',                     'Consumer',   'NYSE',   'rules_only'),
('AMC',   'AMC Entertainment Holdings Inc.',    'Communication', 'NYSE', 'rules_only'),
('HOOD',  'Robinhood Markets Inc.',             'Finance',    'NASDAQ', 'rules_only')
ON CONFLICT (ticker) DO NOTHING;


-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICACIÓN
-- ═══════════════════════════════════════════════════════════════════════════

SELECT '✅ ticker_universe' AS tabla, COUNT(*) AS filas FROM ticker_universe
UNION ALL
SELECT '✅ guardrail_registry', COUNT(*) FROM guardrail_registry
UNION ALL
SELECT '✅ plan_config', COUNT(*) FROM plan_config
UNION ALL
SELECT '✅ training_jobs', COUNT(*) FROM training_jobs
UNION ALL
SELECT '✅ model_type_registry', COUNT(*) FROM model_type_registry
UNION ALL
SELECT '✅ user_credits', COUNT(*) FROM user_credits;

SELECT
    (SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'ticker_universe') AS idx_ticker_universe,
    (SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'training_jobs') AS idx_training_jobs;
