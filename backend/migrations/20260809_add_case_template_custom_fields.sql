-- Persist template-defined custom case fields without customer-specific schema changes.
ALTER TABLE case_templates
    ADD COLUMN IF NOT EXISTS custom_fields TEXT NOT NULL DEFAULT '[]';

ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS custom_fields TEXT NOT NULL DEFAULT '{}';
