-- backend/migrations/0001_add_user_email_role_and_indexes.sql
-- Ensure users.email/users.role exist; add constraint + indexes. Safe to re-run.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
    ) THEN
        CREATE TABLE public.users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            email VARCHAR(255),
            role VARCHAR(32) NOT NULL DEFAULT 'analyst'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'email'
    ) THEN
        ALTER TABLE public.users ADD COLUMN email VARCHAR(255);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'role'
    ) THEN
        ALTER TABLE public.users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'analyst';
    END IF;
END
$$;

UPDATE public.users SET role = 'sys_admin'
WHERE is_admin = TRUE AND (role IS NULL OR role = '');

UPDATE public.users SET role = 'analyst'
WHERE (role IS NULL OR role = '') AND is_admin = FALSE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_role_check' AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE public.users
        ADD CONSTRAINT users_role_check CHECK (role IN ('sys_admin', 'analyst', 'requestor'));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_idx ON public.users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON public.users (lower(email)) WHERE email IS NOT NULL;
