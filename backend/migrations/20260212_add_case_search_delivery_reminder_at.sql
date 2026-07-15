ALTER TABLE cases
  ADD COLUMN IF NOT EXISTS last_search_delivery_reminder_at TIMESTAMPTZ;
