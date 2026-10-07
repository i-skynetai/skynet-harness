# SH-093 — An organisation can see what it gets

**Status:** historical proposal · **Owner:** @arupmmi07 · **Date:** 2026-10-06

This records the original proposal, not the current installation or capability guide.
The README was subsequently updated; the 2026-10-07 consistency pass is SH-094.
Use [the current README](../../README.md) and [documentation index](../README.md)
for working commands and status. This proposal keeps its badges, sixty-second offline demo,
numbered usage, limits and licence. Replace the opening and feature section within
the existing 900-word budget; remove equivalent old prose rather than append this.
Do not announce the complete loop as shipped until its roadmap rows are validated.

## Proposed first screen

These are five text lines, plus one picture; retain the existing badge block beneath
the title. The maintainer rendered the organisation figure from the Mermaid source;
its current and planned paths are kept distinct.

# Skynet Harness
*One policy for the AI coding agents your team already uses.*
Give Claude specialists clear roles, selected knowledge and checks before a run starts.
Keep outward actions at a human checkpoint and retain the runtime's record.
The 3.0 roadmap adds the loop: retrieve → analyze → decide → plan → build → refresh.

![Current checked specialist runs and human shipping checkpoints, with the planned project-context loop shown by dashed paths](../images/org-loop.png)

The README target is `docs/images/org-loop.png`. Codex's managed reviewer uses its own read-only
sandbox; it does not acquire Claude's per-role tool boundary.

## Proposed “What it does”

- **Roles your team can review.** Skills name tools, roles grant skills, and policy
  bindings name actions. Claude's agent definition is the availability boundary;
  missing or drifted definitions refuse launch. Org/project layers can narrow the
  shipped ceiling; replacement launches still await SH-062.
- **Context selected for the task.** The current runtime resolves one KB by repository,
  override or default, with privacy checks. The planned local store and context protocol
  connect your documents, code index and decision history (SH-024/040/083/084).
- **An analysis and plan that become reusable context.** In the planned loop, read-only
  agents return cited analysis and knowledge; the runtime validates and persists them.
  People confirm decisions; stale or conflicting answers remain OPEN. Plans pin their
  inputs before governed dispatch (SH-082/085–088/091).
- **Review and a human shipping checkpoint.** Current roles include architect, reviewer
  and security; the broker renders supported outward-action intents and executes none.
  Ordered automatic workflow gates and remote-KB publication remain SH-075/079/081.
- **Evidence that distinguishes checks from claims.** Current readiness probes and run
  records retain outcomes and host-reported usage. MCP-call manifests, refresh and golden
  retrieval evaluation add measured context, staleness and offline regression checks
  (SH-031/068/089/090); live model judgments are recorded separately.

## Acceptance before applying

Keep the first PNG within 25 lines, one opening picture, and at most 900 prose words.
Keep the real demo/output image and numbered usage. Show current host limits and
row-tagged planned behavior. Render and inspect the organisation PNG, then run the
documentation checker. Do not copy illustrative document counts, token savings,
enterprise adoption or customer results into the README without measured evidence.

## Diagram sources

[org-loop.mmd](../images/org-loop.mmd) is the proposed organisation figure, authored
in Mermaid and rendered to PNG by the maintainer. Solid connections describe current
runtime paths; dashed connections and labels name the planned loop.
