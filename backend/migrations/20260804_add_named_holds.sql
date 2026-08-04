CREATE TABLE IF NOT EXISTS case_holds (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    sort_order INTEGER NOT NULL DEFAULT 0,
    ntp_template_name VARCHAR(255),
    preservation_template_name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMPTZ,
    CONSTRAINT uq_case_hold_name UNIQUE (case_id, name)
);

CREATE INDEX IF NOT EXISTS ix_case_holds_case_id ON case_holds(case_id);

CREATE TABLE IF NOT EXISTS hold_custodians (
    id SERIAL PRIMARY KEY,
    hold_id INTEGER NOT NULL REFERENCES case_holds(id) ON DELETE CASCADE,
    custodian_id INTEGER NOT NULL REFERENCES custodians(id) ON DELETE CASCADE,
    ntp_status VARCHAR(32) NOT NULL DEFAULT 'not sent',
    ntp_sent_at TIMESTAMPTZ,
    ntp_acknowledged_at TIMESTAMPTZ,
    ntp_template_name VARCHAR(255),
    ntp_not_required_reason TEXT,
    consent_status VARCHAR(32) NOT NULL DEFAULT 'not sent',
    consent_not_required_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_hold_custodian UNIQUE (hold_id, custodian_id)
);

CREATE INDEX IF NOT EXISTS ix_hold_custodians_hold_id ON hold_custodians(hold_id);
CREATE INDEX IF NOT EXISTS ix_hold_custodians_custodian_id ON hold_custodians(custodian_id);

CREATE TABLE IF NOT EXISTS hold_preservation_sources (
    id SERIAL PRIMARY KEY,
    hold_custodian_id INTEGER NOT NULL REFERENCES hold_custodians(id) ON DELETE CASCADE,
    source_key VARCHAR(80) NOT NULL,
    source_label VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'not_started',
    provider_reference VARCHAR(512),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_hold_custodian_source UNIQUE (hold_custodian_id, source_key)
);

CREATE INDEX IF NOT EXISTS ix_hold_preservation_sources_membership
    ON hold_preservation_sources(hold_custodian_id);

CREATE TABLE IF NOT EXISTS hold_searches (
    id SERIAL PRIMARY KEY,
    hold_id INTEGER NOT NULL REFERENCES case_holds(id) ON DELETE CASCADE,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_hold_search UNIQUE (hold_id, search_id)
);

CREATE INDEX IF NOT EXISTS ix_hold_searches_hold_id ON hold_searches(hold_id);
CREATE INDEX IF NOT EXISTS ix_hold_searches_search_id ON hold_searches(search_id);

INSERT INTO case_holds (case_id, name, description, status, sort_order, created_at, updated_at, closed_at)
SELECT
    c.id,
    'Hold A',
    'Default hold created during named-hold migration.',
    CASE WHEN c.closed THEN 'closed' ELSE 'active' END,
    0,
    COALESCE(c.created_at, CURRENT_TIMESTAMP),
    COALESCE(c.updated_at, c.created_at, CURRENT_TIMESTAMP),
    CASE WHEN c.closed THEN COALESCE(c.closed_at, c.updated_at, c.created_at, CURRENT_TIMESTAMP) ELSE NULL END
FROM cases c
WHERE NOT EXISTS (
    SELECT 1 FROM case_holds h WHERE h.case_id = c.id
);

INSERT INTO hold_custodians (
    hold_id,
    custodian_id,
    ntp_status,
    ntp_sent_at,
    ntp_acknowledged_at,
    ntp_template_name,
    ntp_not_required_reason,
    consent_status,
    consent_not_required_reason,
    created_at,
    updated_at
)
SELECT
    h.id,
    c.id,
    COALESCE(NULLIF(c.ntp_status, ''), 'not sent'),
    c.ntp_sent_at,
    c.ntp_acknowledged_at,
    c.ntp_template_name,
    c.ntp_not_required_reason,
    COALESCE(NULLIF(c.consent_status, ''), 'not sent'),
    c.consent_not_required_reason,
    COALESCE(c.created_at, CURRENT_TIMESTAMP),
    CURRENT_TIMESTAMP
FROM custodians c
JOIN case_holds h ON h.case_id = c.case_id AND h.name = 'Hold A'
ON CONFLICT (hold_id, custodian_id) DO NOTHING;

INSERT INTO hold_preservation_sources (
    hold_custodian_id,
    source_key,
    source_label,
    status,
    created_at,
    updated_at
)
SELECT
    hc.id,
    source.source_key,
    source.source_label,
    CASE
        WHEN source.failed THEN 'failed'
        WHEN source.pending THEN 'pending'
        WHEN source.active THEN 'active'
        WHEN source.released THEN 'released'
        ELSE 'not_started'
    END,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM hold_custodians hc
JOIN custodians c ON c.id = hc.custodian_id
CROSS JOIN LATERAL (
    VALUES
        ('email', 'Email', c.holds_email, c.holds_email_pending, c.holds_email_failed, c.holds_email_released),
        ('onedrive', 'OneDrive', c.holds_onedrive, c.holds_onedrive_pending, c.holds_onedrive_failed, c.holds_onedrive_released),
        ('google_drive', 'Google Drive', c.holds_gdrive, c.holds_gdrive_pending, c.holds_gdrive_failed, c.holds_gdrive_released),
        ('box', 'Box', c.holds_box, c.holds_box_pending, c.holds_box_failed, c.holds_box_released),
        ('slack', 'Slack', c.holds_slack, c.holds_slack_pending, c.holds_slack_failed, c.holds_slack_released),
        ('crashplan', 'CrashPlan', c.holds_crashplan, FALSE, FALSE, FALSE),
        ('rubrik', 'Rubrik', c.holds_rubrik_restore, c.holds_rubrik_restore_pending, c.holds_rubrik_restore_failed, c.holds_rubrik_restore_released)
) AS source(source_key, source_label, active, pending, failed, released)
ON CONFLICT (hold_custodian_id, source_key) DO NOTHING;

INSERT INTO hold_preservation_sources (
    hold_custodian_id,
    source_key,
    source_label,
    status,
    created_at,
    updated_at
)
SELECT
    hc.id,
    cps.source_key,
    cps.source_label,
    CASE
        WHEN cps.failed THEN 'failed'
        WHEN cps.pending THEN 'pending'
        WHEN cps.active THEN 'active'
        WHEN cps.released THEN 'released'
        ELSE 'not_started'
    END,
    COALESCE(cps.created_at, CURRENT_TIMESTAMP),
    COALESCE(cps.updated_at, cps.created_at, CURRENT_TIMESTAMP)
FROM hold_custodians hc
JOIN custodian_preservation_sources cps ON cps.custodian_id = hc.custodian_id
ON CONFLICT (hold_custodian_id, source_key) DO UPDATE
SET source_label = EXCLUDED.source_label,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at;

INSERT INTO hold_searches (hold_id, search_id, created_at)
SELECT h.id, s.id, CURRENT_TIMESTAMP
FROM searches s
JOIN case_holds h ON h.case_id = s.case_id AND h.name = 'Hold A'
ON CONFLICT (hold_id, search_id) DO NOTHING;