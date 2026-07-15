from __future__ import annotations

from typing import Any, Callable, Protocol


class PersonLookupProvider(Protocol):
    name: str

    def lookup(
        self,
        query: str,
        *,
        email: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        ...


PersonLookupProviderFactory = Callable[[], PersonLookupProvider]

_FACTORIES: dict[str, PersonLookupProviderFactory] = {}
_ALIASES: dict[str, str] = {}


def normalize_person_lookup_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_person_lookup_provider(
    name: str,
    factory: PersonLookupProviderFactory,
    *,
    aliases: tuple[str, ...] = (),
    replace: bool = False,
) -> None:
    canonical = normalize_person_lookup_provider_name(name)
    if not canonical or canonical == "none":
        raise ValueError("Person lookup providers require a unique provider name.")
    if canonical in _FACTORIES and not replace:
        raise ValueError(f"Person lookup provider '{canonical}' is already registered.")

    normalized_aliases = {
        normalize_person_lookup_provider_name(alias)
        for alias in aliases
        if normalize_person_lookup_provider_name(alias)
    }
    normalized_aliases.discard("none")
    for alias in normalized_aliases:
        owner = _ALIASES.get(alias)
        if owner and owner != canonical and not replace:
            raise ValueError(
                f"Person lookup provider alias '{alias}' is already registered."
            )

    if replace:
        for alias, owner in list(_ALIASES.items()):
            if owner == canonical:
                _ALIASES.pop(alias, None)
    _FACTORIES[canonical] = factory
    for alias in normalized_aliases:
        _ALIASES[alias] = canonical


def unregister_person_lookup_provider(name: str) -> None:
    canonical = normalize_person_lookup_provider_name(name)
    canonical = _ALIASES.get(canonical, canonical)
    _FACTORIES.pop(canonical, None)
    for alias, owner in list(_ALIASES.items()):
        if owner == canonical:
            _ALIASES.pop(alias, None)


def get_person_lookup_provider_factory(
    name: str | None,
) -> PersonLookupProviderFactory | None:
    normalized = normalize_person_lookup_provider_name(name)
    canonical = _ALIASES.get(normalized, normalized)
    return _FACTORIES.get(canonical)


def registered_person_lookup_provider_names(
    *,
    include_none: bool = False,
    include_aliases: bool = True,
) -> set[str]:
    names = set(_FACTORIES)
    if include_aliases:
        names.update(_ALIASES)
    if include_none:
        names.add("none")
    return names
