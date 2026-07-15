-- Persist the provider that owns each e-signature consent request.
ALTER TABLE case_consents
  ADD COLUMN IF NOT EXISTS provider VARCHAR(64);

-- All rows created before provider ownership was recorded belong to DocuSign.
UPDATE case_consents
   SET provider = 'docusign'
 WHERE provider IS NULL OR BTRIM(provider) = '';

ALTER TABLE case_consents
  ALTER COLUMN provider SET DEFAULT 'docusign',
  ALTER COLUMN provider SET NOT NULL;

-- Request identifiers are provider-owned and may overlap across providers.
ALTER TABLE case_consents
  DROP CONSTRAINT IF EXISTS case_consents_envelope_id_key;
DROP INDEX IF EXISTS ix_case_consents_envelope_id;
CREATE INDEX IF NOT EXISTS ix_case_consents_envelope_id
  ON case_consents(envelope_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_case_consents_provider_request_id
  ON case_consents(provider, envelope_id);

CREATE INDEX IF NOT EXISTS case_consents_provider_idx
  ON case_consents(provider);
