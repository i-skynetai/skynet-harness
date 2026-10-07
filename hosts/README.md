# Host support — install Sky on Claude Code or Codex

Sky has native Claude and Codex manifests in the same plugin package. The
[Codex marketplace](../.agents/plugins/marketplace.json) installs the native
`code` and `review` workflow skills; Claude uses its existing skills and
agent definitions. Both include the bundled Python runtime.

The older `sky host codex` command exports a rules/configuration package and remains
available. It is not the native plugin installer. The installed plugin and a managed
launcher run are different: installing workflows does not grant or enforce a role.

## What each host can actually enforce

Measured from `codex --help` and `kimi --help`, not assumed:

| host | mechanism | what it buys |
|---|---|---|
| claude | `--agent sky:<role>`, with a checked definition's `tools:` list | **tier A — the boundary**; `--allowedTools` pre-approves calls |
| codex | `--profile` layering config, `--sandbox read-only` | a real limit for reading; nothing per-role |
| kimi | `--skills-dir`, `config.toml` | the skills load; no role selection at all |

That table is why the roles are not offered everywhere. Codex may be asked for
`reviewer` only; Kimi for no role, because it has no way to set the knowledge base for
one run, so a managed Kimi run could read whichever knowledge base the person's own
settings name. The launcher's `HAND_ROLES` (`core/sky/launcher.py`) is the one table;
`sky host` and this page follow it, and a test fails if they differ. Not because
the other roles matter less, but because **a role a host cannot keep inside its
limits is a label**, and each generated package says so in its first paragraph.

## Install and verify each supported host

Use Git and Python 3.11+ for the shared runtime. Install and authenticate the chosen
host CLI separately. Commands below run from the target Git repository; replace
`<harness-checkout>` with your checkout path. These are CLI integrations, not a claim
that every desktop session automatically uses Sky.

### Claude Code

```sh
claude plugin marketplace add i-skynetai/skynet-harness
claude plugin install sky@sky --scope project
claude plugin list
python <harness-checkout>/sky build --hand claude --role reviewer --dry-run
```

Follow the host's plugin activation message. Each collaborator installs the plugin.
Before the dry-run, configure the target repository, its context and test runner using
the [user guide](../docs/user-guide.md). A successful dry-run checks readiness; it does
not prove an authenticated model run. Claude also supports developer, architect and
security roles on managed launches whose definitions match policy.

### Codex native plugin

```sh
codex plugin marketplace add i-skynetai/skynet-harness
codex plugin add sky@sky
codex plugin list --marketplace sky --json
```

For a local checkout, use `codex plugin marketplace add <harness-checkout>` instead
of the GitHub source. The list should report `sky@sky` installed and enabled. Start a
new Codex chat and invoke `$sky:code` to implement a bounded change or `$sky:review`
to review one. The skills locate the shared procedures and bundled runtime inside
the installed package; they require no global `sky` installation.

These are workflow instructions under your Codex session's existing permissions.
They do not install Claude hooks or enforce a developer tool allowlist. A read-only
session must return a patch rather than bypass its permissions. Publication and
decision approval remain human steps.

The current managed launcher supports only reviewer on Codex. After configuring a
KB profile/default and target readiness as described in the user guide:

```sh
python <harness-checkout>/sky build --hand codex --role reviewer --dry-run
```

After readiness passes, replace `--dry-run` with `--task "Review this change"` for
an authenticated review. The launcher requests `--sandbox read-only`. Its local
stdio context adapter has not been demonstrated end to end on Codex.

**Required parity (SH-096):** both Claude and Codex must support governed implementation
and review, local context and run evidence. Codex native installation is the first
step; managed developer support remains unfinished. Current Codex exposes hooks,
MCP tool filters and sandbox controls, which must be probed before changing the
launcher. See [official packaging](https://developers.openai.com/plugins/build/plugins)
and [configuration](https://learn.chatgpt.com/docs/config-file/config-reference).

Upgrade the source with `codex plugin marketplace upgrade sky`, then run
`codex plugin add sky@sky` and start a new chat. Check the listed version and readiness.
Do not replace your personal config or copy a shared token.

### What has been checked

Host-package and launcher tests verify generated content, refusal of unsupported
roles, agreement between role tables and the Codex read-only command. These offline
tests do not prove login, a live context connection or completion of a real review.
Report those separately with host version and result. Use `sky doctor` and dry-run
refusal messages to resolve prerequisites before a live run.

Run `python scripts/check-codex-plugin.py` from the harness checkout to repeat the
installer/discovery check in a temporary Codex home. It makes no model call.

**Observed installation, 2026-10-07:** Codex CLI 0.160.0, isolated temporary Codex
home: local marketplace add succeeded; plugin add reported version 2.1.2; list reported
`installed: true` and `enabled: true`; the prompt diagnostic exposed `sky:code` and
`sky:review`. Temporary-home helper-alias warnings did not
prevent installation. This is installer evidence, not an authenticated model run.
