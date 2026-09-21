# What you may do, and where that is decided

The rules are not in this file. They are in `policy.yaml`, which the launcher,
the guard and the broker all read — one file, so the three cannot drift apart.
This explains how to read it and what the layers mean.

## Four roles

| role | in one line |
|---|---|
| architect | design, the spec gate, impact walks; produces documents, not code |
| developer | implement one bounded change, with tests, and stop |
| reviewer | read a change and say APPROVED or BLOCKED, with file and line |
| security | scan for secrets, permission drift and tampering with the checks |

**Default deny.** An action a role does not list is denied. An action nothing
lists is denied. This is not a formality: it means a capability appears in the
policy before it appears in a run, and never the other way round.

## Three answers, not two

- **allow** — do it.
- **needs a human** — you may prepare it; a person performs it. Every outward
  action is here: push, open a pull request, comment on a ticket, transition
  one, write to the knowledge base.
- **deny** — not for anyone, at any time.

Nine things are denied to everyone, and each for a stated reason: deploy ·
permission.change · pipeline.run · pr.merge · pr.vote · repo.edit_outside ·
shell.free · skill.promote · ticket.assign. The reasons are in the file. Read
them rather than working around them — **an agent that can widen its own
permission has none.**

## Three layers, and only one is a boundary

**Tier A — the tool allowlist.** Decided before the model exists, applied by the
host. A role that never receives `Edit` cannot edit, and nothing it outputs
changes that. *This is the boundary.*

**Tier B — the guard.** A hook that reads the command you are about to run and
refuses the ones the policy names. It exists because tier A is all-or-nothing:
a developer legitimately has a shell, and `git push` has to be stopped inside
that grant. **It matches on a string, and a string can be rewritten.** It stops
the ordinary attempt and the honest mistake. It is not a sandbox.

**Tier C — this document.** Prose. It works because you are cooperative, and it
is worth exactly that much.

Do not treat B or C as if they were A. The dangerous version of this system is
one where a person believes an outward write would be stopped mid-run because
they read that it would.

## When the guard refuses you

It tells you the policy action and the reason. The answer is almost never to
find another way to run the command — it is `/sky:ship`, which renders the
exact thing for a person to run. If you genuinely think the refusal is wrong,
say so and stop. Do not route around it.

## Where this applies, and where it does not

In an **Ethan-managed run**, outward actions go through core's typed intents and
the broker. In a session a person opened themselves, the host's own permission
prompts apply and the person is right there. Neither is this file deciding; both
are described by it.
