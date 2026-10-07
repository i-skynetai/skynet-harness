# Make AI a team working practice

Use Skynet Harness as the team's standard way to delegate coding work: shared rules,
selected project context, reviewed decisions, checked launches and a human publication
checkpoint. It supplies neither a model nor evidence that your team will work faster.

## Why use it

Generating code is only part of delivery. Understanding the repository, explaining the
same constraints again, reviewing mistakes and recovering missing decisions also take
time. The harness aims to make those steps repeatable across sessions.

| Team problem | Available support | Benefit to test |
|---|---|---|
| Every session starts with repeated explanation | Local documents indexed by `sky kb init`, search and an optional code index | Less time gathering context |
| A review agent acts as an implementer | Checked Claude role tool lists; Codex reviewer sandbox | Clearer delegation boundaries |
| The same question is decided repeatedly | Decision proposals with runtime-recorded human approval | Fewer repeated questions and conflicting choices |
| Missing setup is discovered after starting work | `sky doctor` and launch checks | Less time diagnosing failed starts |
| Success claims lack evidence | Runtime run records and MCP context manifests | More useful review evidence |

These are expected benefits, not measured speed, cost or adoption improvements.
The complete analyze → plan → governed workflow, automatic discovery/refresh and
`sky eval` are still roadmap work. See [current status](../README.md#status-and-history).

## What making it the standard means

The team agrees to use checked launches for supported specialist work, maintain project
documents, record important decisions and review publication. A maintainer owns policy
changes. Contributors can question the rules and propose reviewed changes.

Installing the plugin does not make every action mandatory or technically enforced.
Parent-session Edit/Write/MCP tools remain unrestricted; ordinary-session routing and
workflow admission are planned. Claude has per-role tool boundaries; Codex supports
managed reviewer runs only. Read [host limits](../hosts/README.md).

## Start with one repository

1. Follow the [user guide](user-guide.md) and [offline example](../examples/README.md).
   Choose a repository with public or appropriately protected project documents.
2. Name a policy owner and agree which supported tasks use checked launches. Start
   with review; do not promise the unfinished workflow to the team.
3. Index useful documentation, inspect search results and record exclusions. Connect
   a code index only when its coverage is understood. Keep secrets and private data
   out of public repositories and outward artifacts.
4. Record an important decision as a proposal. A person reviews the exact revision
   and accepts it; a retrieved candidate alone never settles a question.
5. Review the results of a small pilot before expanding to more contributors or
   repositories. Feed reproducible problems into the [backlog](../ROADMAP.md).

## Measure delivery, quality and adoption separately

Compare similar tasks before and during the pilot. Record the sample size, dates,
repository revision, host/model, task difficulty and skipped checks. Do not attribute
every difference to the harness when the tasks or models changed.

| Question | Evidence to collect |
|---|---|
| Did work reach review sooner? | Time from task start to the first reviewable change |
| Did correction effort fall? | Review rounds, rework time, reopened defects |
| Did context improve? | Missing-context findings, repeated questions, sources used |
| Did usage improve? | Actual host-reported usage and measured retrieved characters; keep estimates labelled |
| Did people adopt the process? | Contributors using supported checked runs, successful first setups, reasons for opting out |

Set targets from your own baseline. Report failures and costs as well as gains.
Faster code generation by itself does not establish faster delivery or safer work.

## Where evals fit

**Planned: SH-090.** `sky eval` will use known tasks and expected context to measure
retrieval recall, precision and delivered size offline. Optional live runs will assess
analysis/plan quality against a rubric. Those scores are separate from team delivery
metrics, and a retrieval score alone cannot prove better adoption.

Today `sky context manifest <run>` reports observed retrieval events and sizes. It
does not implement the golden-task eval runner or enforce a context budget. SH-080
covers budget enforcement; SH-090 covers evals.

## How these docs are organised

The [documentation index](README.md) separates a runnable example, task guides,
reference material and explanations. This follows the four reader needs described by
[Diátaxis](https://diataxis.fr/start-here/). Contribution guidelines and issue/PR
templates follow [GitHub's contributor documentation](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors).
