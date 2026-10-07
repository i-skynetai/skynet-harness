---
name: code
description: Implement a bounded code change with project context, tests and a reviewable result. Use when asked to implement or fix code with Skynet Harness.
---

# Sky code on Codex

This is a native Codex workflow skill. It is not a role permission boundary.
The managed Sky launcher currently offers Codex read-only reviews only;
managed implementation parity is tracked as SH-096. Never describe a normal
Codex coding session as a governed developer launch.

## Locate the shared package

Use the absolute path of this loaded SKILL.md. Its directory is
`<plugin-root>/codex-skills/code/`. The plugin root is two directories
above that directory. Resolve reference paths below against that root,
not against the user's repository. Do not guess a cache path.

1. Read `SKILLS.md`, `CONFIG.md` and `policy.yaml` from the plugin root.
2. Read `skills/code/SKILL.md` and follow its procedure. Its `agent:` field
   describes the Claude role; it does not select or grant a Codex role.
3. In that shared procedure, `/sky:<name>` means read and follow
   `skills/<name>/SKILL.md` from this package. Interpret
   `${CLAUDE_PLUGIN_ROOT}` as the resolved plugin root, not a Codex variable.
4. The bundled runtime is `bin/sky` in the plugin root. Invoke it as
   `python <absolute-plugin-root>/bin/sky <arguments>`; on Unix `python3`
   may be the interpreter name. Run it from the target repository.

## Host permissions and output

For implementation, use the person's Codex workspace permissions. If the
session is read-only, return a patch or explain the missing write permission;
do not bypass the sandbox. A review must inspect code without changing it.
Before either workflow, retrieve project context through configured read
capabilities. If context is unavailable, state the gap rather than invent it.

Prepare code, tests or review findings as the shared procedure requires.
Do not push, open or merge a PR, send a ticket message, approve a decision,
change permissions or perform remote ingestion. Return proposed outward
actions for a person. Check results and state what ran, failed or was skipped.
