from __future__ import annotations

from typing import Any

from .search_export_provider_registry import SearchExportOperationContext


class PurviewSearchExportProviderAdapter:
    name = "purview"
    display_name = "Microsoft Purview"

    def is_available(self) -> bool:
        from .purview import purview_enabled

        return purview_enabled()

    def normalize_query(self, raw: Any) -> str:
        from .purview_search_export import normalize_purview_kql

        return normalize_purview_kql(raw)

    def push_search(
        self,
        *,
        case: Any,
        search: Any,
        payload: dict[str, Any],
        context: SearchExportOperationContext,
    ) -> dict[str, Any]:
        from .purview_search_export import push_search_to_purview

        return push_search_to_purview(
            case=case,
            search=search,
            payload=payload,
            context=context,
        )