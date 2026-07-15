-- Add employment metadata to custodians for badge/status rendering
ALTER TABLE custodians
    ADD COLUMN IF NOT EXISTS employment_end_date TEXT,
    ADD COLUMN IF NOT EXISTS employment_status TEXT;
