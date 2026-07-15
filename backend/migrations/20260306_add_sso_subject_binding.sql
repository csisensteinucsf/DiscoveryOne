ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_sso_subject ON users (sso_subject);
ALTER TABLE account_registration_requests ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255);
CREATE INDEX IF NOT EXISTS ix_account_registration_requests_sso_subject ON account_registration_requests (sso_subject);
