ALTER TABLE cases
  ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS requestor_group_access (
  id SERIAL PRIMARY KEY,
  source_group VARCHAR(255) NOT NULL,
  target_group VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_requestor_group_access_source_target
  ON requestor_group_access (lower(source_group), lower(target_group));

CREATE INDEX IF NOT EXISTS ix_requestor_group_access_source
  ON requestor_group_access (lower(source_group));

CREATE INDEX IF NOT EXISTS ix_requestor_group_access_target
  ON requestor_group_access (lower(target_group));
