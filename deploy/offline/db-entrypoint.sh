#!/usr/bin/env bash
# Normalize both secrets before the official PostgreSQL entrypoint reads either.
set -euo pipefail
export LC_ALL=C
normalize_secret() {
    local source=$1 destination=$2 value original_size
    # A sentinel preserves trailing newlines. Byte count also detects stripped NULs.
    value=$(cat -- "$source"; printf '.')
    value=${value%.}
    original_size=$(wc -c < "$source")
    if [[ ${#value} -ne $original_size ]]; then
        echo 'Invalid database password file' >&2; return 1
    fi
    case "$value" in
        *$'\r\n') value=${value%$'\r\n'} ;;
        *$'\n') value=${value%$'\n'} ;;
    esac
    if [[ -z $value || $value == *$'\r'* || $value == *$'\n'* || $value == $'\xef\xbb\xbf'* ]]; then
        echo 'Invalid database password file' >&2; return 1
    fi
    printf '%s' "$value" > "$destination"
    chmod 600 "$destination"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    umask 077
    secret_dir=$(mktemp -d /run/wellspring-secrets/passwords.XXXXXXXX)
    normalize_secret /run/secrets/db_owner_password "$secret_dir/owner"
    normalize_secret /run/secrets/runtime_password "$secret_dir/runtime"
    if [[ $(id -u) == 0 ]]; then
        chown -R postgres:postgres "$secret_dir"
    fi
    export POSTGRES_PASSWORD_FILE="$secret_dir/owner"
    export WELLSPRING_RUNTIME_PASSWORD_FILE="$secret_dir/runtime"
    exec /usr/local/bin/docker-entrypoint.sh "$@"
fi
