#!/bin/sh
set -e

prepare_writable_dir() {
  dir="$1"
  if [ -z "$dir" ]; then
    return 0
  fi
  mkdir -p "$dir"
  chown -R app:app "$dir" 2>/dev/null || true
  chmod -R u+rwX,g+rwX "$dir" 2>/dev/null || true
  if ! gosu app test -w "$dir" 2>/dev/null; then
    chmod -R a+rwX "$dir" 2>/dev/null || true
  fi
  if ! gosu app test -w "$dir" 2>/dev/null; then
    echo "[entrypoint] WARNING: app user cannot write to $dir"
  fi
}

prepare_file_parent() {
  file_path="$1"
  if [ -z "$file_path" ]; then
    return 0
  fi
  prepare_writable_dir "$(dirname "$file_path")"
}

LOG_DIR="${LOG_DIR:-/app/logs}"
AUDIT_LOG_DIR="${AUDIT_LOG_DIR:-$LOG_DIR}"
BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
BACKUP_LOG_FILE="${BACKUP_LOG_FILE:-/app/logs/backup.log}"
APP_RUNTIME_DIR="${APP_RUNTIME_DIR:-/app/run}"
CASE_REQUEST_UPLOAD_DIR="${CASE_REQUEST_UPLOAD_DIR:-/app/case_request_uploads}"
CASE_IMPORT_REPORT_DIR="${CASE_IMPORT_REPORT_DIR:-/app/import_reports}"
LOG_SHIP_WORK_DIR="${LOG_SHIP_WORK_DIR:-/app/run/log_ship}"
ADMIN_SEED_STATE_PATH="${ADMIN_SEED_STATE_PATH:-/app/data/.admin_seed_state.json}"
TOOLS_SAFE_ROOT="${TOOLS_SAFE_ROOT:-}"

export LOG_DIR AUDIT_LOG_DIR BACKUP_DIR BACKUP_LOG_FILE APP_RUNTIME_DIR CASE_REQUEST_UPLOAD_DIR CASE_IMPORT_REPORT_DIR LOG_SHIP_WORK_DIR ADMIN_SEED_STATE_PATH

APP_CONFIG_DIR="${APP_DATA_DIR:-/data/system}"
BOOTSTRAP_ENV_FILE="$APP_CONFIG_DIR/bootstrap.env"

prepare_writable_dir "$LOG_DIR"
prepare_writable_dir "$AUDIT_LOG_DIR"
prepare_writable_dir "$BACKUP_DIR"
prepare_file_parent "$BACKUP_LOG_FILE"
prepare_writable_dir "$APP_RUNTIME_DIR"
prepare_writable_dir "$LOG_SHIP_WORK_DIR"
prepare_writable_dir "$APP_CONFIG_DIR"
prepare_writable_dir "$APP_CONFIG_DIR/tls"
prepare_writable_dir "$CASE_REQUEST_UPLOAD_DIR"
prepare_writable_dir "$CASE_REQUEST_UPLOAD_DIR/consent_proofs"
prepare_writable_dir "$CASE_IMPORT_REPORT_DIR"
prepare_file_parent "$ADMIN_SEED_STATE_PATH"
if [ -n "$TOOLS_SAFE_ROOT" ]; then
  prepare_writable_dir "$TOOLS_SAFE_ROOT"
fi

if [ -d "/certs" ]; then
  prepare_writable_dir "/certs"
fi

if [ -n "$APP_DATA_DIR" ]; then
  prepare_writable_dir "$APP_DATA_DIR"
fi

if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
  . "$BOOTSTRAP_ENV_FILE"
fi

is_placeholder_secret() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    ""|"please-change-this"|"change-me"|"changeme"|"password"|"secret"|"secret_key"|"admin"|"please-set-a-strong-password")
      return 0
      ;;
  esac
  return 1
}

if is_placeholder_secret "${SECRET_KEY:-}" || [ "${#SECRET_KEY}" -lt 32 ]; then
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export SECRET_KEY
  umask 077
  tmp_file="${BOOTSTRAP_ENV_FILE}.tmp"
  if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
    grep -v '^SECRET_KEY=' "$BOOTSTRAP_ENV_FILE" > "$tmp_file" || true
  else
    : > "$tmp_file"
  fi
  printf "SECRET_KEY='%s'\n" "$SECRET_KEY" >> "$tmp_file"
  mv "$tmp_file" "$BOOTSTRAP_ENV_FILE"
  chown app:app "$BOOTSTRAP_ENV_FILE" || true
  echo "[entrypoint] Generated and persisted SECRET_KEY in $BOOTSTRAP_ENV_FILE"
else
  export SECRET_KEY
fi

if is_placeholder_secret "${SETTINGS_ENCRYPTION_KEY:-}" || [ "${#SETTINGS_ENCRYPTION_KEY}" -lt 32 ]; then
  SETTINGS_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  export SETTINGS_ENCRYPTION_KEY
  umask 077
  tmp_file="${BOOTSTRAP_ENV_FILE}.tmp"
  if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
    grep -v '^SETTINGS_ENCRYPTION_KEY=' "$BOOTSTRAP_ENV_FILE" > "$tmp_file" || true
  else
    : > "$tmp_file"
  fi
  printf "SETTINGS_ENCRYPTION_KEY='%s'\n" "$SETTINGS_ENCRYPTION_KEY" >> "$tmp_file"
  mv "$tmp_file" "$BOOTSTRAP_ENV_FILE"
  chown app:app "$BOOTSTRAP_ENV_FILE" || true
  echo "[entrypoint] Generated and persisted SETTINGS_ENCRYPTION_KEY in $BOOTSTRAP_ENV_FILE"
else
  export SETTINGS_ENCRYPTION_KEY
fi

if is_placeholder_secret "${BACKUP_ENCRYPTION_KEY:-}" || [ "${#BACKUP_ENCRYPTION_KEY}" -lt 43 ]; then
  BACKUP_ENCRYPTION_KEY="$(python -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
  export BACKUP_ENCRYPTION_KEY
  umask 077
  tmp_file="${BOOTSTRAP_ENV_FILE}.tmp"
  if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
    grep -v '^BACKUP_ENCRYPTION_KEY=' "$BOOTSTRAP_ENV_FILE" > "$tmp_file" || true
  else
    : > "$tmp_file"
  fi
  printf "BACKUP_ENCRYPTION_KEY='%s'\n" "$BACKUP_ENCRYPTION_KEY" >> "$tmp_file"
  mv "$tmp_file" "$BOOTSTRAP_ENV_FILE"
  chown app:app "$BOOTSTRAP_ENV_FILE" || true
  echo "[entrypoint] Generated and persisted BACKUP_ENCRYPTION_KEY in $BOOTSTRAP_ENV_FILE"
else
  export BACKUP_ENCRYPTION_KEY
fi

if [ -z "${SETUP_BOOTSTRAP_SECRET:-}" ] || [ "${#SETUP_BOOTSTRAP_SECRET}" -lt 24 ]; then
  SETUP_BOOTSTRAP_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  umask 077
  tmp_file="${BOOTSTRAP_ENV_FILE}.tmp"
  if [ -f "$BOOTSTRAP_ENV_FILE" ]; then
    grep -v '^SETUP_BOOTSTRAP_SECRET=' "$BOOTSTRAP_ENV_FILE" > "$tmp_file" || true
  else
    : > "$tmp_file"
  fi
  printf "SETUP_BOOTSTRAP_SECRET='%s'\n" "$SETUP_BOOTSTRAP_SECRET" >> "$tmp_file"
  mv "$tmp_file" "$BOOTSTRAP_ENV_FILE"
  chown app:app "$BOOTSTRAP_ENV_FILE" || true
  chmod 600 "$BOOTSTRAP_ENV_FILE" || true
  echo "[entrypoint] Generated and persisted one-time setup code in $BOOTSTRAP_ENV_FILE"
fi
export SETUP_BOOTSTRAP_SECRET

SYSTEM_SETTINGS_FILE="$APP_CONFIG_DIR/system_settings.json"
if [ ! -f "$SYSTEM_SETTINGS_FILE" ] || ! grep -Eq '"initial_setup_completed"[[:space:]]*:[[:space:]]*true' "$SYSTEM_SETTINGS_FILE"; then
  echo "[setup] One-time setup code: $SETUP_BOOTSTRAP_SECRET"
  echo "[setup] Enter this code on the Administrator step. It is required only for initial setup."
fi
if [ -z "${DATABASE_URL:-}" ]; then
  POSTGRES_USER="${POSTGRES_USER:-ediscovery}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ediscovery-internal-db}"
  POSTGRES_DB="${POSTGRES_DB:-ediscovery}"
  DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  export DATABASE_URL
fi

# Run DB migrations (PostgreSQL) unless disabled.
if [ -z "${DISABLE_AUTO_MIGRATIONS:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] Running migrations..."
  gosu app python /app/scripts/run_migrations.py
fi

exec gosu app "$@"
