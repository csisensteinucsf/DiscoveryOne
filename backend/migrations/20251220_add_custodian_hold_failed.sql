-- Track failed hold requests separately from pending/completed
ALTER TABLE custodians
  ADD COLUMN IF NOT EXISTS holds_email_failed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_onedrive_failed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_box_failed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_slack_failed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_rubrik_restore_failed BOOLEAN NOT NULL DEFAULT FALSE;
