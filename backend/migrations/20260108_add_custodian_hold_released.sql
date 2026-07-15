-- Track released holds separately from pending/completed
ALTER TABLE custodians
  ADD COLUMN IF NOT EXISTS holds_email_released BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_onedrive_released BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_box_released BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_slack_released BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS holds_rubrik_restore_released BOOLEAN NOT NULL DEFAULT FALSE;
