ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_id VARCHAR(128);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'pp_02_number'
    ) THEN
        EXECUTE 'UPDATE users SET employee_id = pp_02_number WHERE employee_id IS NULL AND pp_02_number IS NOT NULL';
    END IF;
END $$;
