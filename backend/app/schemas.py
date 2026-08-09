from typing import Any, Dict, List
from typing import Optional, List, Literal
from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict, EmailStr, field_validator

# ---------------- Users ----------------

UserRole = Literal["sys_admin", "analyst", "requestor", "tech", "tester"]
NTPStatus = Literal["not sent", "sent", "acknowledged", "silent"]
ConsentStatus = Literal["not sent", "sent", "received", "implied", "awoc"]

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_id: Optional[str] = None
    requestor_group: Optional[str] = None
    user_theme: Optional[str] = None
    local_auth_only: Optional[bool] = None
    is_active: Optional[bool] = None

class UserCreate(UserBase):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    password: Optional[str] = Field(default=None, min_length=8)
    # legacy flag kept for backward compatibility; UI should prefer 'role'
    is_admin: Optional[bool] = None
    role: Optional[UserRole] = None

class UserRead(UserBase):
    id: int
    is_admin: bool
    local_auth_only: bool = False
    is_active: bool = True
    role: UserRole = "analyst"
    model_config = ConfigDict(from_attributes=True)  # pydantic v2

class AnalystRead(BaseModel):
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_id: Optional[str] = None
    role: Optional[UserRole] = None
    requestor_group: Optional[str] = None
    local_auth_only: Optional[bool] = None
    is_active: Optional[bool] = None
    # legacy flag kept for backward compatibility
    is_admin: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)
    model_config = ConfigDict(from_attributes=True)

class PasswordReset(BaseModel):
    # accept either key from the client
    password: Optional[str] = Field(default=None, min_length=8)
    new_password: Optional[str] = Field(default=None, min_length=8)

    def resolved(self) -> str:
        # prefer 'password', fall back to 'new_password'
        return (self.password or self.new_password or "").strip()


# ---------------- Custodians ----------------
# Persisted workflow fields live on Base so they're returned on reads and can be set on create.

class CustodianCustomPreservation(BaseModel):
    source_key: str
    source_label: Optional[str] = None
    active: bool = False
    pending: bool = False
    failed: bool = False
    released: bool = False
    model_config = ConfigDict(from_attributes=True)


class CustodianBase(BaseModel):
    name: str
    email: Optional[str] = None
    notes: Optional[str] = None
    person_lookup_overridden: bool = False
    name_email_review_required: bool = False
    name_email_review_reason: Optional[str] = None
    name_email_review_last_checked_at: Optional[datetime] = None

    # persisted workflow fields
    holds_email: bool = False
    holds_onedrive: bool = False
    holds_gdrive: bool = False
    holds_box: bool = False
    holds_slack: bool = False
    holds_rubrik_restore: bool = False
    holds_email_pending: bool = False
    holds_onedrive_pending: bool = False
    holds_gdrive_pending: bool = False
    holds_box_pending: bool = False
    holds_slack_pending: bool = False
    holds_rubrik_restore_pending: bool = False
    holds_email_failed: bool = False
    holds_onedrive_failed: bool = False
    holds_gdrive_failed: bool = False
    holds_box_failed: bool = False
    holds_slack_failed: bool = False
    holds_rubrik_restore_failed: bool = False
    holds_email_released: bool = False
    holds_onedrive_released: bool = False
    holds_gdrive_released: bool = False
    holds_box_released: bool = False
    holds_slack_released: bool = False
    holds_rubrik_restore_released: bool = False
    custom_preservation: List[CustodianCustomPreservation] = Field(default_factory=list)

    ntp_status: NTPStatus = "not sent"
    ntp_not_required_reason: Optional[str] = None
    consent_status: ConsentStatus = "not sent"
    consent_not_required_reason: Optional[str] = None

    search_done: bool = False
    export_done: bool = False
    delivered_done: bool = False

    employment_end_date: Optional[str] = None
    employment_status: Optional[str] = None
    external_id: Optional[str] = None
    employee_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department_id: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    current_employee: Optional[bool] = None
    person_lookup_last_at: Optional[datetime] = None

class CustodianCreate(CustodianBase):
    hold_ids: list[int] = Field(default_factory=list)

class CustodianBulkCreateRequest(BaseModel):
    custodians: list[CustodianCreate]
    hold_ids: list[int] = Field(default_factory=list)

class CustodianUpdate(BaseModel):
    # all optional for partial updates
    name: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    employment_end_date: Optional[str] = None
    employment_status: Optional[str] = None
    person_lookup_overridden: Optional[bool] = None
    name_email_review_required: Optional[bool] = None
    name_email_review_reason: Optional[str] = None
    name_email_review_last_checked_at: Optional[datetime] = None
    external_id: Optional[str] = None
    employee_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    department_id: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    current_employee: Optional[bool] = None
    person_lookup_last_at: Optional[datetime] = None

    holds_email: Optional[bool] = None
    holds_onedrive: Optional[bool] = None
    holds_gdrive: Optional[bool] = None
    holds_box: Optional[bool] = None
    holds_slack: Optional[bool] = None
    holds_rubrik_restore: Optional[bool] = None
    holds_email_pending: Optional[bool] = None
    holds_onedrive_pending: Optional[bool] = None
    holds_gdrive_pending: Optional[bool] = None
    holds_box_pending: Optional[bool] = None
    holds_slack_pending: Optional[bool] = None
    holds_rubrik_restore_pending: Optional[bool] = None
    holds_email_failed: Optional[bool] = None
    holds_onedrive_failed: Optional[bool] = None
    holds_gdrive_failed: Optional[bool] = None
    holds_box_failed: Optional[bool] = None
    holds_slack_failed: Optional[bool] = None
    holds_rubrik_restore_failed: Optional[bool] = None
    holds_email_released: Optional[bool] = None
    holds_onedrive_released: Optional[bool] = None
    holds_gdrive_released: Optional[bool] = None
    holds_box_released: Optional[bool] = None
    holds_slack_released: Optional[bool] = None
    holds_rubrik_restore_released: Optional[bool] = None
    custom_preservation: Optional[List[CustodianCustomPreservation]] = None

    ntp_status: Optional[NTPStatus] = None
    ntp_not_required_reason: Optional[str] = None
    consent_status: Optional[ConsentStatus] = None
    consent_not_required_reason: Optional[str] = None

    search_done: Optional[bool] = None
    export_done: Optional[bool] = None
    delivered_done: Optional[bool] = None

class CustodianRead(CustodianBase):
    id: int
    created_at: Optional[datetime] = None
    added_at: Optional[datetime] = None
    ntp_sent_at: Optional[datetime] = None
    ntp_acknowledged_at: Optional[datetime] = None
    ntp_template_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class CustodianBulkCreateResponse(BaseModel):
    created: list[CustodianRead] = Field(default_factory=list)
    created_count: int = 0
    duplicate_count: int = 0
    failed_count: int = 0
    errors: list[str] = Field(default_factory=list)


class CustodianBulkUpdateItem(BaseModel):
    id: int
    patch: CustodianUpdate


class CustodianBulkUpdateRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    patch: Optional[CustodianUpdate] = None
    updates: list[CustodianBulkUpdateItem] = Field(default_factory=list)


class CustodianBulkUpdateResponse(BaseModel):
    updated: list[CustodianRead] = Field(default_factory=list)
    updated_count: int = 0
    errors: list[str] = Field(default_factory=list)

# ---------------- Cases ----------------

class CaseStatus(BaseModel):
    hold: bool = False
    ntp: Literal["none", "partial", "full"] = "none"
    consent: Literal["none", "partial", "full"] = "none"
    search: bool = False
    export: bool = False
    delivered: bool = False

class CaseRequestTicketEntry(BaseModel):
    id: str
    category: str
    ticket: str = ""
    created_at: Optional[datetime] = None
    case_hold_id: Optional[int] = None
    custodian_id: Optional[int] = None
    custodian_name: Optional[str] = None
    custodian_email: Optional[str] = None
    sys_id: Optional[str] = None
    status: Optional[str] = None
    ticket_status: Optional[str] = None
    assigned_to_sys_id: Optional[str] = None
    assigned_to_display: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_email: Optional[str] = None
    model_config = ConfigDict(extra='allow')

class CaseRequestTicketCustodian(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    model_config = ConfigDict(extra='ignore')

class ExternalTicketTimeWindow(BaseModel):
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    model_config = ConfigDict(extra='ignore')

class ExternalTicketRequest(BaseModel):
    category: str
    entry_id: Optional[str] = None
    case_hold_id: Optional[int] = None
    custodian_id: Optional[int] = None
    custodian_name: Optional[str] = None
    custodian_email: Optional[str] = None
    bulk_custodians: Optional[list[CaseRequestTicketCustodian]] = None
    access_log_employee_id: Optional[str] = None
    access_log_request_notes: Optional[str] = None
    access_log_time_windows: Optional[list[ExternalTicketTimeWindow]] = None

class ExternalTicketResponse(BaseModel):
    ticket_number: str
    sys_id: Optional[str] = None
    entry_id: Optional[str] = None


class ExternalTicketStatus(BaseModel):
    entry_id: str
    category: str
    ticket: str
    sys_id: Optional[str] = None
    status: Optional[str] = None
    is_closed: bool = False
    link: Optional[str] = None
    assigned_to_sys_id: Optional[str] = None
    assigned_to_display: Optional[str] = None
    assigned_to_email: Optional[str] = None


class ExternalTicketEmailRequest(BaseModel):
    entry_id: str


# Backward-compatible schema names for older clients/tests and legacy route metadata.
ServiceNowTicketTimeWindow = ExternalTicketTimeWindow
ServiceNowTicketRequest = ExternalTicketRequest
ServiceNowTicketResponse = ExternalTicketResponse
ServiceNowTicketStatus = ExternalTicketStatus
ServiceNowTicketEmailRequest = ExternalTicketEmailRequest

class TicketSelfHealResponse(BaseModel):
    ok: bool = True
    updated: bool = False
    prior_count: int = 0
    after_count: int = 0
    added_count: int = 0


class HelpVideoBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    description: Optional[str] = Field(default=None, max_length=2000)


class HelpVideoCreate(HelpVideoBase):
    pass


class HelpVideoRead(HelpVideoBase):
    id: int
    created_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class PreservationHoldRequest(BaseModel):
    custodian_ids: List[int] = Field(default_factory=list)
    case_hold_id: Optional[int] = Field(default=None, ge=1)
    included_sources: Optional[List[str]] = None
    delete_hold_policy: bool = False
    # Optional: allow provider adapters to wait for external source state.
    # 0 means "use the provider's default quick verification only".
    verify_timeout_seconds: float = 0.0


# Backward-compatible name for existing API clients and extensions.
PurviewHoldRequest = PreservationHoldRequest


class CaseConsent(BaseModel):
    id: int
    case_id: Optional[int] = None
    custodian_id: Optional[int] = None
    hold_id: Optional[int] = None
    hold_custodian_id: Optional[int] = None
    custodian_name: Optional[str] = None
    custodian_email: Optional[str] = None
    provider: str
    request_id: str
    envelope_id: str
    status: Optional[str] = None
    record_type: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sent_at: Optional[datetime] = None
    last_resent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    proof_downloaded: bool = False
    proof_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class CaseRequestorEntry(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    email: str
    requestor_group: Optional[str] = None
    is_primary: bool = False
    model_config = ConfigDict(from_attributes=True)

class CaseBase(BaseModel):
    name: str = Field(min_length=2, description="eDiscovery Case Name")
    legal_case_name: Optional[str] = None
    is_ler_hr: bool = False
    servicenow_inc_number: Optional[str] = None
    claimant: Optional[str] = None
    ler_representative: Optional[str] = None
    internal_counsel: Optional[str] = Field(default=None, max_length=500)
    outside_counsel: Optional[str] = Field(default=None, max_length=500)
    matter_number: Optional[str] = Field(default=None, max_length=128)
    requestor: Optional[str] = None
    requestors: List[CaseRequestorEntry] = Field(default_factory=list)
    analyst_id: Optional[int] = None
    closed: bool = False
    is_private: bool = False
    is_test_case: bool = False
    color: Optional[str] = None
    description: Optional[str] = None
    rubrik_restore_ticket: Optional[str] = None
    box_hold_ticket: Optional[str] = None
    request_ticket_entries: Optional[List[CaseRequestTicketEntry]] = None
    is_active_case: bool = False
    start_date: Optional[date] = None
    closure_nag_days: Optional[int] = Field(default=None, ge=1, le=3650, description="Days between closure reminders")
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("start_date", mode="before")
    @classmethod
    def blank_start_date_as_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

class CaseCreate(CaseBase):
    case_template_id: Optional[int] = Field(default=None, ge=1)

class CaseRead(CaseBase):
    id: int
    case_template_id: Optional[int] = None
    analyst_name: Optional[str] = None
    servicenow_inc_link: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    status: Optional[CaseStatus] = None
    notes_internal_count: int = 0
    notes_requestor_count: int = 0
    notes_ticket_count: int = 0
    consent_envelope_count: int = 0
    consent_proof_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class CaseTemplateFieldRule(BaseModel):
    visible: bool = True
    required: bool = False


class CaseTemplateCustomField(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    field_type: Literal["text", "textarea", "number", "date", "checkbox", "select"] = "text"
    required: bool = False
    options: List[str] = Field(default_factory=list)
    default_value: Any = None

class CaseTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    enabled: bool = True
    is_default: bool = False
    sort_order: int = Field(default=100, ge=0, le=100000)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    field_rules: Dict[str, CaseTemplateFieldRule] = Field(default_factory=dict)

    custom_fields: List[CaseTemplateCustomField] = Field(default_factory=list)

class CaseTemplateCreate(CaseTemplateBase):
    pass


class CaseTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)
    defaults: Optional[Dict[str, Any]] = None
    field_rules: Optional[Dict[str, CaseTemplateFieldRule]] = None

    custom_fields: Optional[List[CaseTemplateCustomField]] = None

class CaseTemplateRead(CaseTemplateBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CaseUpdate(BaseModel):
    # All fields optional for partial updates (used by PUT)
    name: Optional[str] = Field(default=None, min_length=2)
    legal_case_name: Optional[str] = None
    is_ler_hr: Optional[bool] = None
    servicenow_inc_number: Optional[str] = None
    claimant: Optional[str] = None
    ler_representative: Optional[str] = None
    internal_counsel: Optional[str] = Field(default=None, max_length=500)
    outside_counsel: Optional[str] = Field(default=None, max_length=500)
    matter_number: Optional[str] = Field(default=None, max_length=128)
    requestor: Optional[str] = None
    requestors: Optional[List[CaseRequestorEntry]] = None
    analyst_id: Optional[int] = None
    closed: Optional[bool] = None
    is_private: Optional[bool] = None
    is_test_case: Optional[bool] = None
    color: Optional[str] = None
    description: Optional[str] = None
    rubrik_restore_ticket: Optional[str] = None
    box_hold_ticket: Optional[str] = None
    request_ticket_entries: Optional[List[CaseRequestTicketEntry]] = None
    is_active_case: Optional[bool] = None
    start_date: Optional[str] = None
    closure_nag_days: Optional[int] = Field(default=None, ge=1, le=3650)
    custom_fields: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)


# ---- Searches ----
class SearchBase(BaseModel):
    name: str
    keywords: str | None = None
    senders: str | None = None
    recipients: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    additional: str | None = None
    status_search: str = "not performed"
    status_export: str = "not performed"
    export_without_consent: bool = False
    status_delivery: str = "not performed"
    custodian_ids: list[int] = Field(default_factory=list)
    hold_ids: list[int] = Field(default_factory=list)

class SearchCreate(SearchBase):
    pass

class SearchUpdate(BaseModel):
    name: str | None = None
    keywords: str | None = None
    senders: str | None = None
    recipients: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    additional: str | None = None
    status_search: str | None = None
    status_export: str | None = None
    export_without_consent: bool | None = None
    status_delivery: str | None = None
    custodian_ids: list[int] | None = None
    hold_ids: list[int] | None = None

class SearchRead(SearchBase):
    id: int
    case_id: int
    model_config = ConfigDict(from_attributes=True)

class OkResponse(BaseModel):
    ok: bool = True
    model_config = ConfigDict(extra='ignore')

class SettingsOut(BaseModel):
    theme: str | None = None
    logo_id: str | int | None = None
    model_config = ConfigDict(extra='ignore')

class LogoOut(BaseModel):
    id: str | int | None = None
    name: str | None = None
    url: str | None = None
    content_type: str | None = None
    size: int | None = None
    model_config = ConfigDict(extra='ignore')


class SuggestNameResponse(BaseModel):
    name: str
    model_config = ConfigDict(extra='ignore')
