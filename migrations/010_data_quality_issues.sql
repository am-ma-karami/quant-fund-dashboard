-- تخلف‌های کیفیت داده (لایه اعتبارسنجی — services/validation.py)
CREATE TABLE IF NOT EXISTS data_quality_issues (
    id SERIAL PRIMARY KEY,
    fund_reg_no INTEGER NOT NULL REFERENCES funds(reg_no),
    rule VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'warning',
    detail VARCHAR(512),
    observed_at TIMESTAMP NOT NULL,
    detected_at TIMESTAMP DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_quality_issue
    ON data_quality_issues (fund_reg_no, rule, observed_at);

CREATE INDEX IF NOT EXISTS ix_data_quality_issues_severity
    ON data_quality_issues (severity);
