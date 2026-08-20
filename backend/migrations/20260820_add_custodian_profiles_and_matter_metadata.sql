ALTER TABLE cases ADD COLUMN IF NOT EXISTS campus VARCHAR(255);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS matter_type VARCHAR(255);

ALTER TABLE custodians ADD COLUMN IF NOT EXISTS campus VARCHAR(255);

ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS last_name VARCHAR(255);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS campus VARCHAR(255);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS department VARCHAR(255);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS employee_id VARCHAR(128);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS title VARCHAR(255);
ALTER TABLE custodian_directory ADD COLUMN IF NOT EXISTS employment_status VARCHAR(128);

UPDATE custodian_directory
SET first_name = COALESCE(NULLIF(first_name, ''), split_part(name, ' ', 1)),
    last_name = COALESCE(NULLIF(last_name, ''), NULLIF(trim(substr(name, length(split_part(name, ' ', 1)) + 1)), '')),
    campus = COALESCE(campus, 'Not specified');

UPDATE custodian_directory SET last_name = 'Not specified' WHERE last_name IS NULL OR last_name = '';

ALTER TABLE custodian_directory ALTER COLUMN first_name SET NOT NULL;
ALTER TABLE custodian_directory ALTER COLUMN last_name SET NOT NULL;
ALTER TABLE custodian_directory ALTER COLUMN campus SET NOT NULL;
