---
name: plan
description: Turn a cited analysis into ordered work with observable acceptance checks and pinned inputs. Use when the user asks "plan from this analysis", "turn this analysis into steps", or "prepare a governed implementation plan". Stops at unresolved decisions; performs no implementation.
---

# /sky:plan

> **How skills work here** is `SKILLS.md` beside this plugin: saved procedures,
> descriptions that say when to use them, durable corrections, and evidence
> before returning anything.
>
> **Configuration.** Resolve project settings and the tool spelling this session
> actually has as `CONFIG.md` beside this plugin describes. Use bare configured
> read tool names rather than assuming a server prefix.

Return plan text; runtime persistence
pins its inputs. A plan alone does not grant permission to implement.

1. Read the analysis by id. Inspect cited findings and decision candidates.
   If any question has no current applicable closed_by decision, stop with
   the count of OPEN questions and ask the human to run decide. Do not invent
   a decision or produce executable implementation steps around the blocker.
2. Use `templates/plan.md` for ordered steps. Each step names an architect,
   developer, reviewer or security role, bounded work, observable acceptance
   checks and inputs. Include the review and security gates required by the
   workflow; never invent an available role or identity.
3. Cite the analysis, its closing decisions and relevant knowledge records.
   The runtime pins their revision digests and the code checkout. Never supply
   pins, stamp fields or a stored stale flag. Unknown checkout currency remains
   explicit; dispatch admission is a separate runtime check.
4. Return the plan to the parent for validation and storage. If current inputs
   changed, re-analyze/re-plan rather than treating the old plan as current.

Requested tools: Read, Grep, Glob and configured knowledge/code read operations.
No Write, outward tool or automatic build is requested.

## Check your work

Before returning, verify every step against the goal and cited analysis, every
acceptance check against an observable outcome, and every closed question against
accepted/current/in-scope decision evidence. Verify dependencies and role names;
report missing evidence and stale inputs instead of claiming the plan is ready.
