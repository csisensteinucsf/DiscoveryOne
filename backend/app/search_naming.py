from __future__ import annotations

import re
from collections.abc import Iterable


def next_search_number(case_name: str, existing_names: Iterable[str]) -> int:
    base = str(case_name or "").strip()
    if not base:
        return 1
    escaped = re.escape(base)
    patterns = (
        re.compile(rf"^{escaped}-Search\s+(\d+)$", re.IGNORECASE),
        re.compile(rf"^{escaped}\s+Search\s+(\d+)$", re.IGNORECASE),
        re.compile(rf"^{escaped}-Search\s*(\d+)$", re.IGNORECASE),
    )
    maximum = 0
    for name in existing_names or ():
        candidate = str(name or "").strip()
        if not candidate:
            continue
        for pattern in patterns:
            match = pattern.match(candidate)
            if not match:
                continue
            try:
                maximum = max(maximum, int(match.group(1)))
            except (TypeError, ValueError):
                pass
            break
    return maximum + 1


def suggest_search_name(case_name: str, existing_names: Iterable[str]) -> str:
    base = str(case_name or "").strip() or "Case"
    return f"{base}-Search {next_search_number(case_name, existing_names)}"
