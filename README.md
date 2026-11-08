# PostgreSQL patch experiments with Slonik, Qwen and GLM

Source revisions, prompts, model patches and independent checks for the Slonik 27B MLX experiments of 7–8 November 2026. Each case includes the settings preserved from its runs and recorded results. The patches are experimental candidates for review, including unsuccessful candidates.

| Case | Models | Recorded outcome | Materials |
|---|---|---|---|
| Partition pruning, synthetic defect | Slonik oQ8, oQ6e, oQ4e; GLM oQ4e | All four final patches passed 15 focused checks and 231 core regression tests. Each new test caught the defect without the C fix. Attempts and approval settings differed. | [Instructions](pruning/README.md) · [Settings](pruning/settings.json) · [Results](pruning/results.json) |
| `UPDATE … RETURNING OLD`, public bug | Slonik oQ8, Qwen 8bit, GLM oQ4e | The three completed repeat runs passed the shared checks. Only the final patches used in the article are included. | [Instructions](returning-old/README.md) · [Settings](returning-old/settings.json) · [Results](returning-old/results.json) |
| Parallel replication rollback, synthetic defect | Slonik oQ8, Qwen 8bit, GLM oQ4e; additional Qwen run with larger limits | Slonik left protocol errors; initial Qwen produced no patch. GLM and the later Qwen C patches passed the independent scenarios. Qwen's test needed human repair; GLM's own log assertion has a known limitation. | [Instructions](replication/README.md) · [Settings](replication/settings.json) · [Results](replication/results.json) |

## Reproduce the checks

Follow the case instructions to prepare pinned PostgreSQL sources, apply one candidate, and run focused checks. Each package also describes full-suite and test-sensitivity runs. Use a separate source/build/work directory for each candidate and run PostgreSQL as a non-root user. The scripts create disposable clusters; dependencies are listed per case.

Patch validation does not require Markov, oMLX, model weights or a private service. Repeating the original model trajectory is a separate task: inference used Markov, an internal Postgres Professional coding agent. Its implementation and raw sessions are not included. The exact prompts and recovered settings describe the experiment and support new runs with another agent; identical output is not promised.

Historical measurements are recorded separately from the release checks in [VALIDATION.md](VALIDATION.md). Missing settings are explicitly unknown; current server defaults are not substituted for historical values.

## Read the evidence

- Model patches are separate from injected defects, reference repairs and human test repairs.
- A sensitivity run adds a candidate's test to the defective C build. Its expected failure must show the intended symptom, rather than a setup or compilation error.
- Passing a suite establishes behavior within those checks, not correctness of every code path or readiness to merge.
- Model time includes agent commands. Loading and independent validation are separate. Input includes cached prefixes and repeated context; output does not split out reasoning tokens.
- Different limits, reasoning settings and attempts prevent a simple model ranking or an estimate of the effect of fine-tuning.

[Measurement and provenance notes](METHOD.md) describe the release boundaries. [SHA256SUMS](SHA256SUMS) records file checksums.

The original pruning files remain at their existing paths: [fixture](patches/fixture.patch), [oQ8](patches/oq8.patch), [oQ6e](patches/oq6e.patch), [oQ4e](patches/oq4e.patch), and [verifier](verify.py). The new [GLM pruning patch](patches/glm.patch) applies to the same fixture.

[Slonik model and training paper](https://huggingface.co/dglhf/Slonik) · [Speed and SQL-queue measurements](https://huggingface.co/kakoka/Slonik-27B-oQ8-mtp/blob/main/BENCHMARK.md)

The [PostgreSQL copyright and license notice](LICENSE) accompanies the upstream code in these patches.
