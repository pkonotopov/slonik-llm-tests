"""Exercise a canceled local row followed by a foreign row in one UPDATE."""
import asyncio
import json
import sys

from repro import Session


async def main(command):
    observer, first, second = [await Session.open(command) for _ in range(3)]
    update = 'UPDATE epq_parent SET n = n + 1 RETURNING OLD.n, NEW.n'
    try:
        for sql in (
            'CREATE EXTENSION postgres_fdw',
            """CREATE SERVER epq_server FOREIGN DATA WRAPPER postgres_fdw
                OPTIONS (dbname 'postgres')""",
            'CREATE USER MAPPING FOR CURRENT_USER SERVER epq_server',
            'CREATE TABLE epq_parent (id int, n int) PARTITION BY RANGE (id)',
            'CREATE TABLE epq_local PARTITION OF epq_parent FOR VALUES FROM (0) TO (10)',
            'CREATE TABLE epq_remote (id int, n int)',
            """CREATE FOREIGN TABLE epq_foreign PARTITION OF epq_parent
                FOR VALUES FROM (10) TO (20) SERVER epq_server
                OPTIONS (table_name 'epq_remote')""",
            'INSERT INTO epq_local VALUES (1, 7)',
            'INSERT INTO epq_remote VALUES (11, 99)',
            """CREATE FUNCTION epq_cancel() RETURNS trigger LANGUAGE plpgsql
                AS $$ BEGIN IF NEW.n = 18 THEN RETURN NULL; END IF; RETURN NEW; END $$""",
            """CREATE TRIGGER epq_cancel BEFORE UPDATE ON epq_local
                FOR EACH ROW EXECUTE FUNCTION epq_cancel()""",
        ):
            await observer.check(sql)
        plan = await second.check('EXPLAIN (COSTS OFF) ' + update)
        print('\n'.join(plan), flush=True)
        a = int((await first.check('SELECT pg_backend_pid()'))[0])
        b = int((await second.check('SELECT pg_backend_pid()'))[0])
        await first.check('BEGIN')
        await first.check('UPDATE epq_local SET n = n + 10')
        pending = asyncio.create_task(second.sql(update))
        async with asyncio.timeout(12):
            while await observer.check(f'SELECT {a} = ANY(pg_blocking_pids({b}))') != ['t']:
                if pending.done():
                    raise RuntimeError(f'No row lock wait: {await pending}')
                await asyncio.sleep(0.05)
        await first.check('COMMIT')
        try:
            status, rows = await pending
        except RuntimeError as exc:
            status, rows = str(exc), []
        print(json.dumps({'sqlstate': status, 'returning': rows}), flush=True)
        return (status, rows) != ('00000', ['99|100'])
    finally:
        for session in (first, second, observer):
            await session.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv[1:] or ['psql'])))
