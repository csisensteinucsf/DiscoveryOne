ALTER TABLE custodians
  ADD COLUMN IF NOT EXISTS ntp_template_name VARCHAR(255);