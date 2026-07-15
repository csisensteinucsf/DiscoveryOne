-- Add email + role columns to users and backfill from existing data.
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS email VARCHAR(255),
  ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'analyst';

-- Backfill roles for existing rows.
UPDATE users
SET role = 'sys_admin'
WHERE is_admin = TRUE
  AND (role IS NULL OR role = '');

UPDATE users
SET role = 'analyst'
WHERE (role IS NULL OR role = '')
  AND is_admin = FALSE;

-- Ensure email is unique when present.
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'users_email_key'
        AND conrelid = 'users'::regclass
  ) THEN
    ALTER TABLE users
      ADD CONSTRAINT users_email_key UNIQUE (email);
  END IF;
END
$$;

-- Constrain role values to the three allowed roles.
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'users_role_check'
        AND conrelid = 'users'::regclass
  ) THEN
    ALTER TABLE users
      ADD CONSTRAINT users_role_check
      CHECK (role IN ('sys_admin', 'analyst', 'requestor'));
  END IF;
END
$$;