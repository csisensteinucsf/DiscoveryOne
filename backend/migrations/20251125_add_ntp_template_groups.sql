CREATE TABLE IF NOT EXISTS ntp_template_groups (
    id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES ntp_templates(id) ON DELETE CASCADE,
    group_name VARCHAR(255) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ntp_template_groups_template_group_idx
    ON ntp_template_groups (template_id, lower(group_name));
