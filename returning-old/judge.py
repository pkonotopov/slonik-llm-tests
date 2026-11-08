#!/usr/bin/env python3
"""Check a candidate on a disposable PostgreSQL server via psql."""

import asyncio
import json
import sys

from repro import case


async def main(command):
    cases = [
        ('commit_with_trigger', {}, '00000', ['17|18'], ['18']),
        ('rollback_with_trigger', {'finish': 'ROLLBACK'}, '00000', ['7|8'], ['8']),
        ('commit_without_trigger', {'trigger': False}, '00000', ['17|18'], ['18']),
        ('predicate_rechecked', {'predicate': 'id = 1 AND n = 7'}, '00000', [], ['17']),
        ('repeatable_read', {'isolation': 'REPEATABLE READ'}, '40001', [], ['17']),
    ]
    outcomes = {}
    for name, options, status, rows, stored in cases:
        actual = await case(command, **options)
        expected = {'sqlstate': status, 'returning': rows, 'stored': stored}
        outcomes[name] = {'actual': actual, 'expected': expected, 'pass': actual == expected}
    print(json.dumps(outcomes, indent=2), flush=True)
    return all(outcome['pass'] for outcome in outcomes.values())


if __name__ == '__main__':
    sys.exit(0 if asyncio.run(main(sys.argv[1:] or ['psql'])) else 1)
