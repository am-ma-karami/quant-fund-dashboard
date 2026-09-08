CREATE INDEX IF NOT EXISTS
idx_fund_histories_reg_no_observed_at
ON fund_histories (fund_reg_no, observed_at);

CREATE INDEX IF NOT EXISTS
idx_funds_type_day30_return
ON funds (fund_type, day30_return DESC);

CREATE INDEX IF NOT EXISTS
idx_funds_net_asset_day30_return
ON funds (net_asset DESC, day30_return);

CREATE INDEX IF NOT EXISTS
idx_etf_market_total_trades
ON etf_market (total_trades DESC);