CREATE TABLE IF NOT EXISTS case_request_consent_proofs (
  id BIGSERIAL PRIMARY KEY,
  case_request_id INTEGER NOT NULL REFERENCES case_requests(id) ON DELETE CASCADE,
  custodian_name TEXT,
  custodian_email TEXT,
  stored_filename VARCHAR(255) NOT NULL UNIQUE,
  original_filename VARCHAR(255) NOT NULL,
  content_type VARCHAR(128),
  size INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS case_request_consent_proofs_req_idx ON case_request_consent_proofs(case_request_id);
