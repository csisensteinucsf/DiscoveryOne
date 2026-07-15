-- Allow tech (and tester) roles in users.role constraint.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_role_check' AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE public.users DROP CONSTRAINT users_role_check;
    END IF;
END
$$;

ALTER TABLE public.users
    ADD CONSTRAINT users_role_check CHECK (role IN ('sys_admin', 'analyst', 'requestor', 'tech', 'tester'));
