-- Avoid immediate bulk reminder sends: seed the last_closure_nag_at for existing cases.
UPDATE public.cases
SET last_closure_nag_at = NOW()
WHERE last_closure_nag_at IS NULL;
