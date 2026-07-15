from __future__ import annotations

from typing import Any, Dict

CASE_NAMING_MODE_DEFAULT = "legal_case_name"
CASE_NAMING_MODES = {"legal_case_name", "created_date", "color"}
CASE_NAMING_ALIASES = {
    "legal": "legal_case_name",
    "legal_name": "legal_case_name",
    "case_create_date": "created_date",
    "create_date": "created_date",
    "date": "created_date",
    "colors": "color",
}


def normalize_case_naming_mode(value: Any, *, strict: bool = False) -> str:
    mode = str(value or CASE_NAMING_MODE_DEFAULT).strip().lower()
    mode = CASE_NAMING_ALIASES.get(mode, mode)
    if mode not in CASE_NAMING_MODES:
        if strict:
            raise ValueError("Unsupported eDiscovery case naming option")
        return CASE_NAMING_MODE_DEFAULT
    return mode


def normalize_case_naming(raw: Any, *, strict: bool = False) -> Dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    return {"mode": normalize_case_naming_mode(data.get("mode"), strict=strict)}
