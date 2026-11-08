#!/usr/bin/env python3
"""Rebuild and verify the published returning-OLD patches without Markov."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

from validate import validate


def baseline_reproduced(result):
    scenarios = result.get('scenarios', {})
    target = scenarios.get('commit_with_trigger', {})
    expected_stale = {'sqlstate': '00000', 'returning': ['7|18'], 'stored': ['18']}
    return (
        result.get('steps') == {'build': 0, 'scenarios': 1}
        and len(scenarios) == 5
        and target.get('actual') == expected_stale
        and all(s['pass'] for name, s in scenarios.items() if name != 'commit_with_trigger')
    )


def fixed_passed(result, full, isolation_count):
    wanted = {'build', 'scenarios', 'replication', 'upstream_isolation', 'fdw'}
    if full:
        wanted |= {'regression', 'isolation'}
    steps = result.get('steps', {})
    good = set(steps) == wanted and all(value == 0 for value in steps.values())
    good = good and len(result.get('scenarios', {})) == 5
    good = good and all(s['pass'] for s in result.get('scenarios', {}).values())
    if full:
        good = good and result.get('regression_tests') == 231
        good = good and result.get('isolation_tests') == isolation_count
    return good and 'error' not in result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='Fresh directory created by prepare.sh')
    parser.add_argument('--model', choices=['all', 'slonik', 'qwen', 'glm'], default='all')
    parser.add_argument('--quick', action='store_true',
                        help='Skip full core/isolation suites on fixed builds; retain focused checks and test sensitivity')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('Use Linux as a regular user (PostgreSQL initdb cannot run as root)')
    root = args.work.resolve()
    package = Path(__file__).resolve().parent
    for entry in ('before.tar', 'fixed.tar', 'judge-helpers', 'evidence'):
        if not (root / entry).exists():
            parser.error(f'Missing {entry}; run prepare.sh first')
    if (root / 'judge').exists():
        parser.error('The work directory already contains judge output; prepare a new directory')

    spec = importlib.util.spec_from_file_location('test_sensitivity', package / 'test-sensitivity.py')
    sensitivity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sensitivity)
    report = {'full_suites': not args.quick, 'baseline_reproduced': False,
              'upstream_passed': False, 'models': {}}
    baseline = validate(root, 'before', root / 'before.tar', None, False, False, False, False)
    report['baseline_reproduced'] = baseline_reproduced(baseline)
    if report['baseline_reproduced']:
        upstream = validate(root, 'upstream', root / 'fixed.tar', None,
                            not args.quick, True, True, True)
        report['upstream_passed'] = fixed_passed(upstream, not args.quick, 120)
        labels = ('slonik', 'qwen', 'glm') if args.model == 'all' else (args.model,)
        for label in labels:
            patch = package / 'patches' / f'{label}.patch'
            shutil.copyfile(patch, root / 'evidence' / f'{label}.patch')
            candidate = validate(root, label, root / 'before.tar', patch,
                                 not args.quick, True, True, True)
            sensitivity.run(root, label)
            test_only = json.loads((root / 'evidence' / f'{label}.test-only.json').read_text())
            report['models'][label] = {
                'candidate_passed': fixed_passed(candidate, not args.quick, 121),
                'test_detected_original_bug': test_only.get('detected') is True,
                'stale_value_observed': test_only.get('stale_value_observed') is True,
            }
    report['pass'] = (
        report['baseline_reproduced'] and report['upstream_passed']
        and bool(report['models'])
        and all(all(item.values()) for item in report['models'].values())
    )
    (root / 'evidence' / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
