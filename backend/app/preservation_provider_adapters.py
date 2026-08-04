from __future__ import annotations

from typing import Any

from .preservation_provider_registry import PreservationOperationContext


def _provider_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    normalized = dict(result)
    normalized.setdefault("provider", "purview")
    provider_case_id = normalized.get("provider_case_id") or normalized.get(
        "purview_case_id"
    )
    normalized["provider_case_id"] = provider_case_id
    # Existing clients may still read the provider-specific response key.
    normalized.setdefault("purview_case_id", provider_case_id)
    return normalized


class PurviewPreservationProviderAdapter:
    name = "purview"
    display_name = "Microsoft Purview"

    def is_available(self) -> bool:
        from .purview import purview_enabled

        return purview_enabled()

    def status_poll_delay_seconds(self) -> float:
        from .case_purview_gateway import status_poll_delay_seconds

        return status_poll_delay_seconds()

    def create_case(
        self,
        *,
        case_id: int,
        context: PreservationOperationContext,
    ) -> Any:
        from .case_purview_case_create import create_purview_case_for_case

        return _provider_result(create_purview_case_for_case(
            case_id=case_id,
            db=context.db,
            request=context.request,
            user=context.user,
        ))

    def get_status(
        self,
        *,
        case_id: int,
        context: PreservationOperationContext,
    ) -> Any:
        from .case_purview_status import get_purview_status_for_case

        return _provider_result(get_purview_status_for_case(
            case_id=case_id,
            db=context.db,
            request=context.request,
            user=context.user,
            case_hold_id=context.options.get("case_hold_id"),
        ))

    def apply_holds(
        self,
        *,
        case_id: int,
        payload: Any,
        context: PreservationOperationContext,
    ) -> Any:
        from .case_purview_apply import apply_purview_holds_for_case

        return _provider_result(apply_purview_holds_for_case(
            case_id=case_id,
            payload=payload,
            db=context.db,
            request=context.request,
            _user=context.user,
        ))

    def release_holds(
        self,
        *,
        case_id: int,
        payload: Any,
        context: PreservationOperationContext,
    ) -> Any:
        from .case_purview_release import release_purview_holds_for_case

        return _provider_result(release_purview_holds_for_case(
            case_id=case_id,
            payload=payload,
            db=context.db,
            request=context.request,
            _user=context.user,
        ))


    def remove_custodian(
        self,
        *,
        case_id: int,
        custodian_id: int,
        custodian_name: str | None,
        custodian_email: str | None,
        context: PreservationOperationContext,
    ) -> Any:
        from .purview_custodian_removal import remove_purview_custodian

        return remove_purview_custodian(
            case_id=case_id,
            custodian_id=custodian_id,
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            context=context,
        )
