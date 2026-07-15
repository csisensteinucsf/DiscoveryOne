ALTER TABLE custodians ADD COLUMN IF NOT EXISTS employee_id VARCHAR(128);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_first_name VARCHAR(255);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_last_name VARCHAR(255);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_department_id VARCHAR(128);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_department VARCHAR(255);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_title VARCHAR(255);
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_current_employee BOOLEAN;
ALTER TABLE custodians ADD COLUMN IF NOT EXISTS person_lookup_last_at TIMESTAMPTZ;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_ucsfid') THEN
        EXECUTE 'UPDATE custodians SET employee_id = scuba_ucsfid WHERE employee_id IS NULL AND scuba_ucsfid IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_first_name') THEN
        EXECUTE 'UPDATE custodians SET person_first_name = scuba_first_name WHERE person_first_name IS NULL AND scuba_first_name IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_last_name') THEN
        EXECUTE 'UPDATE custodians SET person_last_name = scuba_last_name WHERE person_last_name IS NULL AND scuba_last_name IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_department_id') THEN
        EXECUTE 'UPDATE custodians SET person_department_id = scuba_department_id WHERE person_department_id IS NULL AND scuba_department_id IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_department_name') THEN
        EXECUTE 'UPDATE custodians SET person_department = scuba_department_name WHERE person_department IS NULL AND scuba_department_name IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_job_title_official') THEN
        EXECUTE 'UPDATE custodians SET person_title = scuba_job_title_official WHERE person_title IS NULL AND scuba_job_title_official IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_current_employee') THEN
        EXECUTE 'UPDATE custodians SET person_current_employee = scuba_current_employee WHERE person_current_employee IS NULL AND scuba_current_employee IS NOT NULL';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'custodians' AND column_name = 'scuba_last_lookup_at') THEN
        EXECUTE 'UPDATE custodians SET person_lookup_last_at = scuba_last_lookup_at WHERE person_lookup_last_at IS NULL AND scuba_last_lookup_at IS NOT NULL';
    END IF;
END $$;
