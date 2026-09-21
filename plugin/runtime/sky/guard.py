"""The guard, and the ledger — tier B, and honest about being tier B.

**Tier A is the tool allowlist.** A role that never receives `Bash` cannot run
a command, and no string it emits changes that. It is decided before the model
exists and the model cannot reach it. That is the boundary.

**This is tier B**, and it exists because tier A is all-or-nothing: a developer
role *does* get `Bash`, for tests and local commits, and inside that grant
`git push` has to be stopped on its own. So the guard reads the command the
model is about to run and answers on it.

Two properties, both deliberate, and stating them plainly is the point:

**It matches on a string, and a string can be rewritten.** `git push`,
`git\\u00a0push`, `eval "$(echo Z2l0IHB1c2g= | base64 -d)"` — the first is
caught, the last is not. This stops the ordinary attempt and the honest
mistake, which together are nearly all of them. It is not a sandbox, and
documenting it as one would be the actual danger.

**It fails open by default, and says so out loud.** A guard that fails closed
turns a missing runtime into a session where nothing works; a guard that fails
open turns it into a session with one layer fewer. Which is right depends on
the installation, so it is `guard.fails` in the policy — and either way the
reason goes to stderr rather than being swallowed, because a guard that is
silently absent is worse than one that is absent.

The ledger is the other half: every tool call the guard saw, appended to the
run's own event file. Not to enforce anything — to answer "what did it actually
do" afterwards, which no amount of reading a transcript reliably answers.
"""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

#: The host's own vocabulary, read out of the executable rather than assumed:
#: allow · deny · ask · defer, and `defer` is print-mode only.
DECISIONS = ("allow", "deny", "ask", "defer")

#: Tools whose input carries a command string. Everything else is not this
#: guard's business — the allowlist already decided whether the role has it.
COMMAND_TOOLS = ("Bash", "BashOutput")


@dataclass(frozen=True)
class Verdict:
    decision: str              # one of DECISIONS
    reason: str = ""
    action: str = ""           # the policy action, when one was matched

    def as_hook_output(self) -> dict:
        """Exactly the shape the host reads. Anything else is ignored."""
        body = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": self.decision}}
        if self.reason:
            body["hookSpecificOutput"]["permissionDecisionReason"] = self.reason
        return body


def command_of(payload: dict) -> str:
    """The command a tool call is about to run, or "" if it runs none."""
    if str(payload.get("tool_name", "")) not in COMMAND_TOOLS:
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command", ""))


def split_commands(command: str) -> list[str]:
    """One shell line can be several commands. Judge each on its own.

    `npm test && git push` is one string and two intentions, and a guard that
    looks at the whole string sees a test run. Splitting is on the shell's own
    separators; it is not a parser and does not pretend to be one — see the
    module docstring about what this layer is.
    """
    parts: list[str] = []
    current: list[str] = []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [command]
    for token in tokens:
        if token in ("&&", "||", ";", "|", "&"):
            if current:
                parts.append(" ".join(current))
                current = []
        else:
            current.append(token)
    if current:
        parts.append(" ".join(current))
    return parts or [command]


def in_managed_run() -> bool:
    """Is this session one the launcher started?

    Only the launcher sets `SKY_LAUNCHED`, and it is deliberately not in the
    hand's allowlist of inherited variables, so a session cannot acquire it by
    accident.
    """
    return os.environ.get("SKY_LAUNCHED") == "1"


def decide(payload: dict, policy) -> Verdict:
    """What to tell the host about this tool call.

    **Only inside a run the launcher started.** The plugin's hook fires in
    every session that has the plugin enabled, including the one a person
    opened themselves to do their own work — and denying `git push` there is
    both wrong and infuriating: it is their repository, their credentials, and
    the host's own permission prompt is the right control. The design says
    interactive sessions use the host's permissions; this now matches it.

    A denial names the policy action and the reason the policy gives, not a
    generic refusal: the person reading it needs to know what to do instead,
    and `/sky:ship` is usually the answer.
    """
    command = command_of(payload)
    if not command:
        return Verdict("allow")
    if not in_managed_run():
        # No reason string: the host shows it to the user, and "SKY stood
        # aside" on every command in an ordinary session is noise.
        return Verdict("allow")
    if policy is None:
        return Verdict("allow", "no policy was loaded, so the guard stood aside")

    for piece in split_commands(command):
        found = policy.denied_command(piece)
        if found is not None:
            return Verdict("deny",
                           f"{found.why}. [policy: {found.action}]",
                           found.action)
    return Verdict("allow")


# ── the ledger ───────────────────────────────────────────────────────────
def ledger_path() -> Path | None:
    """The run's own event file, when this session belongs to a run.

    None outside a run — an interactive session the user started themselves is
    not something this writes a ledger for, and inventing a file somewhere is
    how a tool ends up littering a home directory.
    """
    directory = os.environ.get("SKY_RUN_DIR", "")
    return Path(directory) / "tools.jsonl" if directory else None


def record(payload: dict, verdict: Verdict | None = None) -> Path | None:
    """Append one line for a tool call. Never raises: a ledger that can break
    a run is a ledger someone turns off."""
    path = ledger_path()
    if path is None:
        return None
    line = {
        "tool": str(payload.get("tool_name", "")),
        "command": command_of(payload)[:2000] or None,
        "decision": verdict.decision if verdict else None,
        "action": verdict.action if verdict else None,
        "run_id": os.environ.get("SKY_RUN_ID") or None,
        "agent_id": os.environ.get("SKY_AGENT_ID") or None,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: v for k, v in line.items()
                                     if v is not None}) + "\n")
    except OSError:
        return None
    return path
