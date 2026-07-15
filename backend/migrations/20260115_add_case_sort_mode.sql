-- Per-user case sorting preference for the Cases page.
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS case_sort_mode VARCHAR(32) NULL;

UPDATE users
   SET case_sort_mode = 'ediscovery'
 WHERE case_sort_mode IS NULL;

ALTER TABLE users
  ALTER COLUMN case_sort_mode SET DEFAULT 'ediscovery';
