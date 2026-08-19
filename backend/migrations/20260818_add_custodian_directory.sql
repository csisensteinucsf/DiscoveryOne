CREATE TABLE IF NOT EXISTS custodian_directory (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_custodian_directory_email_lower
    ON custodian_directory (LOWER(email));

CREATE INDEX IF NOT EXISTS ix_custodian_directory_name_lower
    ON custodian_directory (LOWER(name));
