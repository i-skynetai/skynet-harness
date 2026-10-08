# Local workflows, routing and context budgets

These commands are available on unreleased main. Run them from a managed Git
repository with the host plugin installed, local context initialized and
`sky doctor` passing. `<checkout>` is the harness checkout. A person admits a
current plan before any developer step:

```sh
python <checkout>/sky plan admit <plan-id>
python <checkout>/sky workflow run feature --task "Implement the admitted change" --hand claude
```

The shipped `feature` workflow retrieves context, checks for duplicate work,
runs architect, developer, reviewer and security steps, then prints `sky ship`.
Optional unavailable duplicate sources are named and skipped. A failed step
stops advancement. Review gates require one final `VERDICT: APPROVED` line;
missing, conflicting or blocked verdicts stop the workflow. The verdict is an
agent review result, not human approval to publish. The ship step prints a
command; it never runs publication. Dry runs check launches but do not invent
agent verdicts, and a developer dry run still consumes its admission.

## Host scope

The four-role feature workflow uses Claude. Native Codex currently supports
only developer and reviewer on the recorded Windows 0.160.0 local-store path.
It refuses architect/security; selecting Codex for every feature step therefore
stops rather than pretending those roles are supported. Native `$sky:code` and
`$sky:review` remain the supported Codex entry points. A reviewed workflow may
select a host per step, while each launch retains that host's checks and the
same plan-admission contract. See [host setup](../hosts/README.md).

## Route a goal

```sh
python <checkout>/sky route "Review the cache change" --hand claude
python <checkout>/sky route --role reviewer --task "Review the cache change" --hand codex
```

Routing uses declared policy rules. Ambiguous or unmatched goals print choices
and return without launching a hand. An explicit role uses the ordinary build
checks; choosing developer does not bypass admission. Invalid roles, workflows,
cycles, dependencies or undeclared hosts fail policy validation. Named-session
and remote bridge dispatch remain unshipped.

## Bound runtime context

A project's `.sky/project.yaml` may set `context.max_tokens`. The shipped
default is 10,000 estimated tokens, counted as Unicode characters divided by
four. `max_chars` remains a character ceiling; without an approved override,
the smaller ceiling wins. These are character-based estimates, not tokenizer
measurements or a guarantee about the model's total prompt.

An oversized runtime pack is refused before delivery and records a pending
manifest for that exact task. A person can approve a larger budget:

```sh
python <checkout>/sky budget approve --task "Implement the admitted change" --tokens 15000
```

The confirmation names the task and manifest digest. Approval is bound to that
exact pack; changed content requires another confirmation. Governed sessions
cannot approve larger budgets themselves. Codex checks its task, retrieved
context and installed procedures before consuming plan admission, and passes
that task identity and initial character count to its local context server.
Local server responses count cumulatively. Direct remote MCP responses are
measured but not intercepted or capped by this runtime path.

## Prepare remote handover ingestion

`sky kb put` retains a handover locally. When a remote ingest destination is
configured, the runtime also seals an intent under `.sky/outbox/`; otherwise
it stays local. `sky ship` prints the confirmation command. Only a person runs:

```sh
python <checkout>/sky ingest .sky/outbox/<intent-id>.json
```

The confirmation shows destination identity, source, runtime stamp and payload
digest. Changed local content, a changed destination, malformed provenance or
an unacknowledged write refuses execution. The handover stays local after
confirmation. Remote transports are covered by offline fixtures; these checks
do not claim a live provider write. Store writes and remote ingestion are not
role-granted tools in governed children.
