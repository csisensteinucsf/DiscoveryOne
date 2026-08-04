-- Add configurable case templates, user UI preferences, and explicit workflow statuses.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS ui_preferences TEXT;

CREATE TABLE IF NOT EXISTS case_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 100,
    defaults TEXT NOT NULL DEFAULT '{}',
    field_rules TEXT NOT NULL DEFAULT '{}',
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_case_templates_name ON case_templates(name);

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS case_template_id INTEGER REFERENCES case_templates(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_cases_case_template_id ON cases(case_template_id);

ALTER TABLE case_request_consent_proofs
    ADD COLUMN IF NOT EXISTS proof_type VARCHAR(32) NOT NULL DEFAULT 'standard';

UPDATE case_request_consent_proofs
SET proof_type = 'standard'
WHERE proof_type IS NULL OR BTRIM(proof_type) = '';

UPDATE custodians
SET ntp_status = 'silent'
WHERE LOWER(BTRIM(COALESCE(ntp_status, ''))) IN ('na', 'n/a', 'not applicable', 'not required');

UPDATE hold_custodians
SET ntp_status = 'silent'
WHERE LOWER(BTRIM(COALESCE(ntp_status, ''))) IN ('na', 'n/a', 'not applicable', 'not required');

UPDATE custodians
SET consent_status = 'implied'
WHERE LOWER(BTRIM(COALESCE(consent_status, ''))) IN ('na', 'n/a', 'not applicable', 'not required');

UPDATE hold_custodians
SET consent_status = 'implied'
WHERE LOWER(BTRIM(COALESCE(consent_status, ''))) IN ('na', 'n/a', 'not applicable', 'not required');
