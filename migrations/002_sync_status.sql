CREATE TABLE IF NOT EXISTS sync_status (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    error_message TEXT
);