from __future__ import annotations

from copy import deepcopy
from typing import Any


_DEFAULT_PRESERVATION_SOURCES: list[dict[str, Any]] = [
    {"key": "email", "label": "Email (O365/Google)", "enabled": True, "built_in": True},
    {"key": "onedrive", "label": "OneDrive", "enabled": True, "built_in": True},
    {"key": "gdrive", "label": "Google Drive", "enabled": False, "built_in": True},
    {"key": "box", "label": "Box", "enabled": True, "built_in": True},
    {"key": "dropbox", "label": "Dropbox", "enabled": False, "built_in": True},
    {"key": "slack", "label": "Slack", "enabled": True, "built_in": True},
    {"key": "zoom", "label": "Zoom", "enabled": False, "built_in": True},
]


_DEFAULT_TICKET_WORKFLOWS: list[dict[str, Any]] = [
    {
        "key": "box_hold",
        "label": "Box Hold",
        "enabled": True,
        "provider": "servicenow",
        "external_ticket_enabled": True,
        "service_now_enabled": True,
        "auto_create_on_approval": True,
        "manual_status_tracking": True,
        "hold_operation": "hold",
        "completion_satisfies_source": "",
        "completion_satisfies_hold_key": "",
        "preservation_source": "box",
        "hold_key": "holds_box",
        "tech_group": "box",
        "requires_matched_email": True,
        "legacy_field": "box_hold_ticket",
        "built_in": True,
        "short_description": "Box Hold",
        "assignment_group": "",
        "symptom": "Inquiry",
        "incident_keyword": "",
        "request_type": "Box Hold",
        "link_label": "Case link",
    },
    {
        "key": "box_hold_release",
        "label": "Box Hold Release",
        "enabled": True,
        "provider": "servicenow",
        "external_ticket_enabled": True,
        "service_now_enabled": True,
        "auto_create_on_approval": False,
        "manual_status_tracking": True,
        "hold_operation": "release",
        "completion_satisfies_source": "",
        "completion_satisfies_hold_key": "",
        "preservation_source": "box",
        "hold_key": "holds_box",
        "tech_group": "box",
        "requires_matched_email": True,
        "legacy_field": "",
        "built_in": True,
        "short_description": "Box Hold Release",
        "assignment_group": "",
        "symptom": "Inquiry",
        "incident_keyword": "",
        "request_type": "Box Hold Release",
        "link_label": "Case link",
    },
    {
        "key": "rubrik_restore",
        "label": "Rubrik Restore",
        "enabled": False,
        "provider": "servicenow",
        "external_ticket_enabled": True,
        "service_now_enabled": True,
        "auto_create_on_approval": True,
        "manual_status_tracking": False,
        "hold_operation": "hold",
        "completion_satisfies_source": "email",
        "completion_satisfies_hold_key": "",
        "preservation_source": "rubrik_restore",
        "hold_key": "holds_rubrik_restore",
        "tech_group": "rubrik_restore",
        "requires_matched_email": True,
        "legacy_field": "rubrik_restore_ticket",
        "built_in": True,
        "short_description": "Rubrik Restore",
        "assignment_group": "",
        "symptom": "Inquiry",
        "incident_keyword": "",
        "request_type": "Rubrik Restore",
        "link_label": "Case link",
    },
]


def default_preservation_sources() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT_PRESERVATION_SOURCES)


def default_ticket_workflows() -> list[dict[str, Any]]:
    return deepcopy(_DEFAULT_TICKET_WORKFLOWS)
