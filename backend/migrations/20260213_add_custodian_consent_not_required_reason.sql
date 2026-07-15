ALTER TABLE custodians
  ADD COLUMN IF NOT EXISTS consent_not_required_reason TEXT;