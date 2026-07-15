import ast
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"

# These are adapter, transport, or provider-specific ingress modules. General
# workflows must depend on provider facades instead of importing these modules.
ALLOWED_IMPORTERS = {
    "purview": {
        "purview.py",
        "purview_exports.py",
        "purview_custodian_removal.py",
        "case_purview_gateway.py",
    },
    "slack_legal_holds": {
        "slack_legal_holds.py",
        "slack_oauth.py",
        "hold_source_provider_adapters.py",
    },
    "docusign_client": {
        "docusign_client.py",
        "docusign_webhook.py",
        "esignature_provider_adapters.py",
    },
    "servicenow": {
        "servicenow.py",
        "ticket_provider_adapters.py",
    },
    "smtplib": {
        "smtp_mail_provider.py",
    },
}


def _imported_roots(node):
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name.split(".", 1)[0]
        return

    if not isinstance(node, ast.ImportFrom):
        return
    if node.module:
        yield node.module.split(".", 1)[0]
        return
    for alias in node.names:
        yield alias.name.split(".", 1)[0]


def _is_allowed(imported_root, path_name):
    if path_name in ALLOWED_IMPORTERS.get(imported_root, set()):
        return True
    if imported_root == "purview" and path_name.startswith("case_purview"):
        return True
    if imported_root == "purview" and path_name in {
        "preservation_provider_adapters.py",
        "search_export_provider_adapters.py",
        "purview_search_export.py",
    }:
        return True
    return False


def _function_source(path_name, function_name):
    path = APP_DIR / path_name
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    return ast.unparse(function)


def test_preservation_polling_uses_only_the_generic_provider_facade():
    scheduler = _function_source("cases.py", "_schedule_preservation_status_poll")

    assert "preservation_provider.status_poll_delay_seconds()" in scheduler
    assert "preservation_provider.get_status" in scheduler
    assert "get_purview_status" not in scheduler
    assert "purview_status_poll_delay_seconds" not in scheduler

    for path_name in (
        "case_purview_case_create.py",
        "case_purview_apply.py",
        "case_purview_release.py",
    ):
        source = (APP_DIR / path_name).read_text(encoding="utf-8-sig")
        assert "_schedule_purview_status_poll(" not in source
        assert "_schedule_preservation_status_poll(" in source


def test_auto_apply_uses_generic_preservation_filtering():
    source = (APP_DIR / "case_request_auto_apply.py").read_text(encoding="utf-8-sig")

    assert "filter_rubrik_targets_after_preservation(" in source
    assert "filter_rubrik_targets_after_purview(" not in source


def test_provider_implementations_are_imported_only_at_approved_boundaries():
    violations = []
    for path in sorted(APP_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            for imported_root in _imported_roots(node):
                if imported_root not in ALLOWED_IMPORTERS:
                    continue
                if _is_allowed(imported_root, path.name):
                    continue
                violations.append(
                    f"{path.name}:{getattr(node, 'lineno', '?')} imports "
                    f"{imported_root}; use its provider facade or adapter"
                )

    assert not violations, "\n" + "\n".join(violations)