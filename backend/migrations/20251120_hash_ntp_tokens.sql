-- Hash existing NTP acknowledgement tokens so leaked database contents cannot be replayed.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF to_regclass('public.ntp_tokens') IS NOT NULL THEN
        UPDATE ntp_tokens
        SET token = encode(digest(token, 'sha256'), 'hex')
        WHERE token !~ '^[0-9a-f]{64}$';
    END IF;
END
$$;
