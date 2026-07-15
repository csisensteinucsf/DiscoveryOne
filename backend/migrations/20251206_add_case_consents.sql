-- Add table for tracking DocuSign consent envelopes per case/custodian
CREATE TABLE IF NOT EXISTS case_consents (
  id BIGSERIAL PRIMARY KEY,
  case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
  custodian_id INTEGER REFERENCES custodians(id) ON DELETE SET NULL,
  custodian_name TEXT,
  custodian_email TEXT,
  envelope_id TEXT UNIQUE NOT NULL,
  status TEXT,
  record_type TEXT,
  date_from TEXT,
  date_to TEXT,
  message TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_consents_case_id ON case_consents(case_id);
