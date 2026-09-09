CREATE TABLE IF NOT EXISTS history_backfill_state (
    fund_reg_no INTEGER PRIMARY KEY REFERENCES funds(reg_no),
    checked_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_history_backfill_state_checked_at
    ON history_backfill_state (checked_at);
