CREATE TABLE IF NOT EXISTS custodian_preservation_sources (
  id SERIAL PRIMARY KEY,
  custodian_id INTEGER NOT NULL REFERENCES custodians(id) ON DELETE CASCADE,
  source_key VARCHAR(80) NOT NULL,
  source_label VARCHAR(255) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  pending BOOLEAN NOT NULL DEFAULT FALSE,
  failed BOOLEAN NOT NULL DEFAULT FALSE,
  released BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NULL,
  CONSTRAINT uq_custodian_preservation_source UNIQUE (custodian_id, source_key)
);

CREATE INDEX IF NOT EXISTS ix_custodian_preservation_sources_custodian_id
  ON custodian_preservation_sources (custodian_id);
