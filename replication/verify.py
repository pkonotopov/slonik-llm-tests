#!/usr/bin/env python3
"""Build one replication candidate and run independent checks on disposable clusters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
CANDIDATES = ('upstream', 'fixture', 'reference', 'slonik', 'glm', 'qwen', 'qwen-repaired')
SUBSCRIPTION_TESTS = ('t/015_stream.pl', 't/016_stream_subxact.pl',
                      't/018_stream_subxact_abort.pl',
                      't/019_stream_subxact_ddl_abort.pl', 't/023_twophase_stream.pl')
MODEL_TESTS = {
    'glm': 't/036_stream_partial_serialize_reclaim.pl',
    'qwen': 't/036_stream_subxact_abort_reclaim.pl',
    'qwen-repaired': 't/036_stream_subxact_abort_reclaim.pl',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path,
                        help='Unmodified PostgreSQL 18.6 source from the pinned archive')
    parser.add_argument('--work', required=True, type=Path,
                        help='New directory for copied source, build, install, and logs')
    parser.add_argument('--candidate', required=True, choices=CANDIDATES)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--full', action='store_true',
                        help='Also run the five upstream subscription files, core, and isolation suites')
    parser.add_argument('--tests-only', action='store_true',
                        help='Apply only candidate TAP test(s) to the defective fixture; failure is expected')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as an ordinary user; initdb does not run as root.')
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.tests_only and args.candidate not in MODEL_TESTS:
        parser.error('--tests-only needs glm, qwen, or qwen-repaired')
    original, work = args.source.resolve(), args.work.resolve()
    if work == original or original in work.parents:
        parser.error('--work must be outside --source')
    if work.exists():
        parser.error('--work must not exist; each candidate needs a fresh build')
    revision = json.loads((HERE / 'revision.json').read_text())
    worker = original / 'src/backend/replication/logical/worker.c'
    if not worker.is_file() or digest(worker) != revision['upstream_worker_sha256']:
        parser.error('Source worker.c does not match the pinned, unmodified PostgreSQL 18.6 source')
    if not (original / 'configure').is_file():
        parser.error('Source archive is missing configure')
    os.umask(0o077)
    work.mkdir(parents=True)
    source, build, install, logs = (work / name for name in ('source', 'build', 'install', 'logs'))
    shutil.copytree(original, source, symlinks=True, ignore=shutil.ignore_patterns('.git'))
    build.mkdir()
    logs.mkdir()
    result = {'candidate': args.candidate, 'tests_only': args.tests_only, 'full': args.full,
              'upstream_commit': revision['upstream_commit'], 'steps': {}, 'probes': {}}
    env = os.environ | {'LC_ALL': 'C', 'CFLAGS': '-O0'}
    env['PATH'] = str(install / 'bin') + os.pathsep + env.get('PATH', '')
    env['LD_LIBRARY_PATH'] = str(install / 'lib') + (
        os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    started = time.monotonic()

    def run(name, argv, cwd=build, timeout=1800):
        with (logs / (name + '.log')).open('w') as log:
            try:
                status = subprocess.run([str(a) for a in argv], cwd=cwd, env=env,
                                        stdout=log, stderr=subprocess.STDOUT,
                                        timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                status = 'timeout'
        result['steps'][name] = status
        (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(f'{name}: {status}', flush=True)
        return status == 0

    def apply(name, path, tests_only=False):
        command = ['git', 'apply']
        if tests_only:
            command.append('--include=src/test/subscription/t/*.pl')
        command.append(str(path))
        if not run(name, command, cwd=source):
            raise RuntimeError(f'Patch application failed: {name}')

    try:
        if not run('initialize-source', ['git', 'init', '--quiet', '--template='], cwd=source):
            return 1
        if args.candidate != 'upstream':
            apply('apply-fixture', HERE / 'fixture.patch')
        if args.candidate == 'reference':
            apply('apply-reference', HERE / 'reference.patch')
        elif args.candidate in ('slonik', 'glm', 'qwen', 'qwen-repaired'):
            patch_name = 'qwen-131072' if args.candidate.startswith('qwen') else args.candidate
            patch = HERE / 'patches' / (patch_name + '.patch')
            result['model_patch_sha256'] = digest(patch)
            apply('apply-model', patch, tests_only=args.tests_only)
            if args.candidate == 'qwen-repaired':
                apply('apply-human-test-repair', HERE / 'human-repairs/qwen-test-repair.patch')
        build_steps = [
            ('configure', [source / 'configure', '--enable-cassert', '--enable-tap-tests',
                           '--prefix=' + str(install)]),
            ('build', ['make', '-j' + str(args.jobs)]),
            ('install', ['make', '-j' + str(args.jobs), 'install']),
        ]
        for name, command in build_steps:
            if not run(name, command):
                return 1
        if not args.tests_only:
            cases = {
                'hybrid-one': ['--segments', '1'],
                'hybrid-two': ['--segments', '2'],
                'hybrid-nested': ['--nested'],
                'queue-only': ['--segments', '0'],
                'serial-file': ['--mode', 'on'],
                'nonstreamed': ['--mode', 'off'],
            }
            for name, options in cases.items():
                if name.startswith('hybrid-') and args.candidate != 'upstream':
                    options += ['--require-reclaim']
                run(name, [sys.executable, '-B', HERE / 'probe.py', install / 'bin',
                           '--logs', logs / name, *options], timeout=300)
                for line in (logs / (name + '.log')).read_text().splitlines():
                    if line.startswith('{'):
                        result['probes'][name] = json.loads(line)
        if args.candidate in MODEL_TESTS:
            run('candidate-tests', ['make', '-C', build / 'src/test/subscription', 'check',
                                   'PROVE_TESTS=' + MODEL_TESTS[args.candidate]], timeout=600)
        if args.full:
            run('upstream-subscription', ['make', '-C', build / 'src/test/subscription', 'check',
                                         'PROVE_TESTS=' + ' '.join(SUBSCRIPTION_TESTS)], timeout=900)
            run('regression', ['make', '-C', build / 'src/test/regress',
                               '-j' + str(args.jobs), 'check'], timeout=900)
            run('isolation', ['make', '-C', build / 'src/test/isolation',
                              '-j' + str(args.jobs), 'check'], timeout=900)
        return 0 if all(status == 0 for status in result['steps'].values()) else 1
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result['error'] = str(exc)
        return 1
    finally:
        result['seconds'] = round(time.monotonic() - started, 2)
        (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
