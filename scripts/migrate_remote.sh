#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration (Override via environment variables if needed)
# -----------------------------------------------------------------------------
LOCAL_DIR="${LOCAL_DIR:-$(pwd)}"
REMOTE_USER="${REMOTE_USER:-elio}"
REMOTE_HOST="${REMOTE_HOST:-178.238.234.86}"
REMOTE_PROJECT_DIR="${REMOTE_PROJECT_DIR:-/home/elio/guillermo}"
REMOTE_MEDIA_DIR="${REMOTE_MEDIA_DIR:-/home/elio/media/guillermo}"
DUMP_FILE="${LOCAL_DIR}/db_dump.json"

# -----------------------------------------------------------------------------
# Pipeline Steps (Command / Pipeline Pattern)
# -----------------------------------------------------------------------------

dump_database() {
    echo "==> Exporting local database to JSON fixture..."
    python manage.py dumpdata \
        --natural-foreign \
        --natural-primary \
        -e contenttypes \
        -e auth.Permission \
        --indent 2 > "${DUMP_FILE}"
}

sync_dump() {
    echo "==> Transferring database fixture via SSH..."
    rsync -avz -e ssh "${DUMP_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PROJECT_DIR}/"
}

sync_media() {
    echo "==> Transferring media directory to separate remote storage..."
    ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_MEDIA_DIR}'"
    rsync -avz --progress -e ssh "${LOCAL_DIR}/media/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_MEDIA_DIR}/"
}

configure_remote_env() {
    echo "==> Configuring remote environment (.env) for Postgres and Media..."
    ssh "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<EOF
set -euo pipefail
ENV_FILE="${REMOTE_PROJECT_DIR}/project/.env"
touch "\$ENV_FILE"

# Update DATABASE_TYPE and MEDIA_ROOT
grep -q '^DATABASE_TYPE=' "\$ENV_FILE" && sed -i 's/^DATABASE_TYPE=.*/DATABASE_TYPE=postgres/' "\$ENV_FILE" || echo 'DATABASE_TYPE=postgres' >> "\$ENV_FILE"
grep -q '^MEDIA_ROOT=' "\$ENV_FILE" && sed -i 's|^MEDIA_ROOT=.*|MEDIA_ROOT=${REMOTE_MEDIA_DIR}|' "\$ENV_FILE" || echo 'MEDIA_ROOT=${REMOTE_MEDIA_DIR}' >> "\$ENV_FILE"
EOF
}

load_remote_data() {
    echo "==> Running migrations and loading data on remote PostgreSQL..."
    ssh "${REMOTE_USER}@${REMOTE_HOST}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_PROJECT_DIR}"
python manage.py migrate
python manage.py loaddata db_dump.json
rm -f db_dump.json
EOF
}

cleanup_local() {
    echo "==> Cleaning local dump artifact..."
    rm -f "${DUMP_FILE}"
}

main() {
    dump_database
    sync_dump
    sync_media
    configure_remote_env
    load_remote_data
    cleanup_local
    echo "==> Done: Database and media migrated successfully."
}

main "\$@"
