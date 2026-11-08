# Concurrent UPDATE RETURNING OLD

This package contains the three completed repeat runs used in the Slonik article: Slonik oQ8, base Qwen 8bit, and GLM oQ4e. Earlier model attempts are excluded. The original model patches are unchanged.

Two transactions update one row under `READ COMMITTED`. A `BEFORE UPDATE` row trigger makes the second transaction wait for the first, then update the newer row from 17 to 18. The defective executor still returns `OLD.n = 7`. The expected pair is `17|18`, with 18 stored in the table. [Bug #19536](https://www.postgresql.org/message-id/19536-73ce5847e6c0e7b1%40postgresql.org) was public before Slonik's release; we do not know whether the models encountered its discussion or fix during training.

## Sources and artifacts

- Defective PostgreSQL revision: `abecdbc6af0192eb8fc017af5c7a3bb3d5da1ae3`.
- [Upstream fix](https://github.com/postgres/postgres/commit/4908225bebdc31c9b8f735ad1db3d08d9bc85148): `4908225bebdc31c9b8f735ad1db3d08d9bc85148`, the direct child of the defective revision.
- Exact task: [PROMPT.txt](PROMPT.txt). Historical model/agent parameters and their limits: [settings.json](settings.json).
- Original patches: [Slonik](patches/slonik.patch), [Qwen](patches/qwen.patch), [GLM](patches/glm.patch).
- [results.json](results.json) contains historical independent checks, patch hashes, time and corrected token totals. [usage.json](usage.json) contains numeric per-response counts that can be summed without exposing private traces or model payloads.
- [publication-checks.json](publication-checks.json) records the fresh Linux packaging check: baseline, upstream and Slonik focused checks, Slonik test sensitivity, and nested patch-apply checks for all three patches. The fixed builds' full suites were not rerun during packaging.

The first repeat supplied the completed Qwen patch. Fresh Slonik and GLM runs with persistent sessions supplied the other two. Those two runs finished without a continuation prompt. The same task and PostgreSQL base were used, but the inference settings differ. No model is selected by combining C code from different attempts.

## Reproduce the patch checks on Linux

Use a regular user, Python 3.11 or later, Git, Bubblewrap with user namespaces, a C compiler, GNU Make, Bison, Flex, pkg-config, and the development libraries for ICU, Readline and zlib. For example, Debian provides `build-essential bison flex pkg-config libicu-dev libreadline-dev zlib1g-dev python3 git bubblewrap`.

Fetch only the pinned fix and its parent into a new source repository. This step needs network access. The later build and test steps run offline in a Bubblewrap namespace.

```sh
git init postgres-source
git -C postgres-source fetch --depth=2 https://github.com/postgres/postgres.git \
    4908225bebdc31c9b8f735ad1db3d08d9bc85148

# Run from the slonik-llm-tests repository root.
bash returning-old/prepare.sh postgres-source ./returning-old-work
python3 -B returning-old/verify.py ./returning-old-work
```

`prepare.sh` exports the exact two upstream revisions, copies the helper scripts, and exports the two isolation tests changed by the upstream fix. It also saves the upstream commit diff under `evidence/upstream-fix.patch`. It does not need to check out a branch or change the source repository.

`verify.py` uses a fresh source tree and assertion-enabled build for every candidate. It first requires the baseline to reproduce the wrong `7|18` result and pass the four neighboring SQL cases, then checks the upstream fix and all three model patches. It runs:

1. Five two-session SQL cases: concurrent commit, rollback, no trigger, a predicate that no longer matches, and the `REPEATABLE READ` serialization error.
2. A replica-side `BEFORE UPDATE` trigger, a local-row cancellation followed by an update of a foreign partition, and the two isolation tests from the upstream fix.
3. The core and isolation suites. Each model adds one isolation test, giving 231 core and 121 isolation tests. The upstream fix extends existing tests, so its isolation count is 120.
4. Each model's isolation-test changes on the defective code, without the C fix. A failure counts as detecting this bug only when a changed test fails and its output contains `7|18` where the test expects `17|18`.

The SQL cases use disposable clusters, private Unix sockets and no TCP listener. The scripts never connect to an existing database. Builds and logs remain under the work directory. `verification.json` reports the expected baseline failure separately from failures of the fixed builds; the wrapper exits nonzero if the required checks do not match their expectations.

To check one patch, use a **new** prepared work directory and pass `--model slonik`, `--model qwen`, or `--model glm`. `--quick` skips the full suites on fixed builds; it retains the focused SQL, replication, FDW, upstream-isolation and model-test sensitivity checks. It does not substantiate a new claim that the skipped suites passed.

The publication wrapper uses two parallel build jobs instead of the six used in the historical validation. It also explicitly checks the stale value in the model test's failure output. These are packaging changes to the checker, not changes to the model patches or historical results.

## What the completed runs showed

| Model | Markov time | Responses | Commands | Input tokens | Output tokens |
|---|---:|---:|---:|---:|---:|
| Slonik oQ8 | 10:56 | 64 | 61 | 1,729,139 | 23,945 |
| Qwen 8bit | 24:46 | 106 | 102 | 1,660,956 | 30,362 |
| GLM oQ4e | 14:33 | 72 | 84 | 2,277,694 | 33,457 |

All three final patches passed the five scenarios, 231 core tests, 121 isolation tests, both upstream isolation tests, and the supplemental replication and FDW checks. Each model test detected the original stale value without its C fix. Successful tests establish these observed results, not correctness for every possible caller or workload.

Slonik copies the already-read row in shared trigger code and assumes that the caller's OLD slot exists. Qwen rereads the row after the trigger phase, guards the slot and TID, but does not reset `tmfd.traversed` before the triggers. GLM rereads in the local-table path and resets the flag afterward. Upstream resets the flag before the trigger phase. These code differences remain relevant to review despite the shared test outcomes.

## Model run and accounting limits

The historical runs used Markov, an internal coding agent. Its shell had no network access, a source snapshot without upstream history, a persistent build directory, and automatic approval for valid calls. The fixed source and independent checks were outside the model's workspace. The exact task and known settings are published here; reproducing model generation itself also requires that internal agent and provider integration. The patch checks above do not require either.

Slonik and GLM had 131,072-token context windows and 16,384-token response limits. Qwen had 32,768 and 8,192. Slonik requested thinking with a budget of 192; enforcement of that budget was not independently established. GLM used high reasoning, and Qwen used the server profile with thinking disabled. The immutable revisions of the serving artifacts and some effective server settings were not captured; see `settings.json` for the known request parameters and explicit unknowns.

Markov time includes tool commands and excludes model loading and independent validation. Input counts include cached prefixes and repeatedly submitted history. Output counts combine reasoning and other output. One short startup probe per model is excluded. Per-response durations in `usage.json` are not the time for the whole agent session.

The original Langfuse trace missed 18,409 output tokens from three long Qwen responses and 641 from its final response: 11,312 + 18,409 + 641 = 30,362. The three long calls took 718.74 seconds; the context reductions afterward suggest compaction. GLM's final 618 tokens were also absent from its trace. The totals published here use the completed oMLX responses and agree with the retained Markov ledgers for Slonik and GLM. No separate reasoning-token counter is available.

One task with different limits and reasoning settings cannot establish a stable model ranking or measure the effect of Slonik's additional training.
