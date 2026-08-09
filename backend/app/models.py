from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, Date, LargeBinary, func, Computed, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import json
from .database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    local_auth_only = Column(Boolean, nullable=False, default=False)
    sso_subject = Column("sso_subject", String(255), nullable=True, unique=True, index=True)
    # Optional unique email for notifications / identification
    email = Column(String, unique=True, nullable=True, index=True)
    employee_id = Column("employee_id", String(128), nullable=True)
    # Application-level role; 'sys_admin' replaces previous admin checkbox in UI
    role = Column(String, nullable=False, default="analyst")
    requestor_group = Column(String, nullable=True)
    user_theme = Column(String(16), nullable=True)
    # Per-user preference: how Cases page groups/sorts within year/letter buckets.
    # Values: "ediscovery" (default) or "legal".
    case_sort_mode = Column(String(32), nullable=True, default="ediscovery")
    totp_secret = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    ntp_default_template_id = Column(Integer, ForeignKey("ntp_templates.id", ondelete="SET NULL"), nullable=True)
    dashboards_raw = Column("dashboards", Text, nullable=True)
    ui_preferences_raw = Column("ui_preferences", Text, nullable=True)
    trusted_devices = relationship("TrustedDevice", back_populates="user", cascade="all, delete-orphan")

    @property
    def dashboards(self):
        raw = getattr(self, "dashboards_raw", None)
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, str)):
            try:
                return json.loads(raw) or None
            except Exception:
                return None
        return None

    @dashboards.setter
    def dashboards(self, value):
        if value is None:
            self.dashboards_raw = None
            return
        try:
            self.dashboards_raw = json.dumps(value)
        except Exception:
            self.dashboards_raw = None

    @property
    def ui_preferences(self):
        raw = getattr(self, "ui_preferences_raw", None)
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, str)):
            try:
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return {}

    @ui_preferences.setter
    def ui_preferences(self, value):
        try:
            self.ui_preferences_raw = json.dumps(value or {})
        except Exception:
            self.ui_preferences_raw = "{}"


class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    legal_case_name = Column(String, nullable=True)
    is_ler_hr = Column(Boolean, nullable=False, default=False)
    servicenow_inc_number = Column(String(64), nullable=True)
    claimant = Column(String, nullable=True)
    ler_representative = Column(String, nullable=True)
    internal_counsel = Column(String, nullable=True)
    outside_counsel = Column(String, nullable=True)
    matter_number = Column(String(128), nullable=True)
    requestor = Column(String, nullable=True)
    analyst_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed = Column(Boolean, nullable=False, default=False)
    is_private = Column(Boolean, nullable=False, default=False)
    is_test_case = Column(Boolean, nullable=False, default=False)
    color = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    rubrik_restore_ticket = Column(String(64), nullable=True)
    box_hold_ticket = Column(String(64), nullable=True)
    slack_hold_policy_id = Column(String(64), nullable=True)
    request_ticket_entries_raw = Column("request_ticket_entries", Text, nullable=True)
    # Case consents (DocuSign envelopes) relationship defined below CaseConsent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    notes_internal_count = Column(Integer, nullable=False, default=0)
    notes_requestor_count = Column(Integer, nullable=False, default=0)
    notes_ticket_count = Column(Integer, nullable=False, default=0)
    consent_envelope_count = Column(Integer, nullable=False, default=0)
    consent_proof_count = Column(Integer, nullable=False, default=0)
    is_active_case = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=True)
    last_closure_nag_at = Column(DateTime(timezone=True), nullable=True)
    last_search_delivery_reminder_at = Column(DateTime(timezone=True), nullable=True)
    closure_nag_days = Column(Integer, nullable=False, default=180)
    case_template_id = Column(Integer, ForeignKey("case_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    custom_fields_raw = Column("custom_fields", Text, nullable=False, default="{}")



    analyst = relationship("User", lazy="joined")
    custodians = relationship("Custodian", back_populates="case", cascade="all, delete-orphan")
    consents = relationship("CaseConsent", back_populates="case", cascade="all, delete-orphan")
    requestors = relationship("CaseRequestor", back_populates="case", cascade="all, delete-orphan")
    holds = relationship("CaseHold", back_populates="case", cascade="all, delete-orphan", order_by="CaseHold.sort_order")
    case_template = relationship("CaseTemplate", back_populates="cases")

    @property
    def custom_fields(self):
        raw = self.custom_fields_raw
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, str)) and raw:
            try:
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return {}

    @custom_fields.setter
    def custom_fields(self, value):
        self.custom_fields_raw = json.dumps(value or {})

    @property
    def request_ticket_entries(self):
        raw = self.request_ticket_entries_raw
        entries: list[dict] = []
        if isinstance(raw, (bytes, str)) and raw:
            try:
                entries = json.loads(raw) or []
            except Exception:
                entries = []
        elif isinstance(raw, list):
            entries = raw
        if entries:
            entries = [
                e for e in entries
                if isinstance(e, dict) and str(e.get("category") or "").strip()
            ]
        if not entries:
            fallback = []
            if getattr(self, "rubrik_restore_ticket", None):
                fallback.append({
                    "id": "legacy-rubrik",
                    "category": "rubrik_restore",
                    "ticket": self.rubrik_restore_ticket,
                    "custodian_id": None,
                    "custodian_name": None,
                    "custodian_email": None,
                })
            if getattr(self, "box_hold_ticket", None):
                fallback.append({
                    "id": "legacy-box",
                    "category": "box_hold",
                    "ticket": self.box_hold_ticket,
                    "custodian_id": None,
                    "custodian_name": None,
                    "custodian_email": None,
                })
            entries = fallback
        return entries or []

    @request_ticket_entries.setter
    def request_ticket_entries(self, value):
        try:
            serialized = json.dumps(value or [])
        except Exception:
            serialized = "[]"
        self.request_ticket_entries_raw = serialized


class CaseTemplate(Base):
    __tablename__ = "case_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=100)
    defaults_raw = Column("defaults", Text, nullable=False, default="{}")
    field_rules_raw = Column("field_rules", Text, nullable=False, default="{}")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    custom_fields_raw = Column("custom_fields", Text, nullable=False, default="[]")
    updated_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cases = relationship("Case", back_populates="case_template")
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    @staticmethod
    def _load_object(raw):
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, str)) and raw:
            try:
                value = json.loads(raw)
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return {}

    @property
    def defaults(self):
        return self._load_object(self.defaults_raw)

    @defaults.setter
    def defaults(self, value):
        self.defaults_raw = json.dumps(value or {})

    @property
    def field_rules(self):
        return self._load_object(self.field_rules_raw)

    @field_rules.setter
    def field_rules(self, value):
        self.field_rules_raw = json.dumps(value or {})

    @property
    def custom_fields(self):
        raw = self.custom_fields_raw
        if isinstance(raw, list):
            return raw
        if isinstance(raw, (bytes, str)) and raw:
            try:
                value = json.loads(raw)
                return value if isinstance(value, list) else []
            except Exception:
                return []
        return []

    @custom_fields.setter
    def custom_fields(self, value):
        self.custom_fields_raw = json.dumps(value or [])

class Custodian(Base):
    __tablename__ = "custodians"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    added_at = Column(DateTime(timezone=True), nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    onedrive_site_id = Column(String, nullable=True)
    person_lookup_overridden = Column(Boolean, nullable=False, default=False)
    name_email_review_required = Column(Boolean, nullable=False, default=False)
    name_email_review_reason = Column(Text, nullable=True)
    name_email_review_last_checked_at = Column(DateTime(timezone=True), nullable=True)

    holds_email = Column(Boolean, nullable=False, default=False)
    holds_onedrive = Column(Boolean, nullable=False, default=False)
    holds_gdrive = Column(Boolean, nullable=False, default=False)
    holds_box = Column(Boolean, nullable=False, default=False)
    holds_slack = Column(Boolean, nullable=False, default=False)
    holds_crashplan = Column(Boolean, nullable=False, default=False)
    holds_rubrik_restore = Column(Boolean, nullable=False, default=False)
    slack_user_id = Column(String(64), nullable=True)
    holds_email_pending = Column(Boolean, nullable=False, default=False)
    holds_onedrive_pending = Column(Boolean, nullable=False, default=False)
    holds_gdrive_pending = Column(Boolean, nullable=False, default=False)
    holds_box_pending = Column(Boolean, nullable=False, default=False)
    holds_slack_pending = Column(Boolean, nullable=False, default=False)
    holds_rubrik_restore_pending = Column(Boolean, nullable=False, default=False)
    holds_email_failed = Column(Boolean, nullable=False, default=False)
    holds_onedrive_failed = Column(Boolean, nullable=False, default=False)
    holds_gdrive_failed = Column(Boolean, nullable=False, default=False)
    holds_box_failed = Column(Boolean, nullable=False, default=False)
    holds_slack_failed = Column(Boolean, nullable=False, default=False)
    holds_rubrik_restore_failed = Column(Boolean, nullable=False, default=False)
    holds_email_released = Column(Boolean, nullable=False, default=False)
    holds_onedrive_released = Column(Boolean, nullable=False, default=False)
    holds_gdrive_released = Column(Boolean, nullable=False, default=False)
    holds_box_released = Column(Boolean, nullable=False, default=False)
    holds_slack_released = Column(Boolean, nullable=False, default=False)
    holds_rubrik_restore_released = Column(Boolean, nullable=False, default=False)

    employment_end_date = Column(String, nullable=True)
    employment_status = Column(String, nullable=True)
    employee_id = Column(String(128), nullable=True)
    person_first_name = Column(String, nullable=True)
    person_last_name = Column(String, nullable=True)
    person_department_id = Column(String(128), nullable=True)
    person_department = Column(String, nullable=True)
    person_title = Column(String, nullable=True)
    person_current_employee = Column(Boolean, nullable=True)
    person_lookup_last_at = Column(DateTime(timezone=True), nullable=True)
    ntp_status = Column(String, nullable=False, default="not sent")
    ntp_sent_at = Column(DateTime(timezone=True), nullable=True)
    ntp_acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    ntp_template_name = Column(String(255), nullable=True)
    ntp_not_required_reason = Column(Text, nullable=True)
    consent_status = Column(String, nullable=False, default="not sent")
    consent_not_required_reason = Column(Text, nullable=True)

    search_done = Column(Boolean, nullable=False, default=False)
    export_done = Column(Boolean, nullable=False, default=False)
    delivered_done = Column(Boolean, nullable=False, default=False)

    case = relationship("Case", back_populates="custodians")
    custom_preservation = relationship("CustodianPreservation", back_populates="custodian", cascade="all, delete-orphan")
    hold_memberships = relationship("HoldCustodian", back_populates="custodian", cascade="all, delete-orphan")
    ntp_tokens = relationship("NTPTargetToken", back_populates="custodian", cascade="all, delete-orphan")
    consents = relationship("CaseConsent", back_populates="custodian")


class CustodianPreservation(Base):
    __tablename__ = "custodian_preservation_sources"
    __table_args__ = (
        UniqueConstraint("custodian_id", "source_key", name="uq_custodian_preservation_source"),
    )
    id = Column(Integer, primary_key=True, index=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id", ondelete="CASCADE"), index=True, nullable=False)
    source_key = Column(String(80), nullable=False)
    source_label = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=False)
    pending = Column(Boolean, nullable=False, default=False)
    failed = Column(Boolean, nullable=False, default=False)
    released = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    custodian = relationship("Custodian", back_populates="custom_preservation")


class CaseHold(Base):
    __tablename__ = "case_holds"
    __table_args__ = (
        UniqueConstraint("case_id", "name", name="uq_case_hold_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active")
    sort_order = Column(Integer, nullable=False, default=0)
    ntp_template_name = Column(String(255), nullable=True)
    preservation_template_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="holds")
    custodian_memberships = relationship("HoldCustodian", back_populates="hold", cascade="all, delete-orphan")
    search_memberships = relationship("HoldSearch", back_populates="hold", cascade="all, delete-orphan")


class HoldCustodian(Base):
    __tablename__ = "hold_custodians"
    __table_args__ = (
        UniqueConstraint("hold_id", "custodian_id", name="uq_hold_custodian"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hold_id = Column(Integer, ForeignKey("case_holds.id", ondelete="CASCADE"), nullable=False, index=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id", ondelete="CASCADE"), nullable=False, index=True)
    ntp_status = Column(String(32), nullable=False, default="not sent")
    ntp_sent_at = Column(DateTime(timezone=True), nullable=True)
    ntp_acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    ntp_template_name = Column(String(255), nullable=True)
    ntp_not_required_reason = Column(Text, nullable=True)
    consent_status = Column(String(32), nullable=False, default="not sent")
    consent_not_required_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    hold = relationship("CaseHold", back_populates="custodian_memberships")
    custodian = relationship("Custodian", back_populates="hold_memberships")
    preservation_sources = relationship("HoldPreservationSource", back_populates="hold_custodian", cascade="all, delete-orphan")
    consents = relationship("CaseConsent", back_populates="hold_custodian")
    consent_proofs = relationship("CaseRequestConsentProof", back_populates="hold_custodian")
    ntp_tokens = relationship("NTPTargetToken", back_populates="hold_custodian")
    ntp_reminders = relationship("NTPReminder", back_populates="hold_custodian")


class HoldPreservationSource(Base):
    __tablename__ = "hold_preservation_sources"
    __table_args__ = (
        UniqueConstraint("hold_custodian_id", "source_key", name="uq_hold_custodian_source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hold_custodian_id = Column(Integer, ForeignKey("hold_custodians.id", ondelete="CASCADE"), nullable=False, index=True)
    source_key = Column(String(80), nullable=False)
    source_label = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="not_started")
    provider_reference = Column(String(512), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    hold_custodian = relationship("HoldCustodian", back_populates="preservation_sources")


class HoldSearch(Base):
    __tablename__ = "hold_searches"
    __table_args__ = (
        UniqueConstraint("hold_id", "search_id", name="uq_hold_search"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hold_id = Column(Integer, ForeignKey("case_holds.id", ondelete="CASCADE"), nullable=False, index=True)
    search_id = Column(Integer, ForeignKey("searches.id", ondelete="CASCADE"), nullable=False, index=True)
    status_search = Column(String, nullable=False, default="not performed")
    status_export = Column(String, nullable=False, default="not performed")
    status_delivery = Column(String, nullable=False, default="not performed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    hold = relationship("CaseHold", back_populates="search_memberships")
    search = relationship("Search", back_populates="hold_memberships")

class CaseRequestor(Base):
    __tablename__ = "case_requestors"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    requestor_group = Column(String, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", back_populates="requestors")
    user = relationship("User")


class RequestorGroupAccess(Base):
    __tablename__ = "requestor_group_access"

    id = Column(Integer, primary_key=True, index=True)
    source_group = Column(String(255), nullable=False, index=True)
    target_group = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RequestorGroup(Base):
    __tablename__ = "requestor_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    label = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Search(Base):
    __tablename__ = "searches"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String, nullable=False)

    keywords = Column(Text, nullable=True)
    senders = Column(Text, nullable=True)
    recipients = Column(Text, nullable=True)
    date_from = Column(String, nullable=True)
    date_to = Column(String, nullable=True)
    additional = Column(Text, nullable=True)

    status_search = Column(String, nullable=False, default="not performed")
    status_export = Column(String, nullable=False, default="not performed")
    # When true, export was completed via external sync while one or more assigned custodians lacked consent.
    export_without_consent = Column(Boolean, nullable=False, default=False)
    status_delivery = Column(String, nullable=False, default="not performed")

    custodian_ids = Column(Text, nullable=False, default="[]")  # JSON array of ints
    hold_memberships = relationship("HoldSearch", back_populates="search", cascade="all, delete-orphan")

class CaseNote(Base):
    __tablename__ = "case_notes"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    audience = Column(String(32), nullable=False, default="internal")
    author = Column(String(128), nullable=True)
    body = Column(Text, nullable=False)
    format = Column(String(16), nullable=False, default="plain")
    is_pinned = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    updated_at = Column(DateTime, nullable=False, default=_utcnow_naive)
    attachments = relationship("CaseNoteAttachment", back_populates="note", cascade="all, delete-orphan")


class CaseNoteAttachment(Base):
    __tablename__ = "case_note_attachments"

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("case_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    stored_filename = Column(String(255), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    uploaded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    note = relationship("CaseNote", back_populates="attachments")
    uploaded_by = relationship("User")


class SessionToken(Base):
    __tablename__ = "session_tokens"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    jti = Column(String(64), unique=True, nullable=False)
    token_hash = Column(String(128), nullable=False)
    user_agent = Column(String(256))
    ip = Column(String(64))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    jti = Column(String(64), unique=True, nullable=False)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    user_agent = Column(String(256))
    ip = Column(String(64))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    user_agent = Column(String(255), nullable=True)
    label = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="trusted_devices")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")


class CaseRequest(Base):
    __tablename__ = "case_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    case_name = Column(String, nullable=True, index=True)
    color = Column(String, nullable=True)
    payload = Column(Text, nullable=True)
    attachment_name = Column(String, nullable=True)
    attachment_path = Column(String, nullable=True)
    attachment_bytes = Column(Integer, nullable=False, default=0)
    consent_attachment_name = Column(String, nullable=True)
    consent_attachment_path = Column(String, nullable=True)
    consent_attachment_bytes = Column(Integer, nullable=False, default=0)
    requestor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    requestor_email = Column(String, nullable=True)
    ntp_all_sent = Column(Boolean, nullable=False, default=False)
    note = Column(Text, nullable=True)
    decline_reason = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("Case", foreign_keys=[case_id])
    requestor = relationship("User", foreign_keys=[requestor_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_id])
    consent_proofs = relationship("CaseRequestConsentProof", back_populates="case_request", cascade="all, delete-orphan")
    case_deleted = Column(Boolean, nullable=False, default=False)
    case_name_lookup = Column(
        Text,
        Computed("lower(trim(case_name))", persisted=True),
        nullable=True,
        index=True,
    )


class EmailIntakeTemplate(Base):
    __tablename__ = "email_intake_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    sender_pattern = Column(String(512), nullable=True)
    recipient_pattern = Column(String(512), nullable=True)
    subject_pattern = Column(String(512), nullable=True)
    body_markers = Column(Text, nullable=True)
    field_markers = Column(Text, nullable=True)
    default_values = Column(Text, nullable=True)
    hold_name = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    created_by = relationship("User", foreign_keys=[created_by_id])


class EmailIntakeCursor(Base):
    __tablename__ = "email_intake_cursors"
    __table_args__ = (
        UniqueConstraint("mailbox", "folder_id", name="uq_email_intake_cursor_mailbox_folder"),
    )

    id = Column(Integer, primary_key=True, index=True)
    mailbox = Column(String(320), nullable=False, index=True)
    folder_id = Column(String(512), nullable=False)
    delta_link = Column(Text, nullable=True)
    baseline_pending = Column(Boolean, nullable=False, default=True)
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmailIntakeMessage(Base):
    __tablename__ = "email_intake_messages"
    __table_args__ = (
        UniqueConstraint("mailbox", "graph_message_id", name="uq_email_intake_mailbox_message"),
    )

    id = Column(Integer, primary_key=True, index=True)
    mailbox = Column(String(320), nullable=False, index=True)
    graph_message_id = Column(String(1024), nullable=False)
    internet_message_id = Column(String(1024), nullable=True, index=True)
    change_key = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="received", index=True)
    template_id = Column(Integer, ForeignKey("email_intake_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    case_request_id = Column(Integer, ForeignKey("case_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    sender = Column(String(320), nullable=True, index=True)
    recipients = Column(Text, nullable=True)
    subject = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True, index=True)
    body_text = Column(Text, nullable=True)
    attachment_count = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    template = relationship("EmailIntakeTemplate")
    case_request = relationship("CaseRequest")

class CaseRequestConsentProof(Base):
    __tablename__ = "case_request_consent_proofs"

    id = Column(Integer, primary_key=True, index=True)
    case_request_id = Column(Integer, ForeignKey("case_requests.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    hold_custodian_id = Column(Integer, ForeignKey("hold_custodians.id", ondelete="SET NULL"), nullable=True, index=True)
    custodian_name = Column(String, nullable=True)
    custodian_email = Column(String, nullable=True)
    stored_filename = Column(String(255), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    proof_type = Column(String(32), nullable=False, default="standard", server_default="standard")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    case_request = relationship("CaseRequest", back_populates="consent_proofs")
    case = relationship("Case")
    hold_custodian = relationship("HoldCustodian", back_populates="consent_proofs")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])


class CaseConsent(Base):
    __tablename__ = "case_consents"
    __table_args__ = (
        UniqueConstraint("provider", "envelope_id", name="uq_case_consents_provider_request_id"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id", ondelete="SET NULL"), nullable=True, index=True)
    hold_custodian_id = Column(Integer, ForeignKey("hold_custodians.id", ondelete="SET NULL"), nullable=True, index=True)
    custodian_name = Column(Text, nullable=True)
    custodian_email = Column(Text, nullable=True)
    provider = Column(String(64), nullable=False, default="docusign", server_default="docusign", index=True)
    envelope_id = Column(Text, nullable=False, index=True)
    status = Column(Text, nullable=True)
    record_type = Column(Text, nullable=True)
    date_from = Column(Text, nullable=True)
    date_to = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    last_resent_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("Case", back_populates="consents")
    custodian = relationship("Custodian", back_populates="consents")
    hold_custodian = relationship("HoldCustodian", back_populates="consents")

    @property
    def request_id(self) -> str:
        return self.envelope_id

    @property
    def hold_id(self) -> int | None:
        return self.hold_custodian.hold_id if self.hold_custodian is not None else None


class NTPTemplate(Base):
    __tablename__ = "ntp_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    cc = Column(Text, nullable=True)
    bcc = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    high_importance = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    groups = relationship("NTPTemplateGroup", back_populates="template", cascade="all, delete-orphan")

class NTPTemplateGroup(Base):
    __tablename__ = "ntp_template_groups"
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("ntp_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    group_name = Column(String(255), nullable=False)
    template = relationship("NTPTemplate", back_populates="groups")


class NTPTargetToken(Base):
    __tablename__ = "ntp_tokens"
    id = Column(Integer, primary_key=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id", ondelete="CASCADE"), nullable=False, index=True)
    hold_custodian_id = Column(Integer, ForeignKey("hold_custodians.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("ntp_templates.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)

    custodian = relationship("Custodian", back_populates="ntp_tokens")
    hold_custodian = relationship("HoldCustodian", back_populates="ntp_tokens")


class NTPReminder(Base):
    __tablename__ = "ntp_reminders"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    custodian_id = Column(Integer, ForeignKey("custodians.id", ondelete="CASCADE"), nullable=False, index=True)
    hold_custodian_id = Column(Integer, ForeignKey("hold_custodians.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("ntp_templates.id", ondelete="SET NULL"), nullable=True)
    token_id = Column(Integer, ForeignKey("ntp_tokens.id", ondelete="CASCADE"), nullable=False, unique=True)
    variables = Column(Text, nullable=True)
    interval_days = Column(Integer, nullable=False, default=14)
    next_send_at = Column(DateTime(timezone=True), nullable=False)
    stop_after = Column(DateTime(timezone=True), nullable=False)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    send_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("Case")
    custodian = relationship("Custodian")
    hold_custodian = relationship("HoldCustodian", back_populates="ntp_reminders")
    template = relationship("NTPTemplate")
    token = relationship("NTPTargetToken")


class AccountRegistrationRequest(Base):
    __tablename__ = "account_registration_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    declined_reason = Column(Text, nullable=True)
    invite_token_hash = Column(String(128), nullable=True, unique=True, index=True)
    invite_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    invite_totp_secret = Column(String(64), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    sso_subject = Column("sso_subject", String(255), nullable=True, index=True)
    requestor_group = Column(String(255), nullable=True)
    role = Column(String(32), nullable=True)

    approved_by = relationship("User")




