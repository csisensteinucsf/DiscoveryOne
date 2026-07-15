from typing import List, Optional

PURVIEW_HOLD_SOURCES = ["mailbox", "site"]


def normalize_included_sources(included_sources: Optional[list]) -> List[str]:
    if included_sources is None:
        return []
    if isinstance(included_sources, str):
        raw = [included_sources]
    else:
        raw = list(included_sources)
    cleaned: list[str] = []
    for item in raw:
        if item is None:
            continue
        text = str(item)
        parts = text.split(",") if "," in text else [text]
        for part in parts:
            value = str(part).strip().lower()
            if not value or value not in PURVIEW_HOLD_SOURCES:
                continue
            if value not in cleaned:
                cleaned.append(value)
    return cleaned


def serialize_included_sources(included_sources: Optional[list]) -> Optional[str]:
    cleaned = normalize_included_sources(included_sources)
    if not cleaned:
        return None
    ordered = [value for value in PURVIEW_HOLD_SOURCES if value in cleaned]
    return ",".join(ordered)