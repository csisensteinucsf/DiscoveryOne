ALTER TABLE case_requests
  ADD COLUMN IF NOT EXISTS case_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE case_requests
  ADD COLUMN IF NOT EXISTS case_name_lookup TEXT GENERATED ALWAYS AS (lower(trim(case_name))) STORED;
CREATE INDEX IF NOT EXISTS case_requests_case_name_lookup_idx ON case_requests(case_name_lookup);
