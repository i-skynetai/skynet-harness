# core — the brain runtime and the write broker

The `sky` command. Both Skynet Harness and Ethan depend on this, and it depends on
neither: **`core/` must never import from `plugin/`.** That wall is what lets Ethan
reuse the runtime without taking the content.

Standard library only, Python 3.11+. Ethan carries no dependencies, so adding one here
would add one there.

## What works

```bash
sky doctor                              # what is alive, and what that permits
sky kb list                             # which knowledge bases exist
sky kb which                            # which one applies here, and why
sky policy show                         # what each role may do, and why
sky policy lint                         # does the policy hold together
sky policy developer push               # ask the same question the guard asks
sky policy sync-agents                  # write each role agent's tools: line from the policy
sky policy check-agents                 # report drift without changing anything
sky selftest                            # is this repository still sound
sky build --role developer --task X     # start a hand — or refuse, and say why
      --dry-run                         # run every check, start nothing
      --json                            # one structured line last — for a program (Ethan)
```

| Module | Does |
|---|---|
| `kbmap.py` | loads the KB map; resolves a directory to one KB; **refuses to cross a privacy class** |
| `readiness.py` | the ten parts, their states, and which kinds of work each permits |
| `probes.py` | the ten probes of gate G23a — every one a real call |
| `launcher.py` | builds the hand's environment, **proves** the git block, refuses a build the brain is not ready for |
| `recorder.py` | the run id and the event log, created before the hand exists |
| `hand.py` | runs a coding agent under two watchdogs, and stops one that has stopped working |
| `redaction.py` | the gate anything bound for a KB passes through |
| `schemas.py` | the seven contracts, and **who may fill which field** |
| `selftest.py` | ten checks: does it hold together, and is anything in `plugin/` that must not ship |
| `usage.py` | the bill per run — from the hand's own report, never estimated, never read from its prose |
| `policy.py` | one answer to "may this role do that?" — read by the launcher, the guard and the broker |
| `yamlish.py` | a deliberately tiny YAML reader that refuses what it cannot do correctly |
| `cli.py` | the command |

## What does not

The **guard hook** (H5) — so the policy's rules exist and are applied before a hand
starts, but nothing enforces them *during* a run. The Safety probe reports DEGRADED
rather than OK for exactly that reason. And the **broker** (H5 and H8).

## Two things worth knowing about the code

**The silence watchdog is the one that matters.** A hand that is genuinely stuck emits
nothing, so it sails past any check that only runs after a line arrives — that mistake
let one run continue for three hours under a thirty-minute limit. Both caps are watched
from a separate thread, never from inside the read loop. Disabling the silence cap makes
its test take thirty seconds and fail, which is how we know it is doing the work.

**The redaction gate refuses rather than scrubs.** A silent scrub hides the near-miss,
and the near-miss is the thing worth knowing. It is tested in both directions: a corpus
that must be caught, and a corpus that must not — including this repository's own
documents, which discuss tokens and headers at length. A gate that refuses good writes
gets routed around, and a gate people route around is not a gate.

**The contracts refuse a model's word for the runtime's facts.** Each field is owned by
either the model or the runtime. `validate(..., source=MODEL)` refuses a document in
which a hand filled a runtime field — the commit that exists, the PR that was opened,
what CI said, which agent this is — because a claimed success and a real one are
indistinguishable in a log. `seal()` is the only door those fields come through.
Removing that refusal fails four tests.

**There is one policy, and everything reads it.** The launcher's tool allowlist used
to be a dict in `launcher.py`. Two lists in two files is two policies, and the looser
one wins on the day they differ — so `policy.yaml` is the only copy, and the guard hook
and the broker will read the same file. Two rules in it are enforced by its own lint, so
they cannot be edited away quietly: **an outward action is never a plain allow**, and
**a read-only role may not hold an editing tool**. Removing either check fails a test.

**A role agent's `tools:` line is generated, not maintained.** It is that agent's whole
authority — what is not listed is not visible to it — so a typo in it is silent: the
agent simply cannot do something and nobody finds out until a task fails halfway.
`sync-agents` writes it from the policy and a test fails on drift, the same pattern as
the published JSON Schema files. Whether the tool *names* are real is a different
question, and only the live servers can answer it: `scripts/check-allowlists.py`.

**The bill is read, never estimated.** `usage.py` takes the hand's structured result object — cost, tokens, turns, duration — from the durable log after the run. If the hand reported nothing, the run records `available: false` *with the reason*; a guessed number on a dashboard gets believed. A message that says "this cost $99" is a claim and is not read. Claude is started with `stream-json`, not `json`, because `json` is silent until the end and the silence watchdog would kill a healthy long run. Rule: record everything, show money, judge learning on tokens per task kind within one hand.

**`selftest` distinguishes a skipped check from a passed one.** The list of one
organisation's vocabulary cannot live in core — core ships, and shipping a list of a
company's names inside the tool that removes them would be self-defeating. So it is read
from an uncommitted local file, and when that file is absent the check reports **SKIP**
rather than a clean run it did not perform. "Nothing was checked" and "nothing was wrong"
are different claims.

**A hand-written YAML reader is a risk, so it refuses rather than guesses.** Core takes
no dependencies, so it cannot use PyYAML — but a reader that quietly disagrees with
every other YAML tool about a *security policy* is worse than no reader. Anchors, flow
mappings, block scalars, tabs and duplicate keys are errors, not guesses. The words YAML
versions disagree about (`no`, `yes`, `on`, `off`) and anything numeric that is not a
whole number (`1.0`, `2026-09-14`) are refused outright rather than resolved one way.
The cross-check against PyYAML found all three of those; refusing them is what made the
two readers agree on every case, the real policy file included.

## The launcher, and what it is worth

It is the only place the rule *a brain with no Safety may answer and review, but may not
build* is applied. It cannot live anywhere else — the guard cannot enforce its own
presence, and a skill is text a model may skip. So it runs **before the model exists**.

The environment is built by **listing, not filtering**: it starts empty and names what
goes in. A filter has to be updated every time someone puts a new secret in their shell
profile, and nobody remembers to.

The git block is **proven, not assumed** — `git credential fill` in the built
environment must return nothing, or nothing starts. That is a better check than a
dry-run push, which needs a remote and would pass for the wrong reason in a repository
without one.

**And what it is not: a boundary.** The launcher and the hand run as the same
operating-system user, so a hand with a shell can read the token file or reach around
any of this. Defence in depth against mistakes, not containment of an adversary. It
becomes a boundary at harness step H10, and gate G25 proves it.

## Two rules that shaped the code

**A pass needs a positive observation.** Never "no error", never "configured" — something
came back and it was the right shape. Ingest reported `COMPLETED` with zero entities for
two days while every configuration-level check called it healthy.

**Two probes are inverted.** For *safety* and *actions* the healthy answer is a failure —
a guard that denies, a push that cannot happen. A probe treating those as errors would
have the truth exactly backwards.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

They are mostly about refusals, because that is where the value is: a client repository
quietly answered from the team's knowledge base looks exactly like success. Both
load-bearing rules were mutation-checked — the guard was removed and the suite failed.
