from __future__ import annotations

from difflib import SequenceMatcher
import logging
import re
from typing import Any, Optional

from .institution import is_organization_email
from .person_lookup import get_person_lookup_provider

logger = logging.getLogger(__name__)
NO_EMAIL_PLACEHOLDER = "NoEmail"
UNMATCHED_EMAIL_PLACEHOLDER = "UNMATCHED"
def _normalize_person_label(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9@]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _person_label_tokens(value: str | None) -> list[str]:
    normalized = _normalize_person_label(value)
    return normalized.split() if normalized else []


def _token_similarity(left: str | None, right: str | None) -> float:
    a = (left or "").strip().lower()
    b = (right or "").strip().lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return max(0.84, min(len(a), len(b)) / max(len(a), len(b)))
    return SequenceMatcher(None, a, b).ratio()


def _best_token_similarity(query_token: str | None, candidate_tokens: list[str]) -> float:
    if not query_token or not candidate_tokens:
        return 0.0
    return max((_token_similarity(query_token, token) for token in candidate_tokens), default=0.0)


def _match_has_lookup_email(match: dict) -> bool:
    email = str(match.get("email") or "").strip().lower()
    return bool(email and "@" in email)


def _match_has_organization_lookup_email(match: dict) -> bool:
    email = str(match.get("email") or "").strip().lower()
    return bool(email and is_organization_email(email))


def _match_has_lookup_department(match: dict) -> bool:
    return bool(str(match.get("department") or match.get("department_name") or match.get("department_id") or "").strip())


def _match_has_lookup_job(match: dict) -> bool:
    return bool(str(match.get("title") or match.get("job_title_official") or "").strip())


def _match_is_current_employee(match: dict) -> bool:
    current = match.get("current_employee")
    if isinstance(current, bool):
        return current
    return match.get("employee_end_date") in {None, ""}


def _is_exact_first_last_lookup_match(query_name: str, match: dict) -> bool:
    query_tokens = _person_label_tokens(query_name)
    if len(query_tokens) != 2:
        return False
    candidate_name = _build_lookup_display_name(match)
    candidate_tokens = _person_label_tokens(candidate_name)
    first_tokens = _person_label_tokens(match.get("first_name")) or (candidate_tokens[:1] if candidate_tokens else [])
    last_tokens = _person_label_tokens(match.get("last_name")) or (candidate_tokens[-1:] if candidate_tokens else [])
    return bool(first_tokens and last_tokens and query_tokens[0] in first_tokens and query_tokens[-1] in last_tokens)


def _exact_first_last_lookup_sort_key(query_name: str, scored_item: dict[str, Any]) -> tuple[Any, ...]:
    match = scored_item["match"]
    candidate_norm = _normalize_person_label(_build_lookup_display_name(match))
    query_norm = _normalize_person_label(query_name)
    return (
        1 if _match_has_lookup_email(match) else 0,
        1 if _match_has_organization_lookup_email(match) else 0,
        1 if _match_has_lookup_department(match) else 0,
        1 if _match_has_lookup_job(match) else 0,
        1 if candidate_norm == query_norm else 0,
        1 if _match_is_current_employee(match) else 0,
        scored_item["score"],
    )


def _score_lookup_match(query_name: str, match: dict) -> dict[str, Any]:
    query_norm = _normalize_person_label(query_name)
    query_tokens = _person_label_tokens(query_name)
    candidate_name = _build_lookup_display_name(match)
    candidate_norm = _normalize_person_label(candidate_name)
    candidate_tokens = _person_label_tokens(candidate_name)
    first_tokens = _person_label_tokens(match.get("first_name")) or (candidate_tokens[:1] if candidate_tokens else [])
    middle_tokens = _person_label_tokens(match.get("middle_name"))
    last_tokens = _person_label_tokens(match.get("last_name")) or (candidate_tokens[-1:] if candidate_tokens else [])

    first_similarity = _best_token_similarity(query_tokens[0], first_tokens) if query_tokens else 0.0
    last_similarity = _best_token_similarity(query_tokens[-1], last_tokens) if len(query_tokens) >= 2 else 0.0

    query_middle = query_tokens[1:-1] if len(query_tokens) >= 3 else []
    middle_similarity = 0.0
    if query_middle:
        middle_similarity = sum(_best_token_similarity(token, middle_tokens) for token in query_middle) / len(query_middle)

    full_similarity = _token_similarity(query_norm, candidate_norm) if query_norm and candidate_norm else 0.0

    score = full_similarity * 100.0
    if query_tokens:
        score += first_similarity * 70.0
    if len(query_tokens) >= 2:
        score += last_similarity * 140.0
    if query_middle:
        score += middle_similarity * 60.0
    if candidate_norm and candidate_norm == query_norm:
        score += 300.0
    if len(query_tokens) >= 2 and query_tokens[-1] in last_tokens:
        score += 60.0
    if query_tokens and query_tokens[0] in first_tokens:
        score += 20.0
    if query_middle and all(
        _best_token_similarity(token, middle_tokens) >= 0.9
        for token in query_middle
    ):
        score += 40.0

    strong = False
    if candidate_norm and candidate_norm == query_norm:
        strong = True
    elif len(query_tokens) >= 3:
        strong = (
            last_similarity >= 0.84
            and first_similarity >= 0.7
            and (middle_similarity >= 0.65 or full_similarity >= 0.82)
        )
    elif len(query_tokens) == 2:
        strong = last_similarity >= 0.84 and (first_similarity >= 0.7 or full_similarity >= 0.84)
    elif len(query_tokens) == 1:
        strong = _best_token_similarity(query_tokens[0], candidate_tokens) >= 0.9 or full_similarity >= 0.9

    return {
        "match": match,
        "score": score,
        "strong": strong,
    }


def _rank_lookup_matches(query_name: str, matches: list[dict]) -> list[dict]:
    if not matches:
        return []
    scored = [_score_lookup_match(query_name, item) for item in matches]
    scored.sort(
        key=lambda item: (
            1 if item["strong"] else 0,
            item["score"],
        ),
        reverse=True,
    )

    exact_first_last = [item for item in scored if _is_exact_first_last_lookup_match(query_name, item["match"])]
    if exact_first_last:
        exact_first_last.sort(key=lambda item: _exact_first_last_lookup_sort_key(query_name, item), reverse=True)
        return [item["match"] for item in exact_first_last[:10]]

    strong = [item for item in scored if item["strong"]]
    if strong:
        best_score = strong[0]["score"]
        return [item["match"] for item in strong if item["score"] >= best_score - 45.0][:10]
    return [item["match"] for item in scored[:10]]


def _has_strong_lookup_match(query_name: str, matches: list[dict]) -> bool:
    return any(item["strong"] for item in (_score_lookup_match(query_name, match) for match in matches))


def _single_token_fallback_candidates(full_name: str) -> list[str]:
    parts = [token for token in (full_name or "").strip().split() if token]
    if not parts:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for token in ([parts[-1]] + sorted(parts, key=len, reverse=True) + [parts[0]]):
        normalized = token.strip().lower()
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(token)
    return ordered

def _split_name(full_name: str) -> tuple[Optional[str], Optional[str]]:
    parts = [p for p in (full_name or "").replace(",", " ").split() if p]
    if not parts:
        return (None, None)
    if len(parts) == 1:
        return (parts[0], None)
    return (parts[0], parts[-1])

def _name_variants(full_name: str) -> list[tuple[str, str]]:
    parts = [p for p in (full_name or "").replace(",", " ").split() if p]
    if not parts:
        return []
    if len(parts) == 1:
        return []
    seen: set[tuple[str, str]] = set()
    variants: list[tuple[str, str]] = []

    def _add(first_name: str, last_name: str) -> None:
        first = " ".join((first_name or "").split()).strip()
        last = " ".join((last_name or "").split()).strip()
        if not first or not last:
            return
        key = (first.lower(), last.lower())
        if key in seen:
            return
        seen.add(key)
        variants.append((first, last))

    for start in range(len(parts) - 1):
        first = parts[start]
        rest = parts[start + 1 :]
        if not rest:
            continue
        if len(rest) >= 2:
            _add(first, " ".join(rest))
            _add(first, "-".join(rest))
            _add(first, "".join(rest))

            tail2 = rest[-2:]
            _add(first, " ".join(tail2))
            _add(first, "-".join(tail2))
            _add(first, "".join(tail2))

        _add(first, rest[-1])
    return variants


def _three_name_variants(full_name: str) -> list[tuple[str, str, str]]:
    parts = [p for p in (full_name or "").replace(",", " ").split() if p]
    if len(parts) < 3:
        return []
    seen: set[tuple[str, str, str]] = set()
    variants: list[tuple[str, str, str]] = []

    def _add(first_name: str, middle_name: str, last_name: str) -> None:
        first = " ".join((first_name or "").split()).strip()
        middle = " ".join((middle_name or "").split()).strip()
        last = " ".join((last_name or "").split()).strip()
        if not first or not middle or not last:
            return
        key = (first.lower(), middle.lower(), last.lower())
        if key in seen:
            return
        seen.add(key)
        variants.append((first, middle, last))

    first = parts[0]
    last = parts[-1]
    middle_parts = parts[1:-1]
    _add(first, " ".join(middle_parts), last)
    _add(first, "-".join(middle_parts), last)
    _add(first, "".join(middle_parts), last)
    if len(middle_parts) >= 2:
        _add(first, middle_parts[0], " ".join(parts[2:]))
        _add(" ".join(parts[:-2]), middle_parts[-1], last)
    return variants


def _normalize_lookup_email(value: str | None) -> Optional[str]:
    text = (value or "").strip().lower()
    if not text or "@" not in text:
        return None
    return text


def _normalize_lookup_external_id(value: str | None) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized = re.sub(r"[\s()]+", "", raw)
    if re.fullmatch(r"[A-Za-z0-9._-]{2,64}", normalized) and any(ch.isdigit() for ch in normalized):
        return normalized
    return None
def _coerce_lookup_text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _coerce_lookup_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _build_lookup_display_name(match: dict) -> Optional[str]:
    display = _coerce_lookup_text(match.get("display_name"))
    if display:
        return display
    first = _coerce_lookup_text(match.get("first_name"))
    middle = _coerce_lookup_text(match.get("middle_name"))
    last = _coerce_lookup_text(match.get("last_name"))
    combined = " ".join(part for part in [first, middle, last] if part)
    return combined or None


def _pick_lookup_match(*, matches: list[dict], current_name: Optional[str], current_email: Optional[str]) -> Optional[dict]:
    if not matches:
        return None
    email_norm = (current_email or "").strip().lower()
    if email_norm and email_norm not in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        for item in matches:
            candidate_email = (item.get("email") or "").strip().lower()
            if candidate_email and candidate_email == email_norm:
                return item
    name_norm = _normalize_person_label(current_name)
    if name_norm:
        exact_name_matches = []
        for item in matches:
            candidate_name = _build_lookup_display_name(item)
            if _normalize_person_label(candidate_name) == name_norm:
                exact_name_matches.append(item)
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]
    if len(matches) == 1:
        return matches[0]
    return None


def _run_configured_person_lookup(
    query: str,
    *,
    email: Optional[str] = None,
    session=None,
) -> tuple[list[dict], Optional[str]]:
    provider = get_person_lookup_provider()
    try:
        lookup_in_session = getattr(provider, "lookup_in_session", None)
        if session is not None and callable(lookup_in_session):
            matches, err = lookup_in_session(query, email=email, session=session)
        else:
            matches, err = provider.lookup(query, email=email)
    except Exception:
        logger.exception("person lookup provider failed")
        return ([], "Lookup failed. Please try again later.")
    return (matches or [], err)

