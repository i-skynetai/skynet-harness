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
| A review agent acts as an implementer | Checked Claude role tool lists; Codex policy-checked developer/reviewer controller | Clearer delegation boundaries |
| The same question is decided repeatedly | Decision proposals with runtime-recorded human approval | Fewer repeated questions and conflicting choices |
| Missing setup is discovered after starting work | `sky doctor` and launch checks | Less time diagnosing failed starts |
| Success claims lack evidence | Runtime run records and MCP context manifests | More useful review evidence |

These are expected benefits, not measured speed, cost or adoption improvements.
Analysis, planning, code discovery/refresh, offline `sky eval` and person-issued
plan admission are available on main. Multi-role workflow dispatch and automatic
ordinary-session routing remain in development. See [current status](../README.md#current-status).

## What making it the standard means

The team agrees to use checked launches for supported specialist work, maintain project
documents, record important decisions and review publication. A maintainer owns policy
changes. Contributors can question the rules and propose reviewed changes.

Installing the plugin does not make every action mandatory or technically enforced.
Parent-session Edit/Write/MCP tools remain unrestricted; ordinary-session routing and
automatic routing remains planned. Governed implementation requires a current,
person-admitted plan. Claude has four supported roles; Codex supports developer
and reviewer on Windows 0.160.0 with managed local context. Read [host limits](../hosts/README.md).

## Start with one repository

1. Follow the [user guide](user-guide.md) and [offline example](../examples/README.md).
   Choose a repository with public or appropriately protected project documents.
2. Name a policy owner and agree which supported tasks use checked launches. Start
   with review, then one admitted implementation task; keep planned automation
   separate from the workflow that has been verified.
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

`sky eval` now checks known questions against expected context, without a model
or network. **Recall** is the fraction of expected records retrieved; **precision**
is the fraction of retrieved records that were expected. It also reports response
characters and a token estimate, labelled as characters divided by four. A
regression against the reviewed baseline exits with a failure and names the item.

Run the [public retrieval example](evaluation.md) before writing a golden set
for your repository. Keep the expected records and thresholds under review;
only a person updates the baseline. Live model reasoning rubrics are not shipped
in this offline evaluator. Retrieval scores measure context selection, not team
delivery speed, implementation quality or adoption.

`sky context manifest <run>` separately reports observed retrieval events and
sizes. General context-budget enforcement remains SH-080 work; the supported
Codex controller already bounds its initial context and workflow briefing.

## How these docs are organised

The [documentation index](README.md) separates a runnable example, task guides,
reference material and explanations. This follows the four reader needs described by
[Diátaxis](https://diataxis.fr/start-here/). Contribution guidelines and issue/PR
templates follow [GitHub's contributor documentation](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors).
