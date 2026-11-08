# Parallel replication and savepoint rollback

This is an intentionally introduced defect in PostgreSQL 18.6. A transaction spans
an apply worker's shared-memory queue and a temporary spool file. A broken disk
reclamation change drops a subtransaction's rollback message or damages the
stream-block boundaries. The subscriber can retain a rolled-back row, or restart
apply after a protocol error and eventually reach the right rows.

The fixture was constructed after the compared model artifacts were available.
That limits prior exposure to this particular defect; knowledge of similar code
and mechanisms remains possible. These runs do not estimate the effect of
Slonik's additional training.

## Evidence and patch order

- [revision.json](revision.json) pins the upstream commit, official source archive,
  archive checksum, fixture checksum, and exact prompt checksum.
- [fixture.patch](fixture.patch) introduces the synthetic defect into pristine
  PostgreSQL 18.6 at commit `724edf9bde9d356724ad384a2e196edc3c9f80f7`.
- [reference.patch](reference.patch) repairs that fixture. It is the authors'
  control implementation, not model output.
- [Slonik](patches/slonik.patch), [GLM](patches/glm.patch), and
  [Qwen with 131,072 context](patches/qwen-131072.patch) apply **after the fixture**.
  They preserve the original model source changes. Qwen's generated test log was
  excluded from the exported patch; its source and test changes were not repaired.
- [human-repairs](human-repairs/README.md) separately contains the exact subsequent
  author repair to Qwen's TAP test, with a diff against the original model test.
- [PROMPT.txt](PROMPT.txt) is the exact task. [settings.json](settings.json) records
  the retained agent/model settings and marks uncaptured values as unknown.
- [results.json](results.json) contains the historical measurements and checks.
  It keeps the failed first Qwen configuration separate from the successful C
  patch in the larger-context run.
- [publication-validation.json](publication-validation.json) records the separate
  packaging check: an isolated Linux build of Qwen's C patch plus the preserved
  author-repaired test passed the six probes and four TAP assertions. It also
  records patch-application and script checks. The full upstream suites were not
  rerun during packaging.

Apply one of the model patches or the reference patch to a fresh fixture. Do not
apply several alternative fixes on top of one another. The initial Qwen run
produced no patch, so there is no corresponding patch file.

## Reproduce the checks on Linux

The public checker needs Python 3.9 or later, Git, GNU make, a C compiler, the usual
PostgreSQL build dependencies, Perl, and the Perl `IPC::Run` module for TAP tests.
For a Debian-like system, the relevant packages include `build-essential`, `bison`,
`flex`, `libreadline-dev`, `zlib1g-dev`, `libicu-dev`, `pkg-config`, and
`libipc-run-perl`. Run as an ordinary user. The checks create disposable clusters
with private Unix sockets and no TCP listener. Use a short temporary path for
`TMPDIR` if your usual temporary directory has a long name.

From the repository root, fetch and verify the exact source archive:

```sh
curl -fLO https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2
echo '555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f  postgresql-18.6.tar.bz2' | sha256sum -c -
tar -xf postgresql-18.6.tar.bz2
```

The following builds a fresh copy and runs the six independent scenarios plus the
model's own TAP test, if there is one. `--full` adds the five upstream subscription
test files, core regressions, and isolation suite:

```sh
python3 replication/verify.py --source postgresql-18.6 \
  --work /tmp/repl-reference --candidate reference --full
python3 replication/verify.py --source postgresql-18.6 \
  --work /tmp/repl-glm --candidate glm --full
python3 replication/verify.py --source postgresql-18.6 \
  --work /tmp/repl-qwen-repaired --candidate qwen-repaired --full
```

`--work` must not already exist. Each command copies the source, applies the patch
chain, configures with `CFLAGS=-O0 --enable-cassert --enable-tap-tests`, builds and
installs locally, then writes `result.json` and logs beneath that work directory.
The supplied source remains unchanged. Use `--jobs 2` to reduce build parallelism.
The script uses the same SQL/log/disk probe as the historical experiment, but its
build wrapper is portable and does not require the internal sandbox or agent.

Other candidates are `upstream`, `fixture`, `slonik`, and `qwen` (the original
larger-context Qwen patch, with its unrepaired test). The initial small-context
Qwen run has no candidate. The checker exits nonzero if a check fails; that is an
expected observation for the defective fixture, Slonik's hybrid cases, and the
original Qwen TAP setup.

To check that a new test catches the original defect, apply only its TAP test to
the fixture without the model's C fix:

```sh
python3 replication/verify.py --source postgresql-18.6 \
  --work /tmp/repl-glm-tests-only --candidate glm --tests-only
python3 replication/verify.py --source postgresql-18.6 \
  --work /tmp/repl-qwen-tests-only --candidate qwen-repaired --tests-only
```

These two commands are expected to fail their TAP assertions. Read the failure
diff to distinguish detecting the target symptom from a setup failure. The
unrepaired Qwen test fails to create the subscriber tables, which is not evidence
that it detects the intended defect.

For an existing PostgreSQL installation, run the independent probe directly:

```sh
python3 replication/probe.py /path/to/install/bin --require-reclaim
python3 replication/probe.py /path/to/install/bin --segments 2 --require-reclaim
python3 replication/probe.py /path/to/install/bin --nested --require-reclaim
```

Omit `--require-reclaim` when testing unmodified upstream: early file reclamation
is the fixture's new requirement, not an upstream PostgreSQL feature. The remaining
scenarios use `--segments 0`, `--mode on`, and `--mode off`. For a nonstandard shared
library location, set `LD_LIBRARY_PATH` to the installation's `lib` directory.

The independent checks compare exact ordered rows and the locking table, require
a later barrier transaction to arrive, check the subscriber log for
`ERROR`/`FATAL`/`PANIC`, and, in the hybrid cases, require file space to be reclaimed
before the outer commit. Comparing only final table contents misses a restart
that temporarily interrupts apply.

## Historical results

| Run | Independent C checks | New model test |
|---|---|---|
| Slonik oQ8 | Three hybrid cases fail with `STREAM ABORT message without STREAM STOP`; neighboring modes and upstream suites pass | None |
| Qwen 32,768 context | No patch to validate | None |
| GLM oQ4e | Six scenarios, 58 upstream subscription assertions, 231 core regressions and 122 isolation tests pass | Seven assertions pass; test-only run catches the extra row, but its log assertion is ineffective |
| Qwen 131,072 context | Six scenarios and the same upstream suites pass | Original test has setup/validation faults; author-repaired test passes 4/4 and fails 3/4 on the defect |

The original Qwen TAP did not pass. Its author repair is a separate contribution,
not an autonomous model result. The preserved repair and results are linked above.

GLM's test uses `^ERROR:` to search a log whose lines begin with a timestamp and
PID. [check-log-assertion.py](check-log-assertion.py) demonstrates this blind spot;
the independent probe searches errors correctly. GLM's passing independent checks
are unaffected by this flaw in its own test.

The authors preferred Qwen's C patch because it preserves stream boundaries and
has an explicit rule for which DML records can be removed. GLM does not reset the
truncation point for DML with a different `subxid`. A child subtransaction can also
belong to the current rollback, so this observation alone does not prove loss of
data that should survive. No such loss was observed in the recorded checks.

| Run | Agent time | Model requests | Shell calls | Input tokens | Output tokens |
|---|---:|---:|---:|---:|---:|
| Slonik oQ8 | 54:13 | 144 | 139 | 7,871,605 | 138,862 |
| Qwen 32,768 | 1:12:40 | 91 | 86 | 1,025,622 | 112,717 |
| GLM oQ4e | 41:52 | 82 | 92 | 3,090,114 | 97,281 |
| Qwen 131,072 | 44:18 | 62 | 64 | 3,310,823 | 65,113 |

Agent time includes commands and continuations, while model loading and independent
validation are separate. Input includes cached and repeatedly supplied context.
Totals use completed oMLX requests reconciled with the agent ledger, excluding one
startup probe per run. Slonik's Langfuse trace omitted 104,150 input and 381 output
tokens from one compaction; the published totals include them.

All three models had thinking enabled for this task, but their request profiles
differed. Qwen's first run used 32,768 context and an 8,192 output limit; the repeat
used 131,072 and 16,384, matching the other two. Both limits changed together.
The repeat completed without compaction; this single repeat does not isolate the
effect of either limit from run-to-run variation.

The internal Markov agent is not included. The exact task, visible original
[agent-helper.sh](agent-helper.sh), and retained settings document the inference
setup; its `/work`, `/build`, and `/bench` paths refer to disposable sandbox mounts.
The public verifier reproduces patch evaluation without calling any model. The
model could read the seeded source and the focused `/bench` helper, including
`probe.py`. Independent validation reused that probe with additional scenario
arguments and ran the upstream suites in separate builds. The fixture generator,
reference repair, and separate validation workspaces were outside the model's
workspace; the visible reproduction itself was not a hidden test.
