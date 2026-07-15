from types import SimpleNamespace

from app import search_export_provider
from app import search_export_provider_registry


def test_registered_search_export_provider_receives_context(monkeypatch):
    calls = []

    class ExampleSearchExportProvider:
        name = "example_export"
        display_name = "Example Export"

        def is_available(self):
            return True

        def push_search(self, *, case, search, payload, context):
            calls.append((case, search, payload, context))
            return {
                "provider": self.name,
                "status": "created",
                "provider_search_id": "search-123",
            }

    search_export_provider_registry.register_search_export_provider(
        "example_export",
        ExampleSearchExportProvider,
        display_name="Example Export",
    )
    monkeypatch.setattr(
        search_export_provider,
        "current_search_export_provider",
        lambda: "example_export",
    )
    case = SimpleNamespace(id=7, name="Case Seven")
    search = SimpleNamespace(id=11, name="Search Eleven")
    user = SimpleNamespace(id=5)
    try:
        result = search_export_provider.push_search(
            case=case,
            search=search,
            payload={"query": "from:example.edu"},
            db="db",
            request="request",
            user=user,
        )
    finally:
        search_export_provider_registry.unregister_search_export_provider(
            "example_export"
        )

    assert result["provider_search_id"] == "search-123"
    assert calls[0][0] is case
    assert calls[0][1] is search
    assert calls[0][2] == {"query": "from:example.edu"}
    assert calls[0][3].db == "db"
    assert calls[0][3].request == "request"
    assert calls[0][3].user is user


def test_search_export_provider_none_does_not_inherit_preservation_provider(monkeypatch):
    values = {
        "search_export_provider": "none",
        "preservation_provider": "purview",
    }
    monkeypatch.setattr(
        search_export_provider,
        "provider_value",
        lambda name, default="none": values.get(name, default),
    )

    assert search_export_provider.current_search_export_provider() == "none"


def test_search_routes_include_generic_and_compatibility_paths():
    from app import searches

    paths = {route.path for route in searches.router.routes}

    assert "/api/cases/{case_id}/searches/{search_id}/push_to_provider" in paths
    assert "/api/cases/{case_id}/searches/{search_id}/push_to_purview" in paths