# Contributing

## Running the tests

```bash
python3 -m unittest discover -s core/tests -t core
```

661 cases, standard library only — no pytest, no install step. CI runs the same
command, then `./core/bin/sky selftest`, which fails if the plugin's copy of the runtime
has drifted from `core/`. Both must pass before a change is considered. After editing
anything in `core/sky/`, refresh the copy with `python3 scripts/vendor-runtime.py`.

`selftest` also checks the whole tree for a private list of organisation names, using
only their salted hashes in `scripts/private-words.sha256`. The plain list stays on the
maintainer's machine; after changing it, run `python3 scripts/hash-private-words.py`.

## Picking and claiming work

All planned work is a row in [ROADMAP.md](ROADMAP.md) with an ID (`SH-…`), priority,
size, status and owner. Work that is not a row is not planned.

1. Choose a `Ready` row. New here? Take one marked *good first issue*.
2. Claim it with the [*Claim a feature*](.github/ISSUE_TEMPLATE/feature_claim.md) issue
   template, naming the ID.
3. Set the row to `In progress`, with your handle and the date in the Owner column.
4. For an L-sized feature, write a design note from
   [docs/features/TEMPLATE.md](docs/features/TEMPLATE.md) first.
5. Open the pull request and set the row to `In review`. A maintainer sets it to
   `Done — <version>` when it merges.

## What a change needs

- **A test that fails without it.** A pass needs a positive observation, not the absence
  of an error.
- **A reason recorded for any refusal.** If a change makes something impossible, say why
  in the `never:` field or the docstring. A rule without a reason gets relaxed by the
  next person who finds it inconvenient.
- **No new dependency in the core.** The core is standard library. Plugins and hosts may
  depend on what they need.

## What will be refused

- Anything that makes an outward action plainly allowed.
- A role offered on a host that cannot enforce it.
- Silent redaction. If a secret is found, refuse the operation and say so — scrubbing it
  quietly hides the near-miss.
- The core importing from the plugin.

## Documentation

- Write for someone new to the project: short sentences, plain words, and any technical
  term explained where it first appears.
- Every claim in the README must work as written and have a test behind it. A feature
  that does not work yet is a roadmap row, not a sentence in the README.
- Pictures live in `docs/images/`: the SVG source beside a rendered PNG. Pages embed the
  PNG. Render it and look at it before committing.
- A terminal picture shows real command output, never an edited one.

## Style

Match the file you are editing. The code explains its own reasoning in docstrings; keep
that habit — the *why* is the part that survives.
