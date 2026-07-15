ALTER TABLE cases
  ADD COLUMN IF NOT EXISTS request_ticket_entries TEXT;
