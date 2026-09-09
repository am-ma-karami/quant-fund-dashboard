CREATE TABLE IF NOT EXISTS benchmark_histories (
    id SERIAL PRIMARY KEY,
    benchmark_code VARCHAR(32) NOT NULL,
    benchmark_name VARCHAR(255) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    CONSTRAINT uix_benchmark_observation
        UNIQUE (benchmark_code, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_history_code_observed_at
ON benchmark_histories (benchmark_code, observed_at);
