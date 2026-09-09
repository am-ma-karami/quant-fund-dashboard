-- Expand ETF market data models and add risk/data-quality fields

ALTER TABLE funds
    ADD COLUMN IF NOT EXISTS volatility FLOAT,
    ADD COLUMN IF NOT EXISTS sharpe_ratio FLOAT,
    ADD COLUMN IF NOT EXISTS max_drawdown FLOAT;

ALTER TABLE fund_histories
    ADD COLUMN IF NOT EXISTS nav_sub FLOAT,
    ADD COLUMN IF NOT EXISTS nav_red FLOAT,
    ADD COLUMN IF NOT EXISTS units FLOAT;

ALTER TABLE etf_market
    ADD COLUMN IF NOT EXISTS total_trades INTEGER,
    ADD COLUMN IF NOT EXISTS total_volume FLOAT,
    ADD COLUMN IF NOT EXISTS total_value FLOAT,
    ADD COLUMN IF NOT EXISTS price_min FLOAT,
    ADD COLUMN IF NOT EXISTS price_max FLOAT,
    ADD COLUMN IF NOT EXISTS price_first FLOAT,
    ADD COLUMN IF NOT EXISTS price_yesterday FLOAT,
    ADD COLUMN IF NOT EXISTS nav FLOAT,
    ADD COLUMN IF NOT EXISTS nav_red FLOAT,
    ADD COLUMN IF NOT EXISTS nav_sub FLOAT,
    ADD COLUMN IF NOT EXISTS premium_discount FLOAT,
    ADD COLUMN IF NOT EXISTS volatility FLOAT,
    ADD COLUMN IF NOT EXISTS sharpe_ratio FLOAT,
    ADD COLUMN IF NOT EXISTS max_drawdown FLOAT;

ALTER TABLE etf_market_histories
    ADD COLUMN IF NOT EXISTS price_change FLOAT,
    ADD COLUMN IF NOT EXISTS total_trades INTEGER,
    ADD COLUMN IF NOT EXISTS total_volume FLOAT,
    ADD COLUMN IF NOT EXISTS total_value FLOAT,
    ADD COLUMN IF NOT EXISTS price_min FLOAT,
    ADD COLUMN IF NOT EXISTS price_max FLOAT,
    ADD COLUMN IF NOT EXISTS price_first FLOAT,
    ADD COLUMN IF NOT EXISTS price_yesterday FLOAT,
    ADD COLUMN IF NOT EXISTS nav FLOAT,
    ADD COLUMN IF NOT EXISTS nav_red FLOAT,
    ADD COLUMN IF NOT EXISTS nav_sub FLOAT,
    ADD COLUMN IF NOT EXISTS premium_discount FLOAT;

CREATE UNIQUE INDEX IF NOT EXISTS uix_etf_observation
    ON etf_market_histories (ins_code, observed_at);

ALTER TABLE sync_status
    ADD COLUMN IF NOT EXISTS expected_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS received_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS valid_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
    ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS provider VARCHAR(50) DEFAULT 'TSETMC';

CREATE INDEX IF NOT EXISTS idx_etf_market_histories_ins_code_observed_at
    ON etf_market_histories (ins_code, observed_at);
