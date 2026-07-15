-- Backfill custodian NTP template name from historical audit events.
-- Uses the most recent ntp_email_sent event per custodian.
DO $$
BEGIN
    IF to_regclass('public.audit_events') IS NOT NULL THEN
        WITH latest_ntp AS (
            SELECT
                (ev.details->>'custodian_id')::integer AS custodian_id,
                NULLIF(BTRIM(ev.details->>'template_name'), '') AS template_name,
                ROW_NUMBER() OVER (
                    PARTITION BY (ev.details->>'custodian_id')::integer
                    ORDER BY ev.created_at DESC, ev.id DESC
                ) AS rn
            FROM audit_events ev
            WHERE ev.action = 'ntp_email_sent'
              AND ev.details IS NOT NULL
              AND (ev.details->>'custodian_id') ~ '^[0-9]+$'
              AND NULLIF(BTRIM(ev.details->>'template_name'), '') IS NOT NULL
        )
        UPDATE custodians c
        SET ntp_template_name = latest_ntp.template_name
        FROM latest_ntp
        WHERE latest_ntp.rn = 1
          AND c.id = latest_ntp.custodian_id
          AND COALESCE(BTRIM(c.ntp_template_name), '') = '';
    END IF;
END
$$;
