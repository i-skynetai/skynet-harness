# Contributing

## Running the tests

```bash
python3 -m unittest discover -s core/tests -t core
```

523 cases, standard library only — no pytest, no install step. That is the same command
CI runs, so a green run here is the run that matters. They must pass before a change is
considered.

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

## Style

Match the file you are editing. The code explains its own reasoning in docstrings; keep
that habit — the *why* is the part that survives.
