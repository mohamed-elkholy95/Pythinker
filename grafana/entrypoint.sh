#!/bin/sh
# Custom Grafana entrypoint: force-sync admin password from env var on every
# startup, even when the sqlite DB has a stale password from a previous boot.
#
# Problem: GF_SECURITY_ADMIN_PASSWORD only sets the password on first init.
# After volume persistence, manual UI password changes stick, making the .env
# value useless and locking out API/provisioning automation.
#
# Solution: Reset via grafana-cli before handing off to the default entrypoint.
# grafana-cli writes directly to the DB, and the main process picks it up.

set -e

ADMIN_PASSWORD="${GF_SECURITY_ADMIN_PASSWORD:-admin}"

# grafana-cli needs the homepath to find the DB
grafana-cli --homepath /usr/share/grafana \
            --config /usr/share/grafana/conf/defaults.ini \
            admin reset-admin-password "$ADMIN_PASSWORD" >/dev/null 2>&1 || true

# Hand off to the default Grafana entrypoint
exec /run.sh "$@"
