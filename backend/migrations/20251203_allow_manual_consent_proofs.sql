ALTER TABLE case_request_consent_proofs
    ADD COLUMN IF NOT EXISTS case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE;

ALTER TABLE case_request_consent_proofs
    ADD COLUMN IF NOT EXISTS uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

UPDATE case_request_consent_proofs AS proof
SET case_id = req.case_id
FROM case_requests AS req
WHERE proof.case_request_id = req.id
  AND proof.case_id IS NULL;

CREATE INDEX IF NOT EXISTS case_request_consent_proofs_case_idx
    ON case_request_consent_proofs(case_id);

ALTER TABLE case_request_consent_proofs
    ALTER COLUMN case_request_id DROP NOT NULL;
