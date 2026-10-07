# Offline retrieval fixtures

These six questions use the public `examples/demo-docs/` corpus copied into
`docs/demo/` and initialized in a temporary project. Three explicit document ids
make the fixtures portable. The sample ADR is documentation, not an accepted
runtime decision; these questions therefore use search. Decision retrieval has
separate fake-store tests.

Each JSON item requires `id`, `question`, unique nonempty `expect_ids`,
`capability` (`search` or `decisions`), and `k` (1–100). `must_contain` is optional.
Unknown fields and duplicate question ids are refused. Multiple chunks of one
document count once for recall and precision. No hits means zero recall and
undefined precision, and fails evaluation.

Characters count Unicode code points in the canonical JSON retrieval response,
including result metadata. Tokens are **estimated** as characters divided by
four; this is neither tokenizer measurement nor proof of prompt delivery.

`../baseline.json` starts with authored acceptance thresholds: complete recall,
complete precision and at most 4096 response characters per question. These are
budgets, not claimed observations. A reviewed human baseline update replaces
them with the observed report. Default tolerances are zero. Live model reasoning
rubrics are outside this offline slice and do not gate CI.

CLI wiring follows in the next slice phase; the importable evaluator and tests
already exercise retrieval, comparison and report writing without a provider.
