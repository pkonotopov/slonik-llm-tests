#!/usr/bin/env bash
# Run only on a disposable cluster with wal_level=logical and a local socket.
set -euo pipefail
psql=$1
query() { "$psql" -XqAt -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }

query postgres 'CREATE DATABASE pub_db'
query postgres 'CREATE DATABASE sub_db'
for database in pub_db sub_db; do
    query "$database" 'CREATE TABLE t (id int PRIMARY KEY, n int); INSERT INTO t VALUES (1, 7)'
done
query pub_db 'CREATE PUBLICATION upd_pub FOR TABLE t'
query pub_db "SELECT pg_create_logical_replication_slot('upd_slot', 'pgoutput')" >/dev/null
"$psql" -Xq -v ON_ERROR_STOP=1 -d sub_db <<'SQL'
CREATE FUNCTION bump() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.n := NEW.n + 100;
    RETURN NEW;
END
$$;
CREATE TRIGGER bump_n BEFORE UPDATE ON t FOR EACH ROW EXECUTE FUNCTION bump();
ALTER TABLE t ENABLE REPLICA TRIGGER bump_n;
SQL
query sub_db "CREATE SUBSCRIPTION upd_sub CONNECTION 'host=$PGHOST dbname=pub_db user=$PGUSER' PUBLICATION upd_pub WITH (create_slot=false, copy_data=false, slot_name='upd_slot')"
query pub_db 'UPDATE t SET n = 17 WHERE id = 1'
for attempt in {1..100}; do
    value=$(query sub_db 'SELECT n FROM t WHERE id = 1')
    if [[ "$value" == 117 ]]; then
        printf 'Publisher n=17; subscriber n=117 after replica BEFORE UPDATE trigger.\n'
        exit 0
    fi
    sleep 0.1
done
printf 'Subscriber n=%s; expected 117.\n' "$value" >&2
exit 1
