from __future__ import annotations

from typing import Any

from .hold_source_provider_registry import (
    HoldSourceConfigurationError,
    HoldSourceOperationContext,
    HoldSourceOperationError,
    HoldSourceSubjectNotFound,
)


class SlackHoldSourceProviderAdapter:
    source_key = "slack"
    display_name = "Slack"

    def is_available(self) -> bool:
        from .slack_legal_holds import slack_legal_holds_enabled

        return slack_legal_holds_enabled()

    def sync_custodian_hold(
        self,
        *,
        case: Any,
        custodian: Any,
        custodian_email: str,
        enable: bool,
        context: HoldSourceOperationContext,
    ) -> dict[str, Any]:
        from .slack_legal_holds import (
            SlackLegalHoldsAPIError,
            SlackLegalHoldsConfigError,
            sync_slack_hold_for_custodian,
        )

        try:
            policy_id, subject_id = sync_slack_hold_for_custodian(
                case_id=case.id,
                case_name=(case.name or f"Case {case.id}"),
                case_policy_id=getattr(case, "slack_hold_policy_id", None),
                custodian_email=custodian_email,
                enable=enable,
            )
        except SlackLegalHoldsConfigError as error:
            raise HoldSourceConfigurationError(str(error)) from error
        except SlackLegalHoldsAPIError as error:
            error_code = str(getattr(error, "error_code", "") or "").strip()
            error_type = (
                HoldSourceSubjectNotFound
                if error_code.lower() == "user_not_found"
                else HoldSourceOperationError
            )
            raise error_type(
                str(error),
                error_code=error_code or None,
                status_code=getattr(error, "status_code", None),
            ) from error

        if policy_id:
            case.slack_hold_policy_id = policy_id
        elif not enable:
            case.slack_hold_policy_id = None
        if enable:
            if subject_id:
                custodian.slack_user_id = subject_id
        else:
            custodian.slack_user_id = None

        return {
            "source_key": self.source_key,
            "provider": self.source_key,
            "status": "enabled" if enable else "released",
            "provider_case_id": getattr(case, "slack_hold_policy_id", None),
            "provider_subject_id": subject_id,
        }
