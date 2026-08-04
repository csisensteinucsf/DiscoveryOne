-- Associate manually uploaded consent evidence with the named hold workflow it satisfies.
ALTER TABLE case_request_consent_proofs
    ADD COLUMN IF NOT EXISTS hold_custodian_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_case_request_consent_proofs_hold_custodian') THEN
        ALTER TABLE case_request_consent_proofs
            ADD CONSTRAINT fk_case_request_consent_proofs_hold_custodian
            FOREIGN KEY (hold_custodian_id) REFERENCES hold_custodians(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_case_request_consent_proofs_hold_custodian_id
    ON case_request_consent_proofs(hold_custodian_id);

WITH candidate_memberships AS (
    SELECT
        proof.id AS proof_id,
        membership.id AS hold_custodian_id,
        ROW_NUMBER() OVER (
            PARTITION BY proof.id
            ORDER BY hold_record.sort_order ASC, hold_record.id ASC, membership.id ASC
        ) AS rank
    FROM case_request_consent_proofs proof
    JOIN custodians custodian
      ON custodian.case_id = proof.case_id
     AND (
            (NULLIF(BTRIM(proof.custodian_email), '') IS NOT NULL
             AND LOWER(BTRIM(custodian.email)) = LOWER(BTRIM(proof.custodian_email)))
         OR (NULLIF(BTRIM(proof.custodian_email), '') IS NULL
             AND NULLIF(BTRIM(proof.custodian_name), '') IS NOT NULL
             AND LOWER(BTRIM(custodian.name)) = LOWER(BTRIM(proof.custodian_name)))
     )
    JOIN hold_custodians membership ON membership.custodian_id = custodian.id
    JOIN case_holds hold_record ON hold_record.id = membership.hold_id AND hold_record.case_id = proof.case_id
    WHERE proof.hold_custodian_id IS NULL
)
UPDATE case_request_consent_proofs proof
SET hold_custodian_id = candidate.hold_custodian_id
FROM candidate_memberships candidate
WHERE proof.id = candidate.proof_id
  AND candidate.rank = 1;