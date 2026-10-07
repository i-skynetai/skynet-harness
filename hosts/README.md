# Host support — install Sky on Claude Code or Codex

Sky ships native Claude Code and Codex plugins with the same Python runtime.
Use the host you already have. Install and authenticate its CLI separately;
Python 3.11+ and Git must be on PATH.

## Supported governed runs

| Host | Roles | Boundary |
|---|---|---|
| Claude Code | developer, reviewer, architect, security | Checked `--agent sky:<role>` definition; `--allowedTools` pre-approves |
| Codex 0.160.0 | developer, reviewer in managed local-store projects | Isolated app-server configuration, read-only permissions and individual policy-checked approvals |
| Kimi | None | No verified managed boundary |

Codex native `$sky:code` and `$sky:review` call the local `sky_dispatch` server.
It invokes the existing launcher; the parent does not perform the work. A
person admits the plan before implementation. The controller denies unknown
requests, wider permissions, ungranted commands, governance-file edits and
paths outside the target repository. Only observed completed MCP calls enter
the ledger. Host completion is distinct from passing task acceptance checks.

The parent retains its normal host permissions. This is not an adversarial
sandbox or unattended publication system. Current live evidence is Windows
with Codex 0.160.0; other versions refuse. Linux/macOS live validation,
Codex architect/security roles and remote/code context in this controller
remain unverified. Legacy remote reviewer launches remain read-only.

## Claude Code

```sh
claude plugin marketplace add i-skynetai/skynet-harness
claude plugin install sky@sky --scope project
claude plugin list
```

Follow the [user guide](../docs/user-guide.md) for a managed repository,
local context and the first task. Publication stays with a person.

## Codex

```sh
codex plugin marketplace add i-skynetai/skynet-harness
codex plugin add sky@sky --json
codex plugin list --marketplace sky --json
```

The add command reports `installedPath`: that is `<plugin-root>` below.
The list must report installed and enabled. Start a new chat after installation
or upgrade. Installing the plugin does not configure a repository or approve
an implementation plan.

From the target Git repository, run:

```sh
python <plugin-root>/bin/sky setup init --local
python <plugin-root>/bin/sky policy render
python <plugin-root>/bin/sky kb serve --write-adapter
python <plugin-root>/bin/sky kb init
python <plugin-root>/bin/sky doctor --hand codex
```

Store an analysis and a plan through `sky kb analyze put` and `sky kb plan put`
([context loop](../docs/features/SH-083-context-loop.md)). Only a person runs:

```sh
python <plugin-root>/bin/sky plan admit <plan-id>
```

In Codex, ask `$sky:code` to implement that bounded task or `$sky:review` to
review it. The dispatcher takes the session's canonical managed repository
root and task. No arbitrary command, environment or role override is exposed.
A missing, used, expired or stale admission refuses implementation.

### Tool approval

The implementation tool edits code, so Codex may ask to approve its call.
A noninteractive session with approval policy `never` refuses it. To explicitly
trust this one tool, a person can add this to their Codex configuration:

```toml
[plugins."sky@sky".mcp_servers.sky_dispatch.tools.implement]
approval_mode = "approve"
```

This does not grant the child wider permissions or issue plan admission.
The per-tool setting follows the [official plugin approval configuration](https://developers.openai.com/plugins/build/plugins).
Keep other tools on their existing approval policy. If the tool is unavailable,
check `codex mcp list --json`, Python on PATH and the enabled plugin, then
restart the chat. Do not bypass a refusal through the parent's shell.

### Upgrade and verification

```sh
codex plugin marketplace upgrade sky
codex plugin add sky@sky
```

Start a new chat and verify the reported version and readiness again. The
older `sky host codex --into <directory>` command exports read-only rules and
configuration; it is not the native installer or developer boundary.

`python scripts/check-codex-plugin.py` exercises installer and skill discovery
in an isolated home without a model call. Offline protocol tests cover malformed
requests, disconnects, timeouts, permission widening and denied paths. Live
install → dispatch → implementation/test and review evidence is in the
[SH-096 probe record](../docs/features/SH-096-probe-2026-10-07.md). Report live and
offline results separately; neither local success nor a badge substitutes for CI.