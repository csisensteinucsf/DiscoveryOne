-- Attach operational workflow records to named holds while preserving legacy case/custodian fields.
ALTER TABLE hold_searches
    ADD COLUMN IF NOT EXISTS status_search VARCHAR NOT NULL DEFAULT 'not performed',
    ADD COLUMN IF NOT EXISTS status_export VARCHAR NOT NULL DEFAULT 'not performed',
    ADD COLUMN IF NOT EXISTS status_delivery VARCHAR NOT NULL DEFAULT 'not performed',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE ntp_tokens
    ADD COLUMN IF NOT EXISTS hold_custodian_id INTEGER;

ALTER TABLE ntp_reminders
    ADD COLUMN IF NOT EXISTS hold_custodian_id INTEGER;

ALTER TABLE case_consents
    ADD COLUMN IF NOT EXISTS hold_custodian_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ntp_tokens_hold_custodian') THEN
        ALTER TABLE ntp_tokens
            ADD CONSTRAINT fk_ntp_tokens_hold_custodian
            FOREIGN KEY (hold_custodian_id) REFERENCES hold_custodians(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ntp_reminders_hold_custodian') THEN
        ALTER TABLE ntp_reminders
            ADD CONSTRAINT fk_ntp_reminders_hold_custodian
            FOREIGN KEY (hold_custodian_id) REFERENCES hold_custodians(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_case_consents_hold_custodian') THEN
        ALTER TABLE case_consents
            ADD CONSTRAINT fk_case_consents_hold_custodian
            FOREIGN KEY (hold_custodian_id) REFERENCES hold_custodians(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_ntp_tokens_hold_custodian_id ON ntp_tokens(hold_custodian_id);
CREATE INDEX IF NOT EXISTS ix_ntp_reminders_hold_custodian_id ON ntp_reminders(hold_custodian_id);
CREATE INDEX IF NOT EXISTS ix_case_consents_hold_custodian_id ON case_consents(hold_custodian_id);

UPDATE hold_searches hs
SET status_search = COALESCE(s.status_search, 'not performed'),
    status_export = COALESCE(s.status_export, 'not performed'),
    status_delivery = COALESCE(s.status_delivery, 'not performed'),
    updated_at = NOW()
FROM searches s
WHERE s.id = hs.search_id;

UPDATE ntp_tokens token
SET hold_custodian_id = hc.id
FROM hold_custodians hc
JOIN case_holds hold_record ON hold_record.id = hc.hold_id
WHERE token.hold_custodian_id IS NULL
  AND hc.custodian_id = token.custodian_id
  AND hold_record.case_id = token.case_id
  AND hold_record.sort_order = (
      SELECT MIN(first_hold.sort_order)
      FROM case_holds first_hold
      WHERE first_hold.case_id = token.case_id
  );

UPDATE ntp_reminders reminder
SET hold_custodian_id = hc.id
FROM hold_custodians hc
JOIN case_holds hold_record ON hold_record.id = hc.hold_id
WHERE reminder.hold_custodian_id IS NULL
  AND hc.custodian_id = reminder.custodian_id
  AND hold_record.case_id = reminder.case_id
  AND hold_record.sort_order = (
      SELECT MIN(first_hold.sort_order)
      FROM case_holds first_hold
      WHERE first_hold.case_id = reminder.case_id
  );

UPDATE case_consents consent
SET hold_custodian_id = hc.id
FROM hold_custodians hc
JOIN case_holds hold_record ON hold_record.id = hc.hold_id
WHERE consent.hold_custodian_id IS NULL
  AND consent.custodian_id IS NOT NULL
  AND hc.custodian_id = consent.custodian_id
  AND hold_record.case_id = consent.case_id
  AND hold_record.sort_order = (
      SELECT MIN(first_hold.sort_order)
      FROM case_holds first_hold
      WHERE first_hold.case_id = consent.case_id
  );