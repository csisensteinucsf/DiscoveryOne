import pytest

from app import (
    integration_settings,
    log_shipping,
    system_admin_config,
    system_settings,
)


LOG_SHIP_ENV_NAMES = (
    'LOG_SHIP_ENABLED',
    'LOG_SHIP_INTERVAL_HOURS',
    'LOG_SHIP_RUN_ON_STARTUP',
    'LOG_SHIP_TENANT_ID',
    'LOG_SHIP_CLIENT_ID',
    'LOG_SHIP_CLIENT_SECRET',
    'LOG_SHIP_SHAREPOINT_SITE_ID',
    'LOG_SHIP_SHAREPOINT_DRIVE_ID',
    'LOG_SHIP_SHAREPOINT_DRIVE_NAME',
    'LOG_SHIP_SHAREPOINT_FOLDER',
    'LOG_SHIP_GRAPH_BASE',
    'LOG_SHIP_SCOPE',
    'LOG_SHIP_MAX_FILE_MB',
    'LOG_SHIP_MAX_ARCHIVE_MB',
    'LOG_SHIP_MAX_FILES',
    'LOG_SHIP_TIMEOUT_SECONDS',
    'LOG_SHIP_RETRY_COUNT',
    'PURVIEW_TENANT_ID',
    'PURVIEW_CLIENT_ID',
    'PURVIEW_CLIENT_SECRET',
    'O365_TENANT_ID',
    'O365_CLIENT_ID',
    'O365_CLIENT_SECRET',
)


def _clear_log_ship_env(monkeypatch):
    for name in LOG_SHIP_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_log_shipping_is_disabled_with_safe_defaults(monkeypatch):
    _clear_log_ship_env(monkeypatch)
    monkeypatch.setattr(log_shipping, 'load_stored_system_settings', lambda: {})

    settings = log_shipping.load_log_shipping_settings()

    assert system_settings.DEFAULT_SETTINGS['enabled_integrations']['log_shipping'] is False
    assert settings.enabled is False
    assert settings.interval_hours == 24
    assert settings.run_on_startup is True
    assert settings.graph_base == 'https://graph.microsoft.com/v1.0'
    assert settings.scope == 'https://graph.microsoft.com/.default'
    assert settings.max_archive_mb == 250
    assert settings.max_files == 5000


def test_stored_log_shipping_settings_override_legacy_env(monkeypatch):
    _clear_log_ship_env(monkeypatch)
    monkeypatch.setenv('LOG_SHIP_ENABLED', '0')
    monkeypatch.setenv('LOG_SHIP_TENANT_ID', 'env-tenant')
    monkeypatch.setenv('LOG_SHIP_CLIENT_SECRET', 'env-secret')
    encrypted_secret = integration_settings.encrypt_secret('stored-secret')
    stored = {
        'enabled_integrations': {'log_shipping': True},
        'integration_configs': {
            'log_shipping': {
                'tenant_id': 'stored-tenant',
                'client_id': 'stored-client',
                'client_secret': encrypted_secret,
                'sharepoint_site_id': 'stored-site',
                'sharepoint_drive_name': 'Documents',
                'sharepoint_folder': 'Stored/Logs',
                'interval_hours': 12,
                'run_on_startup': False,
            }
        },
    }
    monkeypatch.setattr(
        log_shipping,
        'load_stored_system_settings',
        lambda: stored,
    )

    settings = log_shipping.load_log_shipping_settings()

    assert settings.enabled is True
    assert settings.tenant_id == 'stored-tenant'
    assert settings.client_id == 'stored-client'
    assert settings.client_secret == 'stored-secret'
    assert settings.sharepoint_folder == 'Stored/Logs'
    assert settings.interval_hours == 12
    assert settings.run_on_startup is False

    stored['enabled_integrations']['log_shipping'] = False
    monkeypatch.setenv('LOG_SHIP_ENABLED', '1')
    assert log_shipping.load_log_shipping_settings().enabled is False


def test_log_shipping_secret_is_encrypted_and_required_when_enabled(monkeypatch):
    config = dict(system_settings.DEFAULT_SETTINGS['integration_configs']['log_shipping'])
    config.update(
        {
            'tenant_id': 'tenant',
            'client_id': 'client',
            'sharepoint_site_id': 'site',
            'sharepoint_drive_id': 'drive',
        }
    )

    with pytest.raises(ValueError, match='client secret'):
        integration_settings.validate_integration_settings(
            enabled_integrations={'log_shipping': True},
            providers={},
            configs={'log_shipping': config},
        )

    sanitized = integration_settings.sanitize_integration_config(
        'log_shipping',
        {**config, 'client_secret': 'plain-secret'},
    )
    assert sanitized['client_secret'].startswith('enc:v1:')
    assert integration_settings.decrypt_secret(sanitized['client_secret']) == 'plain-secret'

    integration_settings.validate_integration_settings(
        enabled_integrations={'log_shipping': True},
        providers={},
        configs={'log_shipping': sanitized},
    )

    monkeypatch.setattr(
        integration_settings,
        'load_system_settings',
        lambda: {'integration_configs': {'log_shipping': sanitized}},
    )
    public = integration_settings.public_integration_config('log_shipping')
    assert public['client_secret'] == integration_settings.MASKED_SECRET_VALUE


def test_provider_summary_includes_search_export_provider(monkeypatch):
    monkeypatch.setattr(
        system_admin_config,
        'load_integration_settings',
        lambda: {
            'enabled_integrations': {},
            'search_export_provider': 'relativity',
        },
    )
    monkeypatch.setattr(
        system_admin_config,
        'integration_enabled',
        lambda name: name == 'log_shipping',
    )

    summary = system_admin_config.public_integration_config_summary()

    assert summary['providers']['search_export_provider'] == 'relativity'
    assert summary['enabled']['log_shipping'] is True


def test_log_shipping_ignores_legacy_config_env_after_setup(monkeypatch):
    _clear_log_ship_env(monkeypatch)
    monkeypatch.setenv('LOG_SHIP_ENABLED', '1')
    monkeypatch.setenv('LOG_SHIP_TENANT_ID', 'legacy-tenant')
    monkeypatch.setenv('LOG_SHIP_CLIENT_SECRET', 'legacy-secret')
    monkeypatch.setattr(
        log_shipping,
        'load_stored_system_settings',
        lambda: {
            'initial_setup_completed': True,
            'enabled_integrations': {},
            'integration_configs': {'log_shipping': {}},
        },
    )

    settings = log_shipping.load_log_shipping_settings()

    assert settings.enabled is False
    assert settings.tenant_id == ''
    assert settings.client_secret == ''
    assert settings.target == 'sharepoint'