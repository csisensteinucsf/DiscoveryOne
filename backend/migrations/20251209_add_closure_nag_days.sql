-- Add per-case closure reminder cadence (days) with a sensible default.
ALTER TABLE public.cases
    ADD COLUMN IF NOT EXISTS closure_nag_days INTEGER NOT NULL DEFAULT 180;

-- Backfill any existing rows that might be NULL if the column was created without NOT NULL.
UPDATE public.cases
SET closure_nag_days = 180
WHERE closure_nag_days IS NULL;
