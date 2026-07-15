ALTER TABLE case_requests
  ADD COLUMN IF NOT EXISTS consent_attachment_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS consent_attachment_path VARCHAR(1024),
  ADD COLUMN IF NOT EXISTS consent_attachment_bytes INTEGER NOT NULL DEFAULT 0;
