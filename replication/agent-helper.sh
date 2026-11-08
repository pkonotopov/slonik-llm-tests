#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f /build/Makefile ]]; then
    (cd /build && CFLAGS=-O0 /work/configure --enable-cassert --enable-tap-tests) >/build/configure.log 2>&1 ||
        { tail -40 /build/configure.log; exit 1; }
fi
make -C /build -j4 >/build/build.log 2>&1 || { tail -40 /build/build.log; exit 1; }
make -C /build -j4 install DESTDIR=/build/install >/build/install.log 2>&1 ||
    { tail -40 /build/install.log; exit 1; }
install=/build/install/usr/local/pgsql
export LD_LIBRARY_PATH="$install/lib"
exec python3 -B /bench/probe.py "$install/bin" --require-reclaim "$@"
