from app import integration_settings, person_lookup


def test_http_provider_is_selected_for_api_alias(monkeypatch):
    monkeypatch.setattr(
        person_lookup,
        "load_integration_settings",
        lambda: {
            "person_lookup_provider": "idp",
            "enabled_integrations": {"person_lookup": True},
        },
    )

    provider = person_lookup.get_person_lookup_provider()

    assert isinstance(provider, person_lookup.HttpPersonLookupProvider)


def test_registered_person_lookup_provider_is_selected(monkeypatch):
    class ExampleProvider:
        name = "example_hr"

        def lookup(self, query, *, email=None):
            return ([{"display_name": "Example Person", "source": self.name}], None)

    person_lookup.register_person_lookup_provider(
        "example_hr",
        ExampleProvider,
        aliases=("example_idp",),
    )
    monkeypatch.setattr(
        person_lookup,
        "load_integration_settings",
        lambda: {
            "person_lookup_provider": "example_idp",
            "enabled_integrations": {"person_lookup": True},
        },
    )
    try:
        provider = person_lookup.get_person_lookup_provider()
        results, error = provider.lookup("Example")

        assert isinstance(provider, ExampleProvider)
        assert results[0]["source"] == "example_hr"
        assert error is None
        assert "example_idp" in person_lookup.person_lookup_provider_names()
    finally:
        person_lookup.unregister_person_lookup_provider("example_hr")


def test_csv_provider_loads_and_normalizes_people(tmp_path):
    csv_path = tmp_path / "people.csv"
    csv_path.write_text(
        "display_name,email,employee_id,department,job_title,separation_date\n"
        "Taylor Analyst,taylor@example.edu,E12345,Legal,Analyst,\n",
        encoding="utf-8",
    )

    provider = person_lookup.CsvPersonLookupProvider(str(csv_path))
    results, error = provider.lookup("E12345")

    assert error is None
    assert results == [
        {
            "display_name": "Taylor Analyst",
            "first_name": None,
            "middle_name": None,
            "last_name": None,
            "email": "taylor@example.edu",
            "external_id": "E12345",
            "department": "Legal",
            "title": "Analyst",
            "separation_date": None,
            "separation_status": "current",
            "source": "csv",
            "department_name": "Legal",
            "job_title_official": "Analyst",
            "employee_end_date": None,
            "current_employee": True,
        }
    ]

def test_normalize_person_row_accepts_common_hr_field_names():
    row = person_lookup._normalize_person_row(
        {
            "displayName": "Taylor Analyst",
            "mail": "taylor@example.edu",
            "employeeId": "E12345",
            "departmentName": "Legal",
            "jobTitle": "Analyst",
            "employmentStatus": "current",
        },
        "http",
    )

    assert row["display_name"] == "Taylor Analyst"
    assert row["email"] == "taylor@example.edu"
    assert row["external_id"] == "E12345"
    assert row["department"] == "Legal"
    assert row["title"] == "Analyst"
    assert row["separation_status"] == "current"
    assert row["source"] == "http"



def test_builtin_person_lookup_providers_are_registered():
    assert {
        "none",
        "csv",
        "static",
        "http",
        "api",
        "idp",
        "hr",
    } <= person_lookup.person_lookup_provider_names(include_none=True)

def test_lookup_refresh_routes_batch_session_through_selected_provider(monkeypatch):
    from app import case_request_lookup_refresh as refresh

    session = object()
    calls = []

    monkeypatch.setattr(refresh, "person_lookup_enabled", lambda: True)

    def configured_lookup(query, *, email=None, session=None):
        calls.append((query, email, session))
        return ([{"display_name": "Example Person"}], None)

    monkeypatch.setattr(refresh, "_run_configured_person_lookup", configured_lookup)

    matches, error = refresh.lookup_matches_for_identity(
        "Example Person",
        cursor=session,
    )
    assert error is None
    assert matches == [{"display_name": "Example Person"}]
    assert calls == [("Example Person", None, session)]


def test_normalize_person_row_uses_configured_nested_field_paths():
    row = person_lookup._normalize_person_row(
        {
            "profile": {
                "preferred": "Jordan Counsel",
                "given": "Jordan",
                "family": "Counsel",
                "contact": {"work": "jordan@example.edu"},
            },
            "work": {
                "number": "EMP-204",
                "unit": "Legal",
                "role": "Counsel",
                "ended": "2026-06-30",
                "state": "separated",
            },
        },
        "http",
        {
            "display_name": "profile.preferred",
            "first_name": "profile.given",
            "last_name": "profile.family",
            "email": "profile.contact.work",
            "external_id": "work.number",
            "department": "work.unit",
            "title": "work.role",
            "separation_date": "work.ended",
            "separation_status": "work.state",
        },
    )

    assert row["display_name"] == "Jordan Counsel"
    assert row["first_name"] == "Jordan"
    assert row["last_name"] == "Counsel"
    assert row["email"] == "jordan@example.edu"
    assert row["external_id"] == "EMP-204"
    assert row["department"] == "Legal"
    assert row["title"] == "Counsel"
    assert row["separation_date"] == "2026-06-30"
    assert row["separation_status"] == "separated"
    assert row["current_employee"] is False

def test_person_lookup_limit_uses_app_managed_settings(monkeypatch):
    monkeypatch.setenv("PERSON_LOOKUP_MAX_CUSTODIANS", "999")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "integration_configs": {"person_lookup": {"max_custodians": "25"}},
        },
    )

    assert person_lookup.person_lookup_max_custodians() == 25