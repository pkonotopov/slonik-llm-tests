# Author repairs to Qwen's TAP test

The original model patch remains unchanged in `../patches/qwen-131072.patch`.
The files here contain the **subsequent author repair**, not additional model output.

`036_stream_subxact_abort_reclaim.pl` is the exact test recovered from the preserved
validation workspace. The same bytes ran against Qwen's C patch and against the
synthetic defective build on 8 November 2026. No new repair was made while preparing
this publication package. `qwen-test-repair.patch` records the difference from the
test in the original model patch and can be applied after that patch:

```sh
git apply /path/to/slonik-llm-tests/replication/human-repairs/qwen-test-repair.patch
```

The authors made these changes:

- Created both `gate` and `ledger` on the subscriber.
- Disabled initial copying for the empty tables with `copy_data = false`, allowing
  the tables to become ready for parallel apply.
- Accepted whitespace after `DEBUG:` in the savepoint and reclamation log checks.
- Made the lock polling helper expect the `1` returned by its query.
- Added a payload column and a 20 MiB row to force the queue-to-file transition.
- Replaced `isnt` with `unlike` so the log check applies its regular expression.

The repaired test passed all four assertions on Qwen's C patch. On the defective
build, assertions 1, 3 and 4 failed; they detected incorrect rows and a stream
protocol error. These are preserved historical results, not new executions of the
test during publication. The patch application was checked again while packaging.
The test hashes and result summary are in [results.json](results.json).

This result must not be counted as an autonomous model-written test success.
The original test's setup and assertions were not sufficient to validate the fix.
