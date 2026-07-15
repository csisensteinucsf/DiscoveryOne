from types import SimpleNamespace

from app import permissions, servicenow, ticket_workflow_catalog
from app.system_admin_config import normalize_ticket_workflows, tech_group_ticket_categories


def test_ticket_workflow_catalog_normalizes_custom_workflow_group():
    workflows = normalize_ticket_workflows([
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "manual",
            "preservation_source": "jamf",
            "tech_group": "endpoint",
        }
    ])

    custom = next(item for item in workflows if item["key"] == "endpoint_image")
    assert custom["label"] == "Endpoint Image"
    assert custom["provider"] == "manual"
    assert custom["tech_group"] == "endpoint"
    assert custom["preservation_source"] == "jamf"

    groups = tech_group_ticket_categories(workflows)
    assert "endpoint_image" in groups["endpoint"]

def test_ticket_workflow_uses_provider_neutral_enablement_as_canonical():
    workflows = normalize_ticket_workflows([
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "provider": "servicenow",
            "external_ticket_enabled": False,
            "service_now_enabled": True,
        }
    ])

    workflow = next(item for item in workflows if item["key"] == "endpoint_image")
    assert workflow["external_ticket_enabled"] is False
    assert workflow["service_now_enabled"] is False


def test_ticket_workflow_accepts_legacy_enablement_setting():
    workflows = normalize_ticket_workflows([
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "provider": "manual",
            "service_now_enabled": True,
        }
    ])

    workflow = next(item for item in workflows if item["key"] == "endpoint_image")
    assert workflow["external_ticket_enabled"] is True
    assert workflow["service_now_enabled"] is True


def test_default_ticket_workflows_publish_provider_neutral_enablement():
    workflows = normalize_ticket_workflows([])

    assert workflows
    assert all("external_ticket_enabled" in workflow for workflow in workflows)
    assert all(
        workflow["external_ticket_enabled"] == workflow["service_now_enabled"]
        for workflow in workflows
    )


def test_tech_groups_are_derived_from_ticket_workflows(monkeypatch):
    workflows = [
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "manual",
            "tech_group": "endpoint",
        },
        {
            "key": "mailbox_export",
            "label": "Mailbox Export",
            "enabled": True,
            "provider": "manual",
            "tech_group": "mail",
        },
    ]

    monkeypatch.setattr(ticket_workflow_catalog, "load_system_settings", lambda: {"ticket_workflows": workflows})

    endpoint_user = SimpleNamespace(role="tech", requestor_group="endpoint")
    multi_group_user = SimpleNamespace(role="tech", requestor_group="endpoint,mail")

    assert permissions.is_valid_tech_group("endpoint") is True
    assert permissions.is_valid_tech_group("box") is True
    assert permissions.is_valid_tech_group("not_configured") is False
    assert permissions.tech_allowed_ticket_categories(endpoint_user) == {"endpoint_image"}
    assert permissions.tech_allowed_ticket_categories(multi_group_user) == {"endpoint_image", "mailbox_export"}


def test_default_rubrik_workflow_uses_own_tech_group():
    workflows = normalize_ticket_workflows([])
    groups = tech_group_ticket_categories(workflows)

    assert "rubrik_restore" in groups
    assert "rubrik_restore" in groups["rubrik_restore"]
    assert "email" not in groups or "rubrik_restore" not in groups["email"]


def test_servicenow_categories_come_from_enabled_workflows(monkeypatch):
    workflows = [
        {"key": "box_hold", "label": "Box Hold", "enabled": False, "provider": "servicenow"},
        {"key": "box_hold_release", "label": "Box Hold Release", "enabled": False, "provider": "servicenow"},
        {"key": "rubrik_restore", "label": "Rubrik Restore", "enabled": False, "provider": "servicenow"},
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "servicenow",
            "assignment_group": "Endpoint Support",
            "incident_keyword": "Endpoint_Image",
            "short_description": "Endpoint imaging needed",
            "request_type": "Image custodian endpoint",
            "link_label": "DiscoveryOne case",
        },
    ]
    monkeypatch.setattr(ticket_workflow_catalog, "load_system_settings", lambda: {"ticket_workflows": workflows})

    categories = servicenow._category_config()

    assert "box_hold" not in categories
    assert categories["endpoint_image"] == {
        "short_description": "Endpoint imaging needed",
        "assignment_group": "Endpoint Support",
        "symptom": "Inquiry",
        "incident_keyword": "Endpoint_Image",
        "request_type": "Image custodian endpoint",
        "link_label": "DiscoveryOne case",
        "append_case_name_to_short_description": "",
    }



def test_ticket_workflow_metadata_schema_allows_access_log_request():
    workflows = normalize_ticket_workflows([
        {
            "key": "ehr_access_logs",
            "label": "EHR Access Logs",
            "enabled": True,
            "provider": "manual",
            "metadata_schema": "access_log_request",
        },
        {
            "key": "bad_schema",
            "label": "Bad Schema",
            "enabled": True,
            "provider": "manual",
            "metadata_schema": "org_specific_value",
        },
    ])

    lookup = {item["key"]: item for item in workflows}
    assert lookup["ehr_access_logs"]["metadata_schema"] == "access_log_request"
    assert lookup["bad_schema"]["metadata_schema"] == ""

def test_approval_workflows_follow_selected_provider_and_catalog_flags(monkeypatch):
    workflows = [
        {"key": "box_hold", "label": "Box Hold", "enabled": False},
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "servicenow",
            "external_ticket_enabled": True,
            "preservation_source": "jamf",
        },
        {
            "key": "manual_review",
            "label": "Manual Review",
            "enabled": True,
            "provider": "manual",
            "external_ticket_enabled": False,
            "auto_create_on_approval": True,
            "preservation_source": "manual_review",
        },
    ]
    monkeypatch.setattr(
        ticket_workflow_catalog,
        "load_system_settings",
        lambda: {"ticket_workflows": workflows},
    )

    assert ticket_workflow_catalog.approval_workflow_lookup(provider="none") == {}

    lookup = ticket_workflow_catalog.approval_workflow_lookup(provider="jira")
    assert set(lookup) == {"endpoint_image"}
    assert lookup["endpoint_image"]["auto_create_on_approval"] is True
    assert "box_hold_release" not in lookup


def test_approval_categories_resolve_builtin_and_custom_pending_holds(monkeypatch):
    workflows = [
        {
            "key": "box_hold",
            "label": "Box Hold",
            "enabled": True,
            "external_ticket_enabled": True,
        },
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "servicenow",
            "external_ticket_enabled": True,
            "auto_create_on_approval": True,
            "preservation_source": "jamf",
        },
    ]
    monkeypatch.setattr(
        ticket_workflow_catalog,
        "load_system_settings",
        lambda: {"ticket_workflows": workflows},
    )
    custodian = SimpleNamespace(
        holds_box=False,
        holds_box_pending=True,
        custom_preservation=[
            SimpleNamespace(source_key="jamf", active=False, pending=True)
        ],
    )

    assert ticket_workflow_catalog.approval_categories_for_custodian(
        custodian,
        provider="jira",
    ) == ["box_hold", "endpoint_image"]

def test_servicenow_category_config_honors_provider_neutral_disable(monkeypatch):
    workflows = [
        {"key": "box_hold", "label": "Box Hold", "enabled": False},
        {"key": "box_hold_release", "label": "Box Hold Release", "enabled": False},
        {"key": "rubrik_restore", "label": "Rubrik Restore", "enabled": False},
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "servicenow",
            "external_ticket_enabled": False,
        },
    ]
    monkeypatch.setattr(
        ticket_workflow_catalog,
        "load_system_settings",
        lambda: {"ticket_workflows": workflows},
    )

    assert "endpoint_image" not in ticket_workflow_catalog.servicenow_category_config()

def test_default_ticket_workflow_status_sync_metadata_preserves_legacy_behavior():
    lookup = {
        workflow["key"]: workflow
        for workflow in normalize_ticket_workflows([])
    }

    assert lookup["box_hold"]["manual_status_tracking"] is True
    assert lookup["box_hold"]["hold_operation"] == "hold"
    assert lookup["box_hold_release"]["manual_status_tracking"] is True
    assert lookup["box_hold_release"]["hold_operation"] == "release"
    assert lookup["rubrik_restore"]["manual_status_tracking"] is False
    assert lookup["rubrik_restore"]["hold_operation"] == "hold"
    assert lookup["rubrik_restore"]["completion_satisfies_source"] == "email"
    assert (
        ticket_workflow_catalog.completion_satisfies_hold_key(
            lookup["rubrik_restore"]
        )
        == "holds_email"
    )


def test_custom_ticket_workflow_normalizes_status_sync_opt_in():
    workflows = normalize_ticket_workflows(
        [
            {
                "key": "archive_release",
                "label": "Archive Release",
                "manual_status_tracking": True,
                "operation": "release",
                "completion_satisfies_hold_key": "holds_onedrive",
            }
        ]
    )
    workflow = next(
        item for item in workflows if item["key"] == "archive_release"
    )

    assert workflow["manual_status_tracking"] is True
    assert workflow["hold_operation"] == "release"
    assert workflow["completion_satisfies_hold_key"] == "holds_onedrive"
    assert (
        ticket_workflow_catalog.completion_satisfies_hold_key(workflow)
        == "holds_onedrive"
    )
