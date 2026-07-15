import logging
import os

from .database import Base, SessionLocal, engine
from .safe_log import debug_suppressed as _debug_suppressed


def run_startup_schema_bootstrap() -> None:
    # Create tables if needed (safe if migrations also run)
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        _debug_suppressed("suppressed exception in main.py:154", exc)
    
    # ---- First-run bootstrap (idempotent) ----
    # Create audit_events (raw SQL; not in ORM)
    try:
        from sqlalchemy import text as _sql
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS audit_events (
              id BIGSERIAL PRIMARY KEY,
              actor_id    INTEGER,
              action      TEXT NOT NULL,
              target_type TEXT,
              target_id   INTEGER,
              details     JSONB,
              request_ip  TEXT,
              user_agent TEXT,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              event_hash TEXT
            );
            CREATE INDEX IF NOT EXISTS audit_events_created_at_idx ON audit_events (created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS audit_events_actor_id_idx   ON audit_events (actor_id);
            CREATE INDEX IF NOT EXISTS audit_events_target_idx     ON audit_events (target_type, target_id);
            ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_hash TEXT;
            CREATE UNIQUE INDEX IF NOT EXISTS audit_events_event_hash_idx ON audit_events (event_hash);
            ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS request_ip TEXT;
            ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS user_agent TEXT;
            CREATE TABLE IF NOT EXISTS case_request_consent_proofs (
              id BIGSERIAL PRIMARY KEY,
              case_request_id INTEGER REFERENCES case_requests(id) ON DELETE CASCADE,
              case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
              custodian_name TEXT,
              custodian_email TEXT,
              stored_filename VARCHAR(255) NOT NULL UNIQUE,
              original_filename VARCHAR(255) NOT NULL,
              content_type VARCHAR(128),
              size INTEGER NOT NULL DEFAULT 0,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS case_request_consent_proofs_req_idx ON case_request_consent_proofs(case_request_id);
            CREATE INDEX IF NOT EXISTS case_request_consent_proofs_case_idx ON case_request_consent_proofs(case_id);
            """)
    except Exception as _e:
        print(f"[bootstrap] audit_events skipped: {_e}")
    
    # Optional accelerator for action/category log filtering (best effort).
    try:
        with engine.begin() as _conn:
            _conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            _conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS audit_events_action_trgm_idx ON audit_events USING gin (action gin_trgm_ops);")
    except Exception as _e:
        print(f"[bootstrap] audit_events action index skipped: {_e}")
    
    try:
        from .audit import sync_audit_file_to_db
        _audit_sync_db = SessionLocal()
        try:
            _audit_sync_result = sync_audit_file_to_db(_audit_sync_db, max_files=int(os.getenv("AUDIT_SYNC_MAX_FILES", "10") or "10"), max_lines=int(os.getenv("AUDIT_SYNC_MAX_LINES", "50000") or "50000"))
            if (_audit_sync_result.get("inserted") or 0) > 0:
                logging.getLogger(__name__).info("audit_log_sync inserted=%s scanned=%s skipped=%s failed=%s", _audit_sync_result.get("inserted"), _audit_sync_result.get("scanned"), _audit_sync_result.get("skipped"), _audit_sync_result.get("failed"))
        finally:
            _audit_sync_db.close()
    except Exception as exc:
        _debug_suppressed("suppressed exception in main.py:audit_sync_startup", exc)
    
    # Ensure new user columns exist (safe to run repeatedly)
    try:
        from sqlalchemy import text as _sql
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
                 ALTER TABLE users
                   ADD COLUMN IF NOT EXISTS first_name VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS last_name VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS employee_id VARCHAR(128),
                   ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
                   ADD COLUMN IF NOT EXISTS requestor_group VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(255),
                   ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                   ADD COLUMN IF NOT EXISTS ntp_default_template_id INTEGER,
                   ADD COLUMN IF NOT EXISTS dashboards TEXT;
                  ALTER TABLE ntp_templates
                    ADD COLUMN IF NOT EXISTS cc TEXT,
                    ADD COLUMN IF NOT EXISTS bcc TEXT,
                    ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS high_importance BOOLEAN NOT NULL DEFAULT FALSE;
                ALTER TABLE cases
                  ADD COLUMN IF NOT EXISTS claimant VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS ler_representative VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS is_ler_hr BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS servicenow_inc_number VARCHAR(64),
                  ADD COLUMN IF NOT EXISTS rubrik_restore_ticket VARCHAR(64),
                  ADD COLUMN IF NOT EXISTS box_hold_ticket VARCHAR(64),
                  ADD COLUMN IF NOT EXISTS slack_hold_policy_id VARCHAR(64),
                  ADD COLUMN IF NOT EXISTS request_ticket_entries TEXT,
                  ADD COLUMN IF NOT EXISTS notes_internal_count INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS notes_requestor_count INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS notes_ticket_count INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS consent_envelope_count INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS consent_proof_count INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS is_active_case BOOLEAN NOT NULL DEFAULT FALSE;
                ALTER TABLE custodians
                  ADD COLUMN IF NOT EXISTS holds_gdrive BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_gdrive_pending BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_rubrik_restore BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_crashplan BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_email_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_onedrive_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_gdrive_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_box_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_slack_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_rubrik_restore_failed BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_email_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_onedrive_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_gdrive_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_box_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_slack_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS holds_rubrik_restore_released BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS onedrive_site_id TEXT,
                  ADD COLUMN IF NOT EXISTS person_lookup_overridden BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS consent_not_required_reason TEXT,
                  ADD COLUMN IF NOT EXISTS ntp_not_required_reason TEXT,
                  ADD COLUMN IF NOT EXISTS ntp_sent_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS ntp_acknowledged_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS ntp_template_name VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS slack_user_id VARCHAR(64),
                  ADD COLUMN IF NOT EXISTS employee_id VARCHAR(128),
                  ADD COLUMN IF NOT EXISTS person_first_name VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS person_last_name VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS person_department_id VARCHAR(128),
                  ADD COLUMN IF NOT EXISTS person_department VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS person_title VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS person_current_employee BOOLEAN,
                  ADD COLUMN IF NOT EXISTS person_lookup_last_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS name_email_review_required BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS name_email_review_reason TEXT,
                  ADD COLUMN IF NOT EXISTS name_email_review_last_checked_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
                  ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ;
                ALTER TABLE case_notes
                  ADD COLUMN IF NOT EXISTS audience VARCHAR(32) NOT NULL DEFAULT 'internal';
                ALTER TABLE case_requests
                  ADD COLUMN IF NOT EXISTS attachment_bytes INTEGER NOT NULL DEFAULT 0,
                  ADD COLUMN IF NOT EXISTS consent_attachment_name VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS consent_attachment_path VARCHAR(1024),
                  ADD COLUMN IF NOT EXISTS consent_attachment_bytes INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE case_request_consent_proofs
                  ADD COLUMN IF NOT EXISTS case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE;
                ALTER TABLE case_request_consent_proofs
                  ADD COLUMN IF NOT EXISTS uploaded_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
                ALTER TABLE case_request_consent_proofs
                  ALTER COLUMN case_request_id DROP NOT NULL;
                ALTER TABLE account_registration_requests
                  ADD COLUMN IF NOT EXISTS requestor_group VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS sso_subject VARCHAR(255),
                  ADD COLUMN IF NOT EXISTS role VARCHAR(32);
                ALTER TABLE case_consents
                  ADD COLUMN IF NOT EXISTS last_resent_at TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS provider VARCHAR(64);
                UPDATE case_consents
                   SET provider = 'docusign'
                 WHERE provider IS NULL OR BTRIM(provider) = '';
                ALTER TABLE case_consents
                  ALTER COLUMN provider SET DEFAULT 'docusign',
                  ALTER COLUMN provider SET NOT NULL;
                CREATE INDEX IF NOT EXISTS case_consents_provider_idx ON case_consents(provider);
                CREATE TABLE IF NOT EXISTS case_requestors (
                  id SERIAL PRIMARY KEY,
                  case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                  email VARCHAR(512) NOT NULL,
                  requestor_group VARCHAR(255),
                  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS case_requestors_case_id_idx ON case_requestors (case_id);
                CREATE INDEX IF NOT EXISTS case_requestors_user_id_idx ON case_requestors (user_id);
                CREATE INDEX IF NOT EXISTS case_requestors_email_idx ON case_requestors (LOWER(email));
                CREATE INDEX IF NOT EXISTS case_requestors_primary_idx ON case_requestors (case_id, is_primary DESC);
                CREATE INDEX IF NOT EXISTS case_notes_case_audience_updated_idx ON case_notes (case_id, audience, is_pinned DESC, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS searches_case_status_idx ON searches (case_id, status_search, status_export, status_delivery);
                CREATE UNIQUE INDEX IF NOT EXISTS ix_users_sso_subject ON users (sso_subject);
                CREATE INDEX IF NOT EXISTS ix_account_registration_requests_sso_subject ON account_registration_requests (sso_subject);
                UPDATE custodians AS c
                   SET created_at = src.first_added_at
                  FROM (
                        SELECT target_id AS custodian_id, MIN(created_at) AS first_added_at
                          FROM audit_events
                         WHERE target_type = 'custodian'
                           AND action IN ('custodian_create', 'custodian_add')
                         GROUP BY target_id
                       ) AS src
                 WHERE c.id = src.custodian_id
                   AND (c.created_at IS NULL OR c.created_at > src.first_added_at);
                UPDATE custodians SET created_at = NOW() WHERE created_at IS NULL;
            """)
    except Exception as _e:
        print(f"[bootstrap] users column ensure skipped: {_e}")
