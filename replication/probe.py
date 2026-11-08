#!/usr/bin/env python3
"""Exercise a savepoint rollback after real queue-to-file fallback on a subscriber."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time


def wait_for(predicate, label, seconds=35):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise RuntimeError(f'timed out waiting for {label}')


class Cluster:
    def __init__(self, root, bin_dir, name, port):
        self.root = root / name
        self.bin = bin_dir
        self.port = port
        self.log = root / (name + '.log')
        self.sock = root
        self.data = self.root / 'data'
        self.root.mkdir()
        self.conn = f'host={root} port={port} user=bench dbname=postgres'

    def start(self):
        subprocess.run([self.bin / 'initdb', '-D', self.data, '-A', 'trust',
                        '-U', 'bench', '--no-locale', '-E', 'UTF8'], check=True,
                       stdout=subprocess.DEVNULL)
        with (self.data / 'postgresql.conf').open('a') as file:
            file.write(f"""
listen_addresses = ''
port = {self.port}
unix_socket_directories = '{self.sock}'
wal_level = logical
max_replication_slots = 5
max_wal_senders = 5
max_logical_replication_workers = 4
max_parallel_apply_workers_per_subscription = 2
wal_receiver_status_interval = 1
log_min_messages = debug1
log_error_verbosity = verbose
""")
        subprocess.run([self.bin / 'pg_ctl', '-D', self.data, '-l', self.log, '-w', 'start'],
                       check=True, stdout=subprocess.DEVNULL, timeout=30)

    def stop(self):
        if (self.data / 'postmaster.pid').exists():
            subprocess.run([self.bin / 'pg_ctl', '-D', self.data, '-m', 'immediate',
                            '-w', 'stop'], stdout=subprocess.DEVNULL, timeout=30, check=True)

    def sql(self, query):
        return subprocess.check_output(self.command() + ['-c', query], text=True,
                                       timeout=25).strip()

    def command(self):
        return [str(self.bin / 'psql'), '-XqAt', '-v', 'ON_ERROR_STOP=1', '-d', self.conn]

    def log_text(self):
        return self.log.read_text(errors='replace')

    def spool_bytes(self):
        files = self.data.glob('base/pgsql_tmp/*/*.changes.*')
        total = 0
        for file in files:
            try:
                total += file.stat().st_size
            except FileNotFoundError:
                continue
        return total


class Session:
    def __init__(self, cluster):
        self.process = subprocess.Popen(cluster.command(), text=True, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, bufsize=1)

    def exec(self, sql):
        self.process.stdin.write(sql + "\n\\echo ready\n")
        self.process.stdin.flush()
        lines = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError(f'psql stopped before executing {sql[:120]}')
            if line.rstrip() == 'ready':
                return '\n'.join(lines)
            lines.append(line.rstrip())

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()


SCHEMA = """
CREATE TABLE ledger(id int PRIMARY KEY, amount int, payload text);
CREATE TABLE gate(id int PRIMARY KEY);
CREATE TABLE barrier(id int PRIMARY KEY);
"""
ROWS = "SELECT id, amount FROM ledger ORDER BY id"


def exercise(pub, sub, mode, segments, require_reclaim, wait_seconds, nested):
    def flush():
        pub.sql("SELECT pg_logical_emit_message(false, 'bench-flush', '', true)")
    pub.sql(SCHEMA)
    sub.sql(SCHEMA)
    pub.sql("ALTER SYSTEM SET debug_logical_replication_streaming TO immediate")
    pub.sql("SELECT pg_reload_conf()")
    pub.sql('CREATE PUBLICATION batch_pub FOR TABLE ledger, gate, barrier')
    sub.sql(f"CREATE SUBSCRIPTION batch_sub CONNECTION '{pub.conn}' "
            f"PUBLICATION batch_pub WITH (copy_data=false, streaming={mode})")
    wait_for(lambda: pub.sql("SELECT 1 FROM pg_stat_replication WHERE application_name='batch_sub' AND state='streaming'"),
             'subscription streaming')
    pub.sql('INSERT INTO barrier VALUES (0)')
    wait_for(lambda: sub.sql('SELECT 1 FROM barrier WHERE id=0'), 'initial barrier')

    log_start = len(sub.log_text())
    writer, locker = Session(pub), Session(sub)
    before_bytes = after_bytes = None
    try:
        writer.exec("BEGIN; INSERT INTO ledger VALUES (1,10);")
        if nested:
            writer.exec("SAVEPOINT parent; INSERT INTO ledger VALUES (9,90);")
        writer.exec("SAVEPOINT batch; INSERT INTO ledger VALUES (2,100);")
        flush()
        hybrid = mode == 'parallel' and segments > 0
        if hybrid:
            wait_for(lambda: 'defining savepoint' in sub.log_text(), 'parallel savepoint')
            locker.exec("BEGIN; LOCK TABLE gate IN ACCESS EXCLUSIVE MODE;")
            writer.exec("INSERT INTO gate VALUES (2);")
            flush()
            wait_for(lambda: sub.sql("""
                SELECT 1 FROM pg_stat_subscription
                WHERE leader_pid IS NOT NULL AND cardinality(pg_blocking_pids(pid)) > 0
                """), 'parallel apply blocked on gate')
        for n in range(segments):
            writer.exec(f"INSERT INTO ledger VALUES ({3 + n},200,repeat('x', 20*1024*1024));")
            flush()
            if hybrid:
                limit = (n + 1) * 20 * 1024 * 1024
                wait_for(lambda: sub.spool_bytes() >= limit, 'DML written to partial spool')
        if hybrid:
            before_bytes = sub.spool_bytes()
        writer.exec("ROLLBACK TO batch;")
        flush()
        if hybrid and require_reclaim:
            try:
                wait_for(lambda: sub.spool_bytes() < before_bytes - 1024 * 1024,
                         'file truncated before outer commit', seconds=wait_seconds)
            except RuntimeError:
                pass
            after_bytes = sub.spool_bytes()
        if hybrid:
            locker.exec("COMMIT;")
        if nested:
            writer.exec("RELEASE batch; SAVEPOINT batch; INSERT INTO ledger VALUES (8,80); RELEASE batch;")
        writer.exec("INSERT INTO ledger VALUES (10,20); COMMIT;")
        pub.sql("INSERT INTO barrier VALUES (1)")
        caught_up = False
        try:
            caught_up = bool(wait_for(lambda: sub.sql('SELECT 1 FROM barrier WHERE id=1'),
                                      'commit followed by replication barrier', seconds=wait_seconds))
        except RuntimeError:
            pass
        subscriber = sub.sql(ROWS)
        subscriber_gate = sub.sql('TABLE gate')
        log = sub.log_text()[log_start:]
        apply_errors = [
            match.group(1) for match in re.finditer(
                r'\b(?:ERROR|PANIC|FATAL):\s+(.*)$', log, re.MULTILINE)
        ]
        return dict(mode=mode, segments=segments, nested=nested, caught_up=caught_up, expected=pub.sql(ROWS),
                    subscriber=subscriber, subscriber_gate=subscriber_gate, apply_errors=apply_errors,
                    partial_spool='will serialize the remaining changes' in log,
                    bytes_before_abort=before_bytes, bytes_after_abort=after_bytes)
    finally:
        writer.close()
        locker.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bin_dir', type=Path)
    parser.add_argument('--segments', type=int, choices=(0, 1, 2), default=1)
    parser.add_argument('--mode', choices=('parallel', 'on', 'off'), default='parallel')
    parser.add_argument('--nested', action='store_true')
    parser.add_argument('--require-reclaim', action='store_true')
    parser.add_argument('--logs', type=Path)
    parser.add_argument('--wait-seconds', type=int, default=18)
    args = parser.parse_args()
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='pg-hybrid-') as directory:
        root = Path(directory)
        pub = Cluster(root, args.bin_dir, 'publisher', 56081)
        sub = Cluster(root, args.bin_dir, 'subscriber', 56082)
        try:
            pub.start()
            sub.start()
            result = exercise(pub, sub, args.mode, args.segments, args.require_reclaim,
                              args.wait_seconds, args.nested)
            reclaimed = (result['bytes_before_abort'] is not None and
                         result['bytes_after_abort'] is not None and
                         result['bytes_before_abort'] - result['bytes_after_abort'] >= 1024 * 1024)
            expected = '1|10\n8|80\n9|90\n10|20' if args.nested else '1|10\n10|20'
            result['pass'] = (result['caught_up'] and result['expected'] == expected
                              and result['subscriber'] == expected
                              and not result['subscriber_gate'] and not result['apply_errors']
                              and (not args.require_reclaim or (result['partial_spool'] and reclaimed)))
            print(json.dumps(result), flush=True)
            return 0 if result['pass'] else 1
        finally:
            for node in (sub, pub):
                try:
                    node.stop()
                finally:
                    if args.logs and node.log.exists():
                        args.logs.mkdir(parents=True, exist_ok=True)
                        (args.logs / node.log.name).write_bytes(node.log.read_bytes())


if __name__ == '__main__':
    raise SystemExit(main())
