#!/usr/bin/env python3
"""Apply a candidate to a fresh snapshot and validate it in an offline build."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from sandbox import sandbox


def validate(root, label, source, patch, suites, replication, upstream_isolation, fdw):
    evidence = root / 'evidence'
    stage = root / 'judge' / label
    work, build = stage / 'source', stage / 'build'
    work.mkdir(parents=True)
    build.mkdir()
    result = {'label': label, 'independent_checkout': True, 'steps': {}}
    started = time.monotonic()

    def run(name, command, timeout):
        with (evidence / f'{label}.{name}.log').open('w') as log:
            try:
                proc = subprocess.run(sandbox(work, build, root/'judge-helpers', command),
                                      stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                status = proc.returncode
            except subprocess.TimeoutExpired:
                status = 'timeout'
        result['steps'][name] = status
        return status

    try:
        subprocess.run(['tar', '-xf', str(source), '-C', str(work)], check=True)
        # Keep git apply rooted here even when the work directory is inside
        # the publication repository (rather than inheriting its .git).
        subprocess.run(['git', 'init', '--quiet', '--template=', str(work)], check=True)
        if patch is not None:
            if not patch.is_file() or not patch.stat().st_size:
                raise ValueError('No patch produced')
            changes = subprocess.check_output(['git', 'apply', '--numstat', str(patch)], cwd=work, text=True)
            for line in changes.splitlines():
                added, removed, path = line.split('\t', 2)
                if not (added.isdigit() and removed.isdigit() and re.fullmatch(r'src/[a-zA-Z0-9_/.-]+', path)):
                    raise ValueError(f'Unexpected patch entry: {path}')
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=work, check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=work, check=True)
        if run('build', 'cd /build && CFLAGS=-O0 /work/configure --enable-cassert && make -j2', 950) != 0:
            return result
        run('scenarios', 'bash /bench/run-pg.sh judge', 210)
        content = (evidence / f'{label}.scenarios.log').read_text()
        try:
            result['scenarios'] = json.loads(content[content.index('{'):])
        except (ValueError, json.JSONDecodeError):
            pass
        if replication:
            run('replication', 'bash /bench/run-pg.sh replication', 100)
        if upstream_isolation:
            run('upstream_isolation', 'bash /bench/run-pg.sh upstream-isolation', 550)
        if fdw:
            run('fdw', 'bash /bench/check-fdw.sh', 200)
        if suites:
            run('regression', 'make -C /build/src/test/regress -j2 check', 550)
            run('isolation', 'make -C /build/src/test/isolation -j2 check', 550)
            for kind in ('regression', 'isolation'):
                lines = (evidence / f'{label}.{kind}.log').read_text().splitlines()
                result[f'{kind}_tests'] = sum(bool(re.match(r'^ok\s+\d+\b', line)) for line in lines)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        result['seconds'] = round(time.monotonic() - started, 2)
        (evidence / f'{label}.judge.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'scenarios'}), flush=True)
    return result


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('label')
    p.add_argument('--source', default='before.tar')
    p.add_argument('--patch', type=Path)
    p.add_argument('--suites', action='store_true')
    p.add_argument('--replication', action='store_true', help='Also check a replica-side BEFORE UPDATE trigger')
    p.add_argument('--upstream-isolation', action='store_true', help='Also run the two isolation tests changed by the official fix')
    p.add_argument('--fdw', action='store_true', help='Also check a canceled local update followed by a foreign partition')
    args = p.parse_args()
    root = args.root.resolve()
    validate(root, args.label, root / args.source, args.patch, args.suites, args.replication, args.upstream_isolation, args.fdw)
