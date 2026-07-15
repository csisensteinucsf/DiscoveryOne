-- Ensure crashplan hold has a safe default for custodian inserts.
ALTER TABLE public.custodians
    ADD COLUMN IF NOT EXISTS holds_crashplan BOOLEAN;

UPDATE public.custodians
    SET holds_crashplan = FALSE
    WHERE holds_crashplan IS NULL;

ALTER TABLE public.custodians
    ALTER COLUMN holds_crashplan SET DEFAULT FALSE;

ALTER TABLE public.custodians
    ALTER COLUMN holds_crashplan SET NOT NULL;
