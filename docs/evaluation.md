# Check whether retrieval finds the right context

`sky eval` checks a local context store against a **golden set**: questions with
expected record ids and optional phrases. It runs offline, without a model
account, network or Python dependencies. Run this example from a disposable
Git repository; do not evaluate the demo questions against an unrelated corpus.
Python 3.11+ and Git must be on PATH. `<checkout>` is your harness checkout.

## Try the public example

Create a new folder, enter it, and run `git init`. Copy the five Markdown files
from `<checkout>/examples/demo-docs/` into `docs/demo/`, preserving their names.
Then run these commands from that new repository:

```sh
python <checkout>/sky setup init --local
python <checkout>/sky kb init
python <checkout>/sky eval --golden <checkout>/evals/golden --baseline <checkout>/evals/baseline.json
```

The supplied questions name ids from the demo documents. The report prints one
row per question and an overall result, then writes text and JSON reports under
`.sky/runs/<run-id>/`. Exit code 0 means the baseline passed; a regression or
invalid fixture exits nonzero with a reason. This is a context test, not a model
implementation run, so no host login or plugin installation is required.

## Read the result

| Measure | Meaning |
|---|---|
| Recall | Expected unique record ids found, divided by expected ids |
| Precision | Expected ids found, divided by all returned unique ids |
| Characters | Unicode code points in the canonical JSON response, including metadata |
| Estimated tokens | Characters divided by four; not measured tokenizer usage |

Multiple chunks of the same record count once for recall and precision. No
hits means zero recall and undefined precision, which fails evaluation. A
required phrase must appear in the retrieved content. Character thresholds
limit response size, not the total model prompt or reasoning cost.

## Use your own questions

Create a folder of JSON fixtures following [the fixture reference](../evals/golden/README.md).
Each item needs `id`, `question`, `expect_ids`, `capability` (`search` or
`decisions`) and `k`. `must_contain` is optional. Use ids that actually exist in
your store. Missing ids, duplicate question ids and unknown fields are refused.
Choose representative questions, including cases your team previously missed.
Review expected records and thresholds before treating a score as useful.

Point `--golden` at that folder and `--baseline` at your reviewed baseline file.
A person can replace an existing baseline with the observed report:

```sh
python <checkout>/sky eval --golden <your-golden-folder> --baseline <your-baseline.json> --update-baseline
```

Updates refuse inside a governed session and when expected ids or phrases are
missing. Review the changed baseline as code; increasing a threshold to conceal
a regression does not improve retrieval. The default comparison tolerances are
zero. Keep baselines separate for different corpora and intentional scenarios.

## Current limits

The shipped evaluator measures local search and decision retrieval. It does not
score generated analysis, plans or code through a live model rubric. A perfect
retrieval score does not prove faster delivery, fewer defects or stronger AI
adoption. Measure those separately in a [team pilot](adoption.md).
