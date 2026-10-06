# Policy

One file — `plugin/policy.yaml` — read by everything that decides. This document
explains what it contains and why it is shaped this way.

## Two rules hold it up

**1. Default deny.** An action a role does not list is denied. An action not named in
`actions:` at all is denied, not assumed harmless.

**2. No outward action is ever plainly allowed.** Anything that reaches the world
outside this machine is `needs_human` or goes through the broker. You cannot give a role
`push` by editing the file.

`sky policy lint` fails if either rule is broken.

## Why one file

Three components decide things at three different moments:

- the **launcher**, before the hand starts — the tool allowlist
- the **guard**, during the run — the command about to be executed
- the **broker**, before an outward action

They must give the same answer. Two policies eventually become the looser one, and
nobody notices which. So there is one file rather than a list inside each component.

## Actions

Every action a role can request, and whether it leaves the machine:

```yaml
actions:
  repo.read:
    outward: false
    description: "read files in the repository under work"
  repo.edit:
    outward: false
    description: "create or change files inside the repository"
  repo.edit_outside:
    outward: false
    description: "create or change files outside the repository"
    never: "a hand works in one repository; writing outside it is how a run
            touches something nobody reviewed"
  commit.local:
    outward: false
    description: "commit to a local branch; nothing leaves the machine"
```

`outward: true` means it changes something other people can see — a push, a pull
request, a ticket comment, an ingest. Those never get a plain allow.

A `never:` field records *why* something is refused. A rule without a reason gets
relaxed by the next person who finds it inconvenient.

## Roles

| Role | Gets | Does not get |
|---|---|---|
| **Developer** | Read, Edit, Write, Bash for tests and local commits, KB read | push, PR, ticket write |
| **Reviewer** | Read, Grep, Glob, KB read | Edit, Write, Bash — it reviews, it does not fix |
| **Architect** | Read, Grep, Glob, KB read including graph queries | Edit, Write, Bash — it returns design text; the main thread writes the file |
| **Security** | Read, Grep, Glob, KB read | everything else |

A role a host cannot enforce is not offered. If a coding agent cannot restrict tools
the way a role requires, that role is unavailable on that host rather than approximated.

## Skills own tools

Version 1 policies can give a role `base_tools` and an ordered `skills` list.
Each skill declares `tools`, including `+group` references. The role receives the
base tools followed by its skills' tools, with group expansion and duplicates
removed in first-seen order. Roles grant skills; a skill cannot declare `roles`.
Legacy role `tools` lists retain their validation and need no bindings or registry;
they cannot be mixed with either new role key, even an empty one.

The policy's top-level `tools` maps each tool to an action: a string is shorthand
for a mapping containing `action`. A mapping may also name `reviewed_by`; every
MCP binding requires that reviewer handle. A tool used for both reading and
writing binds to its write action. Every new-style tool needs a binding to an
existing action in the role's `may` or `needs_human`. Outward and `never` tools
cannot be granted, even indirectly through a group: outward actions are prepared
as intents in `.sky/outbox/`, not called. Provider annotation checks are reserved
for SH-067; the offline annotation hook currently reports no annotation problems.

`sky policy render` (also `sync-agents`) checks every existing role template before
writing, preserves its metadata and body, and renders tools plus the plugin source
`registry.json`. Missing, malformed or misnamed templates refuse the whole render.
The registry records active `sky:<role>` identities and a SHA-256 digest of parsed
policy JSON: mapping keys sorted, list order preserved, UTF-8, no generated artifacts.
Comments and whitespace do not affect that digest. `sky policy lint` additionally
refuses missing or stale registries and agent drift; loading a policy needs neither
artifact. `check-agents` checks drift without writing. `show` names declared skills
granted to no role; procedure alignment is tracked in SH-082.

The effective project `.sky/registry.json` and replacement identities belong to
SH-065/SH-062; this row renders only the plugin source registry.

## The two tiers

**Tier A — the tool allowlist.** Fixed before the model exists. A reviewer never
receives `Bash`; no string it produces changes that. This is the boundary.

**Tier B — the guard.** Needed because tier A is all-or-nothing. A developer *does* get
`Bash`, for tests and local commits, and `git push` has to be stopped inside that grant.
The guard reads the command and answers on it.

The guard matches on a string, and a string can be rewritten. `git push` is caught. A
base64-decoded `eval` is not. This stops the ordinary attempt and the honest mistake —
which together are nearly all of them. It is not a sandbox, and calling it one would be
the real danger.

## The broker

For outward actions the broker **renders** the command. It does not execute it. You
read it and run it yourself.

This is why a model cannot claim it opened a pull request: opening one was never
something it could do.

## One hand, one knowledge base

![How a run reaches exactly one knowledge base, is given no write tool, and leaves
outward writes as intents for the broker](images/sky-hand-contract.png)

The contract in one picture: the agent reaches exactly one knowledge base, is handed
no supported write tool, and every outward write leaves as an intent the broker renders
for a human. Nothing in the run can widen any of the three.
