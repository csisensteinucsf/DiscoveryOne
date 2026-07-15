-- Track pending hold requests separately from completed holds
ALTER TABLE custodians
  ADD COLUMN IF NOT EXISTS holds_email_pending BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_onedrive_pending BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_box_pending BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_slack_pending BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_rubrik_restore_pending BOOLEAN NOT NULL DEFAULT FALSE;
