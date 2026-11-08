# PostgreSQL partition pruning experiment

This package records the synthetic pruning case used to compare Slonik's three
MLX quantizations and GLM. It adds GLM to the three Slonik patches already in this
repository. It contains the original model patches, prompts, archived checks and
a portable reproduction wrapper. It does not rerun the models or reproduce the
internal Markov service.

The base is PostgreSQL 18.6 at commit
[`63d9e26c27b9965a78f0d59512a80d84935a7c4b`](https://github.com/postgres/postgres/commit/63d9e26c27b9965a78f0d59512a80d84935a7c4b).
Apply [fixture.patch](../patches/fixture.patch) first, then exactly one candidate.
The fixture incorrectly skips a UNION pruning result when its bound offsets are
empty, losing the separate flags for DEFAULT or NULL partitions.

| Model | Original candidate | Agent time, including attempts | Rows and plans | Core tests | New test catches defect |
| --- | --- | ---: | ---: | ---: | --- |
| Slonik oQ8 | [oq8.patch](../patches/oq8.patch) | 701.38 s (11:42) | 15/15 | 231/231 | Yes |
| Slonik oQ6e | [oq6e.patch](../patches/oq6e.patch) | 488.02 s (8:08) | 15/15 | 231/231 | Yes |
| Slonik oQ4e | [oq4e.patch](../patches/oq4e.patch) | 1143.85 s (19:04) | 15/15 | 231/231 | Yes |
| GLM-5.3-Flash-oQ4e-mtp | [glm.patch](../patches/glm.patch) | 193.92 s (3:14) | 15/15 | 231/231 | Yes |

All times and outcomes in this table are from the 7 November 2026 experiment.
They include shell commands, but exclude model loading and independent validation.
The [results](results.json) include per-attempt times, exact ordered rows and
partition names for all 15 checks, regression summaries, sensitivity results and
patch SHA-256 hashes. The patches are byte-for-byte copies of the accepted final
experiment artifacts. GLM's C change removes exactly the injected four lines;
its resulting `partprune.c` matched the clean upstream file byte for byte.

## Prompts and recorded settings

- [PROMPT.txt](PROMPT.txt): the initial task, also used for GLM.
- [AGENT-INSTRUCTIONS.txt](AGENT-INSTRUCTIONS.txt): the Slonik runner's additional
  instructions; the record does not establish identical additional instructions
  for GLM.
- [FOLLOWUP.txt](FOLLOWUP.txt): oQ8's next session, with its earlier C change.
- [RETRY-oQ4e.txt](RETRY-oQ4e.txt): oQ4e's fresh attempt from the defective source.
- [settings.json](settings.json): historically evidenced settings and missing fields.

oQ6e completed the C patch and test in one attempt. oQ8's first attempt wrote the
C fix and stopped at an approval request while adding the test. Its next session
used automatic approval for the isolated shell. oQ4e reached an output limit of
16,384 tokens before writing a patch. Its next attempt used fresh defective
sources, automatic shell approval and an instruction to use smaller steps. GLM
used `reasoning_effort=high` and automatic isolated-shell approval from the start.

The Slonik runner copied the then-configured oQ8 provider entry for all three
quantizations, changing only the model name. That temporary provider snapshot was
not retained. Context, sampling and thinking parameters are therefore marked
unknown where the surviving records do not establish them. The `-mtp` model name
does not establish whether Lightning MTP was enabled for this particular task.
Settings from other tasks or today's server defaults were not substituted.
The original SDK `usage` fields count the last response, not complete sessions;
they are deliberately not presented as total token usage.

These are results for particular attempts and configurations. Different prompts,
approval policies and numbers of attempts prevent a controlled ranking of the
models or quantizations. The two later C tasks used only Slonik oQ8.

## Reproduce the patch checks

Use Linux, Python 3, Git, tar, a C compiler and PostgreSQL's normal build
dependencies, including GNU make, Bison, Flex, ICU and readline development files.
Run as an ordinary user; `initdb` refuses root. No model, Markov installation,
network access or external PostgreSQL server is needed after obtaining the source.
The verifier starts temporary clusters on local Unix sockets with TCP disabled.

Clone this repository and the PostgreSQL source, then run from this repository:

```sh
git clone https://github.com/postgres/postgres.git /tmp/postgres-pruning-source
python3 pruning/verify.py \
  --source /tmp/postgres-pruning-source \
  --work /tmp/pruning-glm \
  --candidate glm --jobs 2
```

`--source` is a Git repository containing the pinned commit. Its working tree is
not modified. `--work` must not exist. The wrapper exports the pinned source,
applies the fixture and candidate, builds with `CFLAGS=-O0 --enable-cassert`,
installs under `--work`, runs the original [15-check oracle](../verify.py), then
runs `make check`. Logs, source and `result.json` remain under `--work`.
Use a separate output directory for each candidate (`oq8`, `oq6e`, `oq4e`, `glm`).

For the sensitivity check, apply only the candidate's SQL and expected-output
hunks to the defective C build:

```sh
python3 pruning/verify.py \
  --source /tmp/postgres-pruning-source \
  --work /tmp/pruning-glm-tests-only \
  --candidate glm --tests-only --jobs 2
```

This command is successful only when the 15-check oracle retains the expected
eight failures and the regression suite fails on expected-output lines introduced
by GLM's new test. A generic build failure is not accepted as sensitivity. Inspect
`result.json`, `regression.log` and `build/src/test/regress/regression.diffs` to
confirm that the missing DEFAULT scan explains the test difference. The same
command works for each Slonik candidate.

Two controls are available with `--candidate clean` and `--candidate defect`.
Clean upstream should pass all 15 checks and 231 core tests. The defective control
should fail eight query/plan checks; its core-suite result is reported separately.
`--prepare-only` checks source export and patch application without claiming that
the build or tests ran.

For an existing installation, the original oracle can also be run directly:

```sh
python3 verify.py /absolute/path/to/installation/bin
```

## Scope and provenance

The agent saw the reproducer, expected rows and expected partitions, a single
baseline commit, and an offline shell. The clean source, injected diff and
independent checks were kept outside its workspace. Independent builds and
sensitivity checks were recorded for each final patch. The public wrapper adapts
that procedure to explicit local paths; it does not replay the historical agent
sessions. The archived outcomes remain distinct from new local checks.

The [publication recheck](publication-checks.json) on 8 November 2026 checked
application of all four full patches and their test-only hunks against saved
clean source files. It reran the unchanged 15-case oracle on the saved clean,
defective and four candidate installations, with the expected results, and
checked the sensitivity parser against the archived regression differences.
That part of the recheck reused the archived builds. A separate fresh run
fetched the exact upstream commit and ran the public wrapper with
`--candidate glm --jobs 2`. Patch application, configure, build and installation
succeeded; all 15 row/plan checks and all 231 core tests passed. The report records
the wrapper, oracle, fixture and candidate hashes. The other candidates and
test-only sensitivity were not rebuilt during publication. No model inference
was run for either recheck.

The PostgreSQL [copyright and license notice](../LICENSE) applies to the upstream
code represented in these patches. No credentials, private service addresses or
session traces are required to reproduce the patch checks.
