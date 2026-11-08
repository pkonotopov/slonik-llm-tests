#!/usr/bin/env bash
# Run a Python SQL check against the built PostgreSQL in /build.
set -euo pipefail
root=$(mktemp -d /tmp/pg-returning-old.XXXXXX)
install=/build/install/usr/local/pgsql
bin=$install/bin
export LD_LIBRARY_PATH="$install/lib" PGHOST="$root" PGUSER=bench PGDATABASE=postgres
trap 'if [[ -f "$root/data/postmaster.pid" ]]; then "$bin/pg_ctl" -D "$root/data" -m immediate -w stop >/dev/null; fi; rm -rf "$root"' EXIT
if [[ ! -f /build/Makefile ]]; then
    (cd /build && CFLAGS=-O0 /work/configure --enable-cassert) >"$root/configure.log" 2>&1 || { tail -50 "$root/configure.log"; exit 1; }
fi
make -C /build -j2 >"$root/build.log" 2>&1 || { tail -50 "$root/build.log"; exit 1; }
make -C /build -j2 install DESTDIR=/build/install >"$root/install.log" 2>&1 || { tail -50 "$root/install.log"; exit 1; }
"$bin/initdb" -D "$root/data" -A trust -U bench --no-locale -E UTF8 >/dev/null
options="-k $root -c listen_addresses=''"
if [[ ${1:-} == replication ]]; then options="$options -c wal_level=logical"; fi
"$bin/pg_ctl" -D "$root/data" -l "$root/postgres.log" -o "$options" -w start >/dev/null
if [[ ${1:-} == replication ]]; then
    if ! bash /bench/check-replication.sh "$bin/psql"; then
        tail -25 "$root/postgres.log"
        exit 1
    fi
elif [[ ${1:-} == upstream-isolation ]]; then
    make -C /build/src/test/isolation -j2 isolationtester pg_isolation_regress >"$root/isolation-build.log" 2>&1 || { tail -50 "$root/isolation-build.log"; exit 1; }
    mkdir -p /build/upstream-isolation
    /build/src/test/isolation/pg_isolation_regress --use-existing --dbname=postgres \
        --bindir="$bin" --inputdir=/bench/upstream-isolation --outputdir=/build/upstream-isolation \
        eval-plan-qual-trigger merge-match-recheck
elif [[ ${1:-} == judge ]]; then
    exec_mode=/bench/judge.py
    python3 -B "$exec_mode" "$bin/psql"
else
    python3 -B /bench/repro.py -- "$bin/psql"
fi
