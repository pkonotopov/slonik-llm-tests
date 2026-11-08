# Measurement and provenance

## Included runs

This release supports the three C-code case studies in the Slonik 27B MLX article. The speed and SQL-queue measurements remain in the separately linked Hugging Face benchmark. No new model inference runs were made for this release.

Pruning includes the final Slonik oQ8/oQ6e/oQ4e patches and the GLM patch. `RETURNING OLD` includes only the three completed runs selected for the article's repeat-series comparison. Earlier attempts are excluded. Replication preserves the initial Slonik and GLM patches, records the initial Qwen attempt without a patch, and includes the separate Qwen run with larger context and output limits.

## Source and patch identity

Each case pins its PostgreSQL baseline. The synthetic defects are separate patches. Model patches apply to the defective tree. `RETURNING OLD` uses a real pre-fix revision and identifies the accepted upstream fix.

Candidate patch bytes are preserved from the archived exports. Human repairs to Qwen's replication test are separate from its original patch. The reference replication repair is an experiment control, not a model result. Generated run logs are excluded from source patches.

The Slonik quantizations derive from `dglhf/Slonik`, directory `27B/`, at BF16 source revision `321d879c39a809057f324a8133c9484e4c192c06`. This is the source checkpoint, not an immutable hash of every deployed quantized file. Case settings describe recoverable model identities and missing provenance; a model name alone is not a complete artifact fingerprint.

## Execution and settings

Inference used MLX through oMLX on Apple Silicon. Markov provided the coding-agent loop. Model workspaces had PostgreSQL sources and build tools without external network access. The visible reproduction helper and its checks were available to the model. Independent validation used separate builds and additional scenarios; reference repairs and validation workspaces were not exposed to the model.

Public validation entry points use local paths and do not contact the original inference or telemetry services. They preserve SQL scenarios and checking semantics while replacing private orchestration paths with explicit arguments. Their release checks are recorded in `VALIDATION.md`.

The internal agent is not redistributed here. For a new model experiment, start from the defective source and exact prompt, make the prompt's helper available, and keep archived candidate patches, reference repairs and judge-only material out of the model workspace. Changing the agent or its tools creates a new experimental configuration.

Per-case settings distinguish requested parameters, saved settings and unknown fields. A requested thinking budget does not prove server enforcement. Current defaults do not establish what an old run used.

Markov elapsed time includes model calls, commands and continuations where reported. It excludes loading and independent validation. Compilation, context handling and retries contribute to these individual observations.

## Token accounting

Whole-task counts exclude a short startup probe where recorded. Input includes cached prefixes and context sent again. Output is the endpoint's combined count; there is no separate reasoning-token total.

For the completed `RETURNING OLD` runs, oMLX supplies the corrected totals. Qwen's Langfuse trace omitted 18,409 output tokens in three long calls and 641 in the final answer: 11,312 + 18,409 + 641 = 30,362. Slonik and GLM's final totals agree with the saved Markov usage ledger. The long Qwen calls and following context reductions suggest compaction; this is an inference rather than a direct compaction count.

For replication, the saved Markov ledger and oMLX counters agree after excluding startup probes. Slonik's first Langfuse trace missed 104,150 input and 381 output tokens for one compaction. The first Qwen run recorded five compactions; its later run recorded none.

Raw traces, private service addresses, credentials and session identifiers are omitted. Numerical results, patch hashes, prompts, recoverable settings and executable checks are included.

## Limits

The public `RETURNING OLD` report predates Slonik's release. Its presence in training data is unknown. Offline execution prevents looking up the fix during a run but cannot establish that the model had never encountered it.

The replication defect was constructed after the compared model artifacts were available. This reduces the chance of exposure to that particular defect without excluding knowledge of similar mechanisms.

The cases are few, configurations differ, and some candidates needed additional attempts or human test repair. C-code behavior and test quality are assessed separately. These data support a case study of local coding assistance, not a stable quality ranking or an isolated estimate of the benefit of Slonik's training.
