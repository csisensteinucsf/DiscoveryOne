from app.ai_assistant import (
    _contains_action_offer,
    _direct_help_answer,
    _is_action_execution_request,
    _sanitize_info_only_answer,
)


def test_action_execution_request_is_blocked_for_hold_command():
    assert _is_action_execution_request("please place holds on all custodians for me") is True


def test_action_execution_request_is_blocked_for_delete_command():
    assert _is_action_execution_request("delete case 123 now") is True


def test_information_question_is_not_blocked_for_how_to():
    assert _is_action_execution_request("how do i add a custodian to an existing case?") is False


def test_information_question_is_not_blocked_for_explanation():
    assert _is_action_execution_request("what happens when a hold is removed?") is False


def test_contains_action_offer_detects_permission_prompt():
    assert _contains_action_offer("Would you like me to re-apply the hold?") is True


def test_sanitize_info_only_answer_removes_action_offer_sentence():
    raw = "Box shows a red X when hold apply failed. Would you like me to re-apply the hold?"
    out = _sanitize_info_only_answer(raw)
    assert "would you like me to re-apply" not in out.lower()
    assert "red x" in out.lower()
    assert "step-by-step instructions only" in out.lower()


def test_direct_help_answer_for_ntp_template_on_system_page_for_admin():
    out = _direct_help_answer(
        "How do I create a new NTP template?",
        "sys_admin",
        case_id=None,
        pathname="/system",
    )
    assert out is not None
    assert out["task_id"] == "ntp_template_create"
    assert "NTP Templates" in out["answer"]
    assert "New Template" in out["answer"]
    assert "Group Access" in out["answer"]



def test_direct_help_answer_for_ntp_template_on_system_page_for_requestor():
    out = _direct_help_answer(
        "How do I create a new Notice to Preserve template?",
        "requestor",
        case_id=None,
        pathname="/system",
    )
    assert out is not None
    assert out["task_id"] == "ntp_template_create"
    assert "limited to your requestor group automatically" in out["answer"]



def test_direct_help_answer_for_ntp_template_blocks_tech_role():
    out = _direct_help_answer(
        "How do I create a new NTP template?",
        "tech",
        case_id=None,
        pathname="/system",
    )
    assert out is not None
    assert out["task_id"] == "ntp_template_unavailable"
    assert "Tech and tester accounts do not manage NTP templates" in out["answer"]

