#!/usr/bin/env bash
set -euo pipefail

PGDATA="${PGDATA:-/tmp/pgdata}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-pythinker_sandbox}"
PG_BIN="$(pg_config --bindir)"

# Create PostgreSQL socket directory in /tmp (postgres user has write access)
# Using /tmp instead of /var/run/postgresql since /run is tmpfs with root-only write
PGSOCKET_DIR="/tmp/pgsocket"
mkdir -p "$PGSOCKET_DIR"
chmod 755 "$PGSOCKET_DIR"

mkdir -p "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  "$PG_BIN/initdb" -D "$PGDATA" --username="$PGUSER" --no-locale
  {
    echo "listen_addresses='${PGHOST}'"
    echo "port=${PGPORT}"
    echo "unix_socket_directories='${PGSOCKET_DIR}'"
  } >> "$PGDATA/postgresql.conf"
  {
    echo "local all all trust"
    echo "host all all 127.0.0.1/32 trust"
  } >> "$PGDATA/pg_hba.conf"
fi

"$PG_BIN/postgres" -D "$PGDATA" -c listen_addresses="$PGHOST" -p "$PGPORT" -c unix_socket_directories="$PGSOCKET_DIR" &
pg_pid=$!

until "$PG_BIN/pg_isready" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
  sleep 0.2
done

if ! "$PG_BIN/psql" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
  -tc "SELECT 1 FROM pg_database WHERE datname='${PGDATABASE}'" | grep -q 1; then
  "$PG_BIN/psql" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
    -c "CREATE DATABASE ${PGDATABASE};"
fi

wait "$pg_pid"
