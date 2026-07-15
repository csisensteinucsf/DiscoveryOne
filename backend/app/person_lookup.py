from __future__ import annotations

import csv
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from .institution import load_integration_settings
from .integration_settings import config_value
from .person_lookup_registry import (
    PersonLookupProvider,
    get_person_lookup_provider_factory,
    register_person_lookup_provider,
    registered_person_lookup_provider_names,
    unregister_person_lookup_provider,
)


@dataclass
class NormalizedPerson:
    display_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    external_id: str | None = None
    department: str | None = None
    title: str | None = None
    separation_date: str | None = None
    separation_status: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        status = (self.separation_status or "").strip().lower()
        current_employee = not self.separation_date and not status.startswith(("separated", "inactive", "terminated"))
        # Compatibility keys used by existing frontend employment displays.
        data.update(
            {
                "department_name": self.department,
                "job_title_official": self.title,
                "employee_end_date": self.separation_date,
                "current_employee": current_employee,
            }
        )
        return data


class NoopPersonLookupProvider:
    name = "none"

    def lookup(self, query: str, *, email: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        return ([], None)


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _pick(row: dict[str, Any], *names: str) -> str | None:
    normalized = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value not in (None, ""):
            return _clean(value)
    return None


PERSON_FIELD_NAMES = (
    "display_name",
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "external_id",
    "department",
    "title",
    "separation_date",
    "separation_status",
)


def _mapped_value(row: dict[str, Any], mappings: dict[str, str], field: str, *aliases: str) -> str | None:
    path = str(mappings.get(field) or "").strip()
    if path:
        mapped = _extract_path(row, path)
        if mapped not in (None, ""):
            return _clean(mapped)
    return _pick(row, *aliases)


def _person_field_mappings() -> dict[str, str]:
    return {
        field: config_value("person_lookup", f"field_{field}", [], "")
        for field in PERSON_FIELD_NAMES
    }


def _normalize_person_row(
    row: dict[str, Any],
    source: str,
    mappings: dict[str, str] | None = None,
) -> dict[str, Any]:
    mappings = mappings or {}
    first = _mapped_value(row, mappings, "first_name", "first_name", "first", "given_name", "givenname")
    middle = _mapped_value(row, mappings, "middle_name", "middle_name", "middle")
    last = _mapped_value(row, mappings, "last_name", "last_name", "last", "surname", "family_name", "familyname")
    display_name = _mapped_value(row, mappings, "display_name", "display_name", "displayname", "name", "full_name", "fullname")
    if not display_name:
        display_name = " ".join(part for part in [first, middle, last] if part) or None
    separation_date = _mapped_value(row, mappings, "separation_date", "separation_date", "employment_end_date", "employee_end_date", "end_date", "termination_date")
    separation_status = _mapped_value(row, mappings, "separation_status", "separation_status", "employment_status", "status", "employee_status")
    if not separation_status:
        separation_status = "separated" if separation_date else "current"
    person = NormalizedPerson(
        display_name=display_name,
        first_name=first,
        middle_name=middle,
        last_name=last,
        email=_mapped_value(row, mappings, "email", "email", "mail", "primary_email", "user_principal_name", "userprincipalname", "upn"),
        external_id=_mapped_value(row, mappings, "external_id", "external_id", "person_id", "employee_id", "employeeid", "employee_number", "id"),
        department=_mapped_value(row, mappings, "department", "department", "department_name", "departmentname", "org_unit", "organization"),
        title=_mapped_value(row, mappings, "title", "title", "job_title", "jobtitle", "job_title_official"),
        separation_date=separation_date,
        separation_status=separation_status,
        source=source,
    )
    return person.to_dict()


class CsvPersonLookupProvider:
    name = "csv"

    def __init__(self, path: str | None = None):
        self.path = path or config_value("person_lookup", "csv_path", ["PERSON_LOOKUP_CSV_PATH", "PERSON_LOOKUP_STATIC_PATH"])
        self.field_mappings = _person_field_mappings()
        self._rows: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._rows is not None:
            return self._rows
        if not self.path:
            self._rows = []
            return self._rows
        path = Path(self.path)
        if not path.exists() or not path.is_file():
            self._rows = []
            return self._rows
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self._rows = [self._normalize_row(row) for row in reader]
        return self._rows

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return _normalize_person_row(row, self.name, self.field_mappings)

    def lookup(self, query: str, *, email: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        rows = self._load()
        if not rows:
            return ([], "Person lookup CSV is not configured." if not self.path else None)

        email_norm = _lower(email)
        query_norm = _lower(query)
        if email_norm and "@" in email_norm:
            return ([row for row in rows if _lower(row.get("email")) == email_norm], None)
        if query_norm and "@" in query_norm:
            return ([row for row in rows if _lower(row.get("email")) == query_norm], None)
        if not query_norm:
            return ([], "Enter a name, email address, or Employee ID for lookup.")

        matches: list[dict[str, Any]] = []
        for row in rows:
            haystack = " ".join(
                filter(
                    None,
                    [
                        _lower(row.get("display_name")),
                        _lower(row.get("first_name")),
                        _lower(row.get("middle_name")),
                        _lower(row.get("last_name")),
                        _lower(row.get("email")),
                        _lower(row.get("external_id")),
                    ],
                )
            )
            if query_norm == _lower(row.get("external_id")):
                matches.append(row)
            elif query_norm in haystack:
                matches.append(row)
        return (matches[:50], None)


def _extract_path(data: Any, path: str) -> Any:
    current = data
    for part in [p for p in (path or "").split(".") if p]:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


class HttpPersonLookupProvider:
    name = "http"

    def __init__(self):
        self.url = config_value("person_lookup", "http_url", "PERSON_LOOKUP_HTTP_URL")
        self.method = config_value("person_lookup", "http_method", "PERSON_LOOKUP_HTTP_METHOD", "GET").upper()
        self.query_param = config_value("person_lookup", "http_query_param", "PERSON_LOOKUP_HTTP_QUERY_PARAM", "query") or "query"
        self.email_param = config_value("person_lookup", "http_email_param", "PERSON_LOOKUP_HTTP_EMAIL_PARAM", "email") or "email"
        self.results_path = config_value("person_lookup", "http_results_path", "PERSON_LOOKUP_HTTP_RESULTS_PATH", "results")
        try:
            self.timeout = max(
                1.0,
                min(
                    120.0,
                    float(config_value("person_lookup", "http_timeout_seconds", "PERSON_LOOKUP_HTTP_TIMEOUT_SECONDS", "10") or "10"),
                ),
            )
        except (TypeError, ValueError):
            self.timeout = 10.0
        self.auth_header = config_value("person_lookup", "http_auth_header", "PERSON_LOOKUP_HTTP_AUTH_HEADER")
        self.auth_value = config_value("person_lookup", "http_auth_value", "PERSON_LOOKUP_HTTP_AUTH_VALUE")
        self.field_mappings = _person_field_mappings()

    def lookup(self, query: str, *, email: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        if not self.url:
            return ([], "Person lookup API is not configured.")
        payload = {self.query_param: query or ""}
        if email:
            payload[self.email_param] = email
        headers = {}
        if self.auth_header and self.auth_value:
            headers[self.auth_header] = self.auth_value
        try:
            with httpx.Client(timeout=self.timeout) as client:
                if self.method == "POST":
                    response = client.post(self.url, json=payload, headers=headers)
                else:
                    response = client.get(self.url, params=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return ([], f"Person lookup API request failed: {exc}")

        rows = _extract_path(data, self.results_path) if self.results_path else data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return ([], "Person lookup API response did not contain a result list.")
        normalized = [
            _normalize_person_row(row, self.name, self.field_mappings)
            for row in rows
            if isinstance(row, dict)
        ]
        return (normalized[:50], None)


register_person_lookup_provider(
    "csv",
    CsvPersonLookupProvider,
    aliases=("static",),
    replace=True,
)
register_person_lookup_provider(
    "http",
    HttpPersonLookupProvider,
    aliases=("api", "idp", "hr"),
    replace=True,
)


def person_lookup_provider_names(*, include_none: bool = False) -> set[str]:
    return registered_person_lookup_provider_names(
        include_none=include_none,
        include_aliases=True,
    )


def person_lookup_provider_name() -> str:
    return str(load_integration_settings().get("person_lookup_provider") or "none").strip().lower()


def person_lookup_enabled() -> bool:
    settings = load_integration_settings()
    provider = str(settings.get("person_lookup_provider") or "none").strip().lower()
    enabled = (settings.get("enabled_integrations") or {}).get("person_lookup")
    return provider != "none" and bool(enabled)


def person_lookup_max_custodians() -> int:
    raw = config_value("person_lookup", "max_custodians", "PERSON_LOOKUP_MAX_CUSTODIANS", "100")
    try:
        value = int(raw or "100")
    except (TypeError, ValueError):
        value = 100
    return max(1, min(1000, value))


def get_person_lookup_provider() -> PersonLookupProvider:
    if not person_lookup_enabled():
        return NoopPersonLookupProvider()
    factory = get_person_lookup_provider_factory(person_lookup_provider_name())
    if factory is None:
        return NoopPersonLookupProvider()
    return factory()



def person_lookup_provider_readiness_error() -> str | None:
    provider = get_person_lookup_provider()
    readiness = getattr(provider, "readiness_error", None)
    if not callable(readiness):
        return None
    return readiness()


@contextmanager
def person_lookup_batch_session():
    provider = get_person_lookup_provider()
    batch_session = getattr(provider, "batch_session", None)
    if not callable(batch_session):
        yield None
        return
    with batch_session() as session:
        yield session
