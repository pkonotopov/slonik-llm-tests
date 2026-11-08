#!/usr/bin/env python3
"""Apply the candidate's isolation tests alone to the known-defective build."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from sandbox import sandbox


def run(root, label):
    evidence = root/'evidence'
    patch = evidence/f'{label}.patch'
    result = {'label': label, 'detected': None}
    try:
        diff = patch.read_text()
        paths = set(re.findall(r'^\+\+\+ b/src/test/isolation/specs/([\w-]+)\.spec$', diff, re.M))
        expected = set(re.findall(r'^\+\+\+ b/src/test/isolation/expected/([\w-]+)\.out$', diff, re.M))
        paired = paths & expected
        result['changed_specs'] = sorted(paths)
        result['paired_specs'] = sorted(paired)
        if not paired:
            result['reason'] = 'The patch has no isolation spec with corresponding expected output.'
            return
        stage = root/'judge'/f'{label}-test-only'
        work, build = stage/'source', stage/'build'
        work.mkdir(parents=True)
        shutil.copytree(root/'judge/before/build', build, symlinks=True)
        subprocess.run(['tar', '-xf', str(root/'before.tar'), '-C', str(work)], check=True)
        subprocess.run(['git', 'init', '--quiet', '--template=', str(work)], check=True)
        subprocess.run(['git', 'apply', '--whitespace=nowarn', '--include=src/test/isolation/**', str(patch)],
                       cwd=work, check=True)
        log = evidence/f'{label}.test-only.log'
        with log.open('w') as out:
            proc = subprocess.run(sandbox(work, build, root/'judge-helpers', 'make -C /build/src/test/isolation -j2 check'),
                                  stdout=out, stderr=subprocess.STDOUT, timeout=550)
        failures = re.findall(r'^not ok\s+\d+\s+(?:[-+]\s+)?([\w-]+)', log.read_text(), re.M)
        stale_value = False
        for name in paired & set(failures):
            expected_file = work / 'src/test/isolation/expected' / f'{name}.out'
            actual_file = build / 'src/test/isolation/output_iso/results' / f'{name}.out'
            if actual_file.is_file():
                stale_value |= bool(
                    re.search(r'^\s*17\s*\|\s*18\s*$', expected_file.read_text(), re.M)
                    and re.search(r'^\s*7\s*\|\s*18\s*$', actual_file.read_text(), re.M)
                )
        result.update(exit_code=proc.returncode, failing_tests=failures,
                      stale_value_observed=stale_value,
                      detected=bool(proc.returncode and paired & set(failures) and stale_value))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        (evidence/f'{label}.test-only.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('label', choices=['slonik', 'qwen', 'glm'])
    args = p.parse_args()
    run(args.root.resolve(), args.label)
