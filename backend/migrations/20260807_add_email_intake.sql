-- Add Microsoft Graph email-to-case intake templates, delta cursor, and idempotent message tracking.
CREATE TABLE IF NOT EXISTS email_intake_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 100,
    sender_pattern VARCHAR(512),
    recipient_pattern VARCHAR(512),
    subject_pattern VARCHAR(512),
    body_markers TEXT,
    field_markers TEXT,
    default_values TEXT,
    hold_name VARCHAR(255),
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_intake_cursors (
    id SERIAL PRIMARY KEY,
    mailbox VARCHAR(320) NOT NULL,
    folder_id VARCHAR(512) NOT NULL,
    delta_link TEXT,
    baseline_pending BOOLEAN NOT NULL DEFAULT TRUE,
    last_polled_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_email_intake_cursor_mailbox_folder UNIQUE (mailbox, folder_id)
);

CREATE INDEX IF NOT EXISTS ix_email_intake_cursors_mailbox ON email_intake_cursors(mailbox);

CREATE TABLE IF NOT EXISTS email_intake_messages (
    id SERIAL PRIMARY KEY,
    mailbox VARCHAR(320) NOT NULL,
    graph_message_id VARCHAR(1024) NOT NULL,
    internet_message_id VARCHAR(1024),
    change_key VARCHAR(512),
    status VARCHAR(32) NOT NULL DEFAULT 'received',
    template_id INTEGER REFERENCES email_intake_templates(id) ON DELETE SET NULL,
    case_request_id INTEGER REFERENCES case_requests(id) ON DELETE SET NULL,
    sender VARCHAR(320),
    recipients TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    body_text TEXT,
    attachment_count INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_email_intake_mailbox_message UNIQUE (mailbox, graph_message_id)
);

CREATE INDEX IF NOT EXISTS ix_email_intake_messages_status ON email_intake_messages(status);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_template_id ON email_intake_messages(template_id);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_case_request_id ON email_intake_messages(case_request_id);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_received_at ON email_intake_messages(received_at);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_next_retry_at ON email_intake_messages(next_retry_at);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_sender ON email_intake_messages(sender);
CREATE INDEX IF NOT EXISTS ix_email_intake_messages_internet_message_id ON email_intake_messages(internet_message_id);