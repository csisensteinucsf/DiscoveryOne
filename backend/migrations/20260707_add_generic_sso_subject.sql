ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'okta_subject'
    ) THEN
        EXECUTE 'UPDATE users SET sso_subject = okta_subject WHERE sso_subject IS NULL AND okta_subject IS NOT NULL';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_sso_subject ON users (sso_subject);

ALTER TABLE account_registration_requests ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'account_registration_requests'
          AND column_name = 'okta_subject'
    ) THEN
        EXECUTE 'UPDATE account_registration_requests SET sso_subject = okta_subject WHERE sso_subject IS NULL AND okta_subject IS NOT NULL';
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_account_registration_requests_sso_subject ON account_registration_requests (sso_subject);
