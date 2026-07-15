-- backend/migrations/0002_fix_users_role_default.sql
ALTER TABLE public.users ALTER COLUMN role SET DEFAULT 'analyst';

UPDATE public.users
SET role = 'sys_admin'
WHERE is_admin = TRUE AND (role IS NULL OR role = '' OR role NOT IN ('sys_admin','analyst','requestor'));

UPDATE public.users
SET role = 'analyst'
WHERE (role IS NULL OR role = '' OR role NOT IN ('sys_admin','analyst','requestor'));

ALTER TABLE public.users ALTER COLUMN role SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_role_check' AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE public.users
        ADD CONSTRAINT users_role_check CHECK (role IN ('sys_admin', 'analyst', 'requestor'));
    END IF;
END
$$;
