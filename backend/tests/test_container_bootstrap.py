from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_entrypoint_generates_and_persists_required_secrets():
    entrypoint = (ROOT / "backend" / "entrypoint.sh").read_text(encoding="utf-8")

    for key in ("SECRET_KEY", "SETTINGS_ENCRYPTION_KEY", "BACKUP_ENCRYPTION_KEY"):
        assert f"Generated and persisted {key}" in entrypoint
        assert f"grep -v '^{key}='" in entrypoint
        assert f"export {key}" in entrypoint


def test_env_example_omits_generated_secrets():
    template = (ROOT / ".env.example").read_text(encoding="utf-8")

    for key in ("SECRET_KEY", "SETTINGS_ENCRYPTION_KEY", "BACKUP_ENCRYPTION_KEY"):
        assert not any(line.startswith(f"{key}=") for line in template.splitlines())