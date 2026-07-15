-- Store the admin-selected role for registration requests.
ALTER TABLE public.account_registration_requests
    ADD COLUMN IF NOT EXISTS role VARCHAR(32);
