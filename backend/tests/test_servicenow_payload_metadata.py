from app import servicenow


def _config():
    return servicenow.ServiceNowConfig(
        base_url="https://example.service-now.com",
        table="incident",
        auth_type="basic",
        use_import_api=False,
        username="user",
        password="pass",
        client_id=None,
        client_secret=None,
        token_url=None,
        scope=None,
        customer_id="discoveryone",
        source_system="discoveryone",
        status_table="incident",
    )


def test_servicenow_payload_includes_generic_access_log_context(monkeypatch):
    monkeypatch.setattr(
        servicenow,
        "_category_config",
        lambda: {
            "ehr_access_logs": {
                "short_description": "EHR Access Logs",
                "assignment_group": "Audit Team",
                "symptom": "Inquiry",
                "incident_keyword": "EHR_Access_Logs",
                "request_type": "EHR access log request",
                "link_label": "Case link",
            }
        },
    )

    payload = servicenow._build_payload(
        "ehr_access_logs",
        _config(),
        case_name="Case A",
        case_link="https://d1.example/cases/1",
        custodian_name="Jane Doe",
        custodian_email="jane@example.edu",
        customer_id_override="12345",
        extra_context={
            "access_log_employee_id": "E12345",
            "access_log_request_notes": "Need login and export activity.",
            "access_log_time_windows": [
                {"date": "2026-07-01", "start_time": "08:00", "end_time": "12:00"},
                {"date": "2026-07-02", "start_time": "13:00", "end_time": "17:00"},
            ],
        },
    )

    long_description = payload["u_long_description"]
    assert "Access log request details:" in long_description
    assert "Employee ID: E12345" in long_description
    assert "- 2026-07-01 08:00-12:00" in long_description
    assert "- 2026-07-02 13:00-17:00" in long_description
    assert "Request notes: Need login and export activity." in long_description
    assert payload["u_customer_id"] == "12345"


def test_servicenow_payload_accepts_legacy_access_log_context_names(monkeypatch):
    monkeypatch.setattr(
        servicenow,
        "_category_config",
        lambda: {
            "legacy_access_logs": {
                "short_description": "Access Logs",
                "assignment_group": "Audit Team",
                "symptom": "Inquiry",
                "incident_keyword": "Access_Logs",
                "request_type": "Access log request",
                "link_label": "Case link",
            }
        },
    )

    payload = servicenow._build_payload(
        "legacy_access_logs",
        _config(),
        case_name="Case B",
        case_link=None,
        custodian_name=None,
        custodian_email=None,
        extra_context={
            "access_log_employee_id": "E54321",
            "access_log_time_windows": [{"date": "2026-07-03", "start_time": "09:00", "end_time": "10:00"}],
        },
    )

    assert "Employee ID: E54321" in payload["u_long_description"]
    assert "- 2026-07-03 09:00-10:00" in payload["u_long_description"]
