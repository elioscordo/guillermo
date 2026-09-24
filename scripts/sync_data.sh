#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration Loader
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$(dirname "${SCRIPT_DIR}")"
ENV_FILE="${LOCAL_DIR}/project/.env"

load_env() {
    if [[ -f "${ENV_FILE}" ]]; then
        set -o allexport
        # shellcheck disable=SC1090
        source "${ENV_FILE}"
        set +o allexport
    else
        echo "Error: Environment file not found at ${ENV_FILE}" >&2
        exit 1
    fi
}

init_vars() {
    load_env
    REMOTE_SSH_PORT="${SYNC_REMOTE_PORT:-22}"
    REMOTE_TARGET="${SYNC_REMOTE_USER}@${SYNC_REMOTE_HOST}"
    LOCAL_MEDIA_DIR="${MEDIA_ROOT:-${LOCAL_DIR}/media}"
}

# -----------------------------------------------------------------------------
# Reusable Operations (Single Responsibility)
# -----------------------------------------------------------------------------
run_remote() {
    ssh -p "${REMOTE_SSH_PORT}" "${REMOTE_TARGET}" "$1"
}

sync_media() {
    local src="$1"
    local dst="$2"
    rsync -avz --progress -e "ssh -p ${REMOTE_SSH_PORT}" "${src}/" "${dst}/"
}

dump_local() {
    cd "${LOCAL_DIR}"
    python manage.py dumpdata --natural-foreign --natural-primary \
        -e contenttypes -e auth.Permission --indent 2 > "${LOCAL_DIR}/db_sync.json"
}

load_local() {
    cd "${LOCAL_DIR}"
    python manage.py migrate
    python manage.py loaddata "${LOCAL_DIR}/db_sync.json"
    rm -f "${LOCAL_DIR}/db_sync.json"
}

# -----------------------------------------------------------------------------
# Strategies: Push (Local -> Remote) & Pull (Remote -> Local)
# -----------------------------------------------------------------------------
strategy_push() {
    echo "==> [PUSH] 1/4 Dumping local database..."
    dump_local

    echo "==> [PUSH] 2/4 Transferring dump to remote..."
    rsync -avz -e "ssh -p ${REMOTE_SSH_PORT}" "${LOCAL_DIR}/db_sync.json" "${REMOTE_TARGET}:${SYNC_REMOTE_PROJECT_DIR}/"
    rm -f "${LOCAL_DIR}/db_sync.json"

    echo "==> [PUSH] 3/4 Loading dump into remote database..."
    run_remote "cd '${SYNC_REMOTE_PROJECT_DIR}' && python manage.py migrate && python manage.py loaddata db_sync.json && rm -f db_sync.json"

    echo "==> [PUSH] 4/4 Syncing media to remote..."
    run_remote "mkdir -p '${SYNC_REMOTE_MEDIA_DIR}'"
    sync_media "${LOCAL_MEDIA_DIR}" "${REMOTE_TARGET}:${SYNC_REMOTE_MEDIA_DIR}"
    echo "==> [PUSH] Completed successfully."
}

strategy_pull() {
    echo "==> [PULL] 1/4 Dumping remote database..."
    run_remote "cd '${SYNC_REMOTE_PROJECT_DIR}' && python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 2 > db_sync.json"

    echo "==> [PULL] 2/4 Transferring dump to local..."
    rsync -avz -e "ssh -p ${REMOTE_SSH_PORT}" "${REMOTE_TARGET}:${SYNC_REMOTE_PROJECT_DIR}/db_sync.json" "${LOCAL_DIR}/"
    run_remote "rm -f '${SYNC_REMOTE_PROJECT_DIR}/db_sync.json'"

    echo "==> [PULL] 3/4 Loading dump into local database..."
    load_local

    echo "==> [PULL] 4/4 Syncing media to local..."
    mkdir -p "${LOCAL_MEDIA_DIR}"
    sync_media "${REMOTE_TARGET}:${SYNC_REMOTE_MEDIA_DIR}" "${LOCAL_MEDIA_DIR}"
    echo "==> [PULL] Completed successfully."
}

# -----------------------------------------------------------------------------
# Entrypoint Router
# -----------------------------------------------------------------------------
main() {
    init_vars
    case "${1:-}" in
        push)
            strategy_push
            ;;
        pull)
            strategy_pull
            ;;
        *)
            echo "Usage: $0 {push|pull}"
            echo "  push : Local DB & Media  -->  Remote DB & Media"
            echo "  pull : Remote DB & Media -->  Local DB & Media"
            exit 1
            ;;
    esac
}

main "$@"
