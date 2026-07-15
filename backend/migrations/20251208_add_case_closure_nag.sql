-- Add per-case closure reminder cadence and last nudged timestamp.
ALTER TABLE public.cases
    ADD COLUMN IF NOT EXISTS last_closure_nag_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS closure_nag_days INTEGER NOT NULL DEFAULT 180;
