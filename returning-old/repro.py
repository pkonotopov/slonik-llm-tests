#!/usr/bin/env python3
"""Two-session reproduction of PostgreSQL bug #19536 using psql."""

import argparse
import asyncio
import json
import uuid


class Session:
    def __init__(self, process):
        self.process = process

    @classmethod
    async def open(cls, command):
        process = await asyncio.create_subprocess_exec(
            *command, '-XqAt', '-v', 'ON_ERROR_STOP=0',
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return cls(process)

    async def sql(self, statement):
        marker = 'done_' + uuid.uuid4().hex
        self.process.stdin.write(f"{statement.rstrip(';')};\n\\echo {marker} :SQLSTATE\n".encode())
        await self.process.stdin.drain()
        rows = []
        while line := await asyncio.wait_for(self.process.stdout.readline(), 25):
            value = line.decode().rstrip('\r\n')
            if value.startswith(marker + ' '):
                return value.split()[1], rows
            rows.append(value)
        raise RuntimeError('psql exited before returning a result')

    async def check(self, statement):
        status, rows = await self.sql(statement)
        if status != '00000':
            raise RuntimeError(f'psql SQLSTATE {status} for {statement}')
        return rows

    async def close(self):
        if self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()


async def case(command, *, trigger=True, finish='COMMIT', predicate='id = 1', isolation='READ COMMITTED'):
    schema = 'returning_old_' + uuid.uuid4().hex
    observer, first, second = [await Session.open(command) for _ in range(3)]
    pending = None
    try:
        await observer.check(f'CREATE SCHEMA {schema}')
        await observer.check(f'CREATE TABLE {schema}.t (id int PRIMARY KEY, n int NOT NULL)')
        await observer.check(f'INSERT INTO {schema}.t VALUES (1, 7)')
        if trigger:
            await observer.check(f'''CREATE FUNCTION {schema}.pass_new() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END; $$''')
            await observer.check(f'''CREATE TRIGGER touch BEFORE UPDATE ON {schema}.t
                FOR EACH ROW EXECUTE FUNCTION {schema}.pass_new()''')
        a = int((await first.check('SELECT pg_backend_pid()'))[0])
        b = int((await second.check('SELECT pg_backend_pid()'))[0])
        await first.check('BEGIN')
        await first.check(f'UPDATE {schema}.t SET n = n + 10 WHERE id = 1')
        await second.check(f'BEGIN ISOLATION LEVEL {isolation}')
        pending = asyncio.create_task(second.sql(f'''UPDATE {schema}.t SET n = n + 1
            WHERE {predicate} RETURNING OLD.n, NEW.n'''))
        async with asyncio.timeout(12):
            while await observer.check(f'SELECT {a} = ANY(pg_blocking_pids({b}))') != ['t']:
                if pending.done():
                    raise RuntimeError(f'Expected row-lock wait, got {await pending}')
                await asyncio.sleep(0.05)
        await first.check(finish)
        status, rows = await pending
        await second.check('ROLLBACK' if status != '00000' else 'COMMIT')
        final = await observer.check(f'SELECT n FROM {schema}.t WHERE id = 1')
        return {'sqlstate': status, 'returning': rows, 'stored': final}
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await first.close()
        await second.close()
        try:
            await observer.check(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        finally:
            await observer.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect', choices=['stale', 'fixed'])
    parser.add_argument('psql', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.psql[1:] if args.psql[:1] == ['--'] else args.psql
    result = await case(command or ['psql'])
    print(json.dumps(result), flush=True)
    if args.expect:
        old = '7' if args.expect == 'stale' else '17'
        if result != {'sqlstate': '00000', 'returning': [f'{old}|18'], 'stored': ['18']}:
            raise SystemExit(f'Expected {args.expect} behavior, got {result}')


if __name__ == '__main__':
    asyncio.run(main())
