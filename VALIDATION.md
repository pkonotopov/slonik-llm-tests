# Publication checks, 8 November 2026

These checks validate the public evidence package and its reproduction commands. They are separate from the original model experiments. No new model inference was run, and the historical time and token measurements were not replaced.

## Fresh builds

The following public command paths were exercised in new isolated Linux work directories:

| Case | Scope of the new check | Observed result | Detailed record |
|---|---|---|---|
| Pruning | Exact pinned source, fixture and original GLM patch; public wrapper with two build jobs | Build and installation succeeded; 15/15 focused row/plan checks and 231/231 core regressions passed | [Pruning publication checks](pruning/publication-checks.json) |
| `RETURNING OLD` | Public preparation and `--quick --model slonik`: separate baseline, upstream and Slonik builds, plus Slonik's test on defective C | Baseline reproduced `7\|18`; upstream and Slonik passed five SQL cases, the replica-trigger and FDW checks, and both upstream isolation tests. Slonik's test alone detected the stale OLD value. Wrapper exited successfully. | [RETURNING OLD publication checks](returning-old/publication-checks.json) |
| Replication | Original Qwen C patch plus the separately preserved author repair to its TAP test | Build succeeded; all six row/log/disk scenarios and 4/4 TAP assertions passed | [Replication publication checks](replication/publication-validation.json) |

The new `RETURNING OLD` run skipped full core/isolation suites on fixed builds. Its test-only check ran against defective C and required the intended stale value, not merely a nonzero exit. Qwen and GLM were not rebuilt for that packaging check. Replication's full upstream suites were not rerun during packaging. Their historical outcomes remain in each case's `results.json`.

Review also found two wrapper path issues: inherited Git roots could filter patch paths, and replication needed to reject a work directory inside its source. The final guards were checked separately. For RETURNING OLD, all three full and test-only patches were applied in nested repositories after the Git-root fix. These guards did not change model patches or test logic; the detailed records distinguish them from the completed fresh builds.

## Other checks

- Original model patches, synthetic fixtures and the replication reference repair were compared with the retained source artifacts. Human repairs remain separate. Patch checksums are recorded with the case results.
- Every pruning candidate and its test-only hunks passed clean-application checks. The unchanged 15-case oracle was also rerun on the saved clean, defective and four candidate installations: clean/candidates passed, and the defect produced the expected eight failures. The sensitivity parser was checked against the four archived regression diffs; those sensitivity builds were not repeated during packaging.
- Replication patch chains were checked against the pinned official source archive. Applying the human repair reproduces the exact retained tested TAP file. The standalone log-assertion demonstration exposes GLM's timestamp-prefix blind spot.
- Python, shell and JSON files were checked for syntax where applicable. Numeric per-response token totals for RETURNING OLD were reconciled with its published results.
- Public text was checked for credentials, private service addresses, personal filesystem paths and raw session/trace identifiers. Those operational details are excluded.

## Reading the evidence

The archived results document the original checks; the records linked above document the additional publication checks. Neither is a claim that all possible PostgreSQL behavior is covered. Test quality, C-code behavior and agent-generation settings remain separate questions.

The patch checks can run without the internal Markov agent. Repeating the original inference trajectory would also require its implementation and uncaptured runtime details. Unknown historical parameters are marked explicitly in the settings files. See [METHOD.md](METHOD.md) for the comparison limits.

[SHA256SUMS](SHA256SUMS) lists every public file except itself. From the repository root on Linux, verify the checked-out files with `sha256sum -c SHA256SUMS`.
