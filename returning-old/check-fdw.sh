#!/usr/bin/env bash
set -euo pipefail
root=$(mktemp -d /tmp/pg-epq-fdw.XXXXXX)
install=/build/install/usr/local/pgsql
bin=$install/bin
export LD_LIBRARY_PATH="$install/lib" PGHOST="$root" PGUSER=bench PGDATABASE=postgres
trap 'if [[ -f "$root/data/postmaster.pid" ]]; then "$bin/pg_ctl" -D "$root/data" -m immediate -w stop >/dev/null; fi; rm -rf "$root"' EXIT
make -C /build/contrib/postgres_fdw -j2 all install DESTDIR=/build/install >"$root/fdw.log" 2>&1 || { tail -50 "$root/fdw.log"; exit 1; }
"$bin/initdb" -D "$root/data" -A trust -U bench --no-locale -E UTF8 >/dev/null
"$bin/pg_ctl" -D "$root/data" -l "$root/postgres.log" -o "-k $root -c unix_socket_directories=$root -c listen_addresses=''" -w start >/dev/null
if ! python3 -B /bench/check-fdw.py "$bin/psql"; then
    grep -m 1 "TRAP:" "$root/postgres.log" || true
    tail -30 "$root/postgres.log"
    exit 1
fi
