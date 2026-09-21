"""Starting a hand — and refusing to.

This is where *a brain with no Safety may answer and review, but may not build*
is applied. It cannot live anywhere else: the guard cannot enforce its own
presence, and a skill is text a model may skip — and a model that has lost its
guard is exactly the one that will. So the rule runs **before the model exists**,
in whatever starts it.

Four things happen, in this order, and the order is the design:

    1. resolve the KB
    2. check readiness for this kind of work, and REFUSE if it is not ready
    3. build the environment the hand gets — allowlisted variables only,
       plus git configured so the normal push paths fail
    4. prove step 3 rather than assume it — if the proof fails, nothing starts

Step 3 is a different kind of control from the rest: it removes the capability
rather than policing it. A hand started this way has no credential to push with.

**And the limit, because it is load-bearing.** The launcher and the hand run as
the same operating-system user, so a hand with a shell can read the token file,
edit the grant record, or reach around any of this. That makes it defence in
depth against mistakes, not containment of an adversary. It becomes a boundary
at harness step H10, and gate G25 is what proves it. Nothing here should be
described as more than it is.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .kbmap import KB
from .policy import Policy
from .readiness import Brain, Kind, Part

#: The only variables a hand inherits. Everything else in the parent's
#: environment — every other token, every other endpoint — stays behind.
ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL", "USER")

#: Variables whose VALUE is a secret. Named exactly, never matched by substring:
#: "PAT" is a substring of PATH, and a heuristic that redacts PATH while missing
#: a real token is worse than no heuristic at all.
SECRET_VARS = frozenset({"SKY_KB_PAT"})


def is_secret(name: str) -> bool:
    return name in SECRET_VARS


#: The tool allowlist used to live here, as a dict. It now comes from
#: `policy.yaml`, because the guard hook and the broker need the same answer and
#: two lists in two files is two policies — with the looser one winning on the
#: day they differ. `hand_command` takes a Policy and asks it.

#: Claude is asked for `stream-json`, not `json`, and the difference matters to
#: a watchdog. `json` is silent until the very end — one object when the run is
#: over — so a healthy forty-minute build would look exactly like a stuck hand
#: and the silence cap would kill it. `stream-json` emits a line per event, so
#: the cap keeps meaning "nothing happened", and the final line is the result
#: object `usage.py` reads for the bill.
#:
#: `--verbose` is not optional: in print mode the CLI refuses `stream-json`
#: without it ("--output-format=stream-json requires --verbose", Claude Code
#: 2.1.152). It was left out until a real run said so, rather than added on a
#: guess; the run said so on 2026-09-14.
HAND_COMMANDS = {
    "claude": ("claude", "-p", "--strict-mcp-config", "--verbose",
               "--output-format", "stream-json"),
    "codex": ("codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only"),
    "kimi": ("kimi", "-p"),
}

#: Which hand can actually enforce a role, and which roles it may therefore run.
#:
#: This is not a preference — it is what each product supports today. Only
#: Claude takes a named agent with a tool allowlist and a single MCP config, so
#: only Claude can hold a role to its boundary. Codex has an OS sandbox and no
#: role selection, which is enough for reading and not for a bounded build.
#: Kimi has neither: `kimi -p` auto-approves every tool call and has no sandbox.
#:
#: An earlier version built a command for any pair. That silently produced a
#: "reviewer" on Kimi with no role, no tool restriction and no KB confinement —
#: a full-power hand wearing the name of a read-only one, which is worse than
#: refusing. A review caught it.
HAND_ROLES = {
    "claude": frozenset({"developer", "reviewer", "architect", "security"}),
    # One read role, not three. The OS sandbox is Codex's only boundary and it
    # makes architect, reviewer and security *identical* — none of them can
    # write, and nothing stops the one asked for a review from doing an
    # architect's job or the reverse. Offering three was a label pretending to
    # be enforcement, which is the failure this file exists to avoid. Reviewer
    # is the narrowest remit of the three.
    "codex": frozenset({"reviewer"}),
    # Empty, and that is the finding rather than an omission: Kimi publishes
    # no way to set an MCP server for one run — only `~/.kimi-code/config.toml`,
    # which belongs to the person. A managed Kimi run would therefore read
    # whichever knowledge base their own configuration names, possibly another
    # tenant's, with core believing it had chosen. Refusing is the honest
    # answer until Kimi grows a per-run override.
    "kimi": frozenset(),
}

HAND_LIMITS = {
    "codex": ("Codex has no role selection, so its boundary is the OS sandbox alone. "
              "Read-only roles run under --sandbox read-only; a build needs a role "
              "the sandbox cannot express."),
    "kimi": ("`kimi -p` auto-approves every tool call and has no sandbox, so no role "
             "can be held to its boundary there. Not offered until that changes."),
}


def without_prompt(command: list[str], prompt: str) -> list[str]:
    """The command as it is safe to show and to record.

    The prompt is no longer the last argument — it sits before `--allowedTools`,
    which is variadic and would otherwise eat it. So "everything but the last
    element" is wrong twice over: it shows the prompt and it silently drops a
    tool from the record. This replaces the prompt wherever it actually is.
    """
    return ["<prompt>" if a == prompt and prompt else a for a in command]


class Refused(Exception):
    """The launcher declined to start. Always says which part is the problem."""


@dataclass
class HandEnv:
    """The environment a hand will be given, and the proof that it holds."""
    variables: dict[str, str]
    gitconfig: Path
    _tmp: tempfile.TemporaryDirectory | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def build_env(kb: KB, *, run_id: str, agent_id: str, role: str, task: str,
              directory: Path | None = None) -> HandEnv:
    """The environment, built from nothing rather than filtered from ours.

    Starting from an empty dict and adding is the only version that stays
    correct: a filter has to be updated every time someone adds a secret to
    their shell profile, and nobody will remember to.
    """
    tmp = tempfile.TemporaryDirectory(prefix="sky-hand-")
    gitconfig = Path(tmp.name) / "gitconfig"
    # An empty credential helper is not the same as no helper line: the empty
    # value RESETS the list, so a helper configured at system or global level
    # cannot contribute. GIT_CONFIG_NOSYSTEM then removes /etc entirely.
    gitconfig.write_text(
        "[credential]\n"
        "\thelper =\n"
        "[core]\n"
        "\taskpass =\n"
    )

    env: dict[str, str] = {k: os.environ[k] for k in ENV_ALLOWLIST if k in os.environ}
    env.update({
        "SKY_LAUNCHED": "1",
        "SKY_RUN_ID": run_id,
        # `SKY_AGENT_ID`, spelled exactly as `sky stamp` and the ledger read
        # it. It was `SKY_AGENT` here and `SKY_AGENT_ID` there, so every stamp
        # inside a real run came out blank and every ledger line lost its
        # agent — silently, because a missing variable reads as an empty
        # string. `SKY_AGENT` is still set, for anything that already used it.
        "SKY_AGENT_ID": agent_id,
        "SKY_AGENT": agent_id,
        "SKY_ROLE": role,
        "SKY_TASK": task,
        "SKY_KB_NAME": kb.name,
        "SKY_KB_URL": kb.url,
        "SKY_KB_PAT": kb.token(),
        # Every knowledge-base tool call requires the tenant as an argument —
        # it is not carried by the URL or the header. Without these two the
        # hand has a working connection and fails on its first call, which is
        # a confusing way to discover a missing variable.
        "SKY_TENANT": kb.tenant,
        "SKY_ONTOLOGY": kb.ontology,
        # Git, made unable to find a credential by any of its usual routes.
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": ("ssh -o BatchMode=yes -o IdentitiesOnly=yes "
                            "-o IdentityAgent=none -i /nonexistent"),
    })
    if directory is not None:
        # The ledger writes here. Without it the PostToolUse hook has nowhere
        # to put a line and silently records nothing — which looks exactly
        # like a run in which the hand called no tools.
        env["SKY_RUN_DIR"] = str(directory)

    if kb.code_url:
        env["SKY_CODE_URL"] = kb.code_url
    return HandEnv(variables=env, gitconfig=gitconfig, _tmp=tmp)


def prove_git_blocked(env: HandEnv, cwd: Path | None = None) -> tuple[bool, str]:
    """Confirm the block by recognising its own fingerprint — not by its silence.

    The first version of this asked git for a credential and passed whenever no
    password came back. That is the exact antipattern this codebase exists to
    avoid: git failing for ANY reason looked identical to git being blocked, so
    a broken git, a missing git, or an unrelated error all read as "safe". A
    review reproduced it with `exit 128` and an arbitrary message.

    So a pass now needs a positive observation. A correctly blocked git exits
    non-zero AND names the askpass program we pointed it at — that message only
    appears because our block worked. Anything else is unknown, and unknown is
    a refusal.

    The remote route is checked too when there is a remote, but only in one
    direction: a push that SUCCEEDS is an unambiguous failure, while a push that
    fails cannot be told apart from being offline, so it never counts as proof.
    """
    askpass = env.variables.get("GIT_ASKPASS", "")
    probe = "protocol=https\nhost=dev.azure.com\n\n"

    if shutil.which("git") is None:
        return False, ("git is not on PATH, so the block cannot be proven. "
                       "Refusing rather than assuming.")
    try:
        out = subprocess.run(
            ["git", "credential", "fill"],
            input=probe, capture_output=True, text=True, timeout=15,
            env=env.variables, cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        return False, ("git credential fill hung — something is still waiting for "
                       "input, so a prompt is reachable")
    except OSError as exc:
        return False, f"could not run git ({exc}); refusing rather than assuming"

    if "password=" in out.stdout:
        return False, ("git handed back a password inside the launched environment. "
                       "The block is not working; refusing to start.")

    blocked = out.returncode != 0 and askpass and askpass in out.stderr
    if not blocked:
        return False, (
            f"could not confirm the block: git exited {out.returncode} and the "
            f"askpass program was not named in its output. A pass needs the "
            f"block's own fingerprint, not merely the absence of a password. "
            f"stderr: {out.stderr.strip()[:120]!r}"
        )

    detail = "git refuses to produce a credential, and names the askpass block as why"
    remote = _remote_reachable_check(env, cwd)
    if remote is False:
        return False, ("a dry-run push SUCCEEDED inside the launched environment. "
                       "The block does not cover this remote; refusing to start.")
    if remote is True:
        detail += "; a dry-run push also fails"
    return True, detail


def _remote_reachable_check(env: HandEnv, cwd: Path | None) -> bool | None:
    """True if a push failed, False if one succeeded, None if there was nothing to try.

    Only the False case is trusted. A push that fails may simply be a machine
    with no network, and treating that as proof would be the same mistake all
    over again.
    """
    if cwd is None:
        return None
    try:
        has_remote = subprocess.run(["git", "remote"], capture_output=True, text=True,
                                    timeout=10, cwd=str(cwd), env=env.variables)
        if has_remote.returncode != 0 or not has_remote.stdout.strip():
            return None
        push = subprocess.run(["git", "push", "--dry-run"], capture_output=True,
                              text=True, timeout=25, cwd=str(cwd), env=env.variables)
        return push.returncode != 0
    except (subprocess.TimeoutExpired, OSError):
        return None


def check_readiness(brain: Brain, kind: Kind) -> None:
    """Refuse, naming the part to fix — never just 'not ready'."""
    blockers = brain.blockers(kind)
    if not blockers:
        return
    lines = [f"this brain is not ready for {kind.value}:"]
    for b in blockers:
        lines.append(f"    {b.part.value:<18} {b.state.value:<8} {b.detail}")
    ready = [k.value for k in brain.ready_kinds()]
    lines.append("")
    lines.append(f"    it IS ready for: {', '.join(ready) or 'nothing'}")
    if Part.SAFETY in [b.part for b in blockers]:
        lines.append(
            "\n    Safety is the blocking one. A brain that can act on the world "
            "without\n    anything telling it what it must not do is the "
            "configuration this refuses."
        )
    raise Refused("\n".join(lines))


def hand_command(hand: str, role: str, mcp_config: Path, prompt: str,
                 policy: "Policy") -> list[str]:
    """Build the command — or refuse the pair.

    A hand that cannot enforce the role is not given the role. Producing a
    command anyway would hand back something that answers to "reviewer" while
    being able to do anything.

    The tool list comes from the policy, never from here. **A policy is
    required to start anything at all**, including a read-only role: the tool
    allowlist *is* tier A, the strongest in-session control there is, so
    launching without one means launching a hand with whatever tools it happens
    to have. That is a larger hole than the missing-Safety case the readiness
    check already refuses.
    """
    if hand not in HAND_COMMANDS:
        raise Refused(f"unknown hand {hand!r}; have {', '.join(HAND_COMMANDS)}")
    if policy is None:
        raise Refused(
            "no policy, so no tool allowlist, so nothing to hold a role to.\n"
            "    The allowlist is the strongest in-session control there is; "
            "without it\n    a role name is a label and not a boundary.")
    if role not in policy.roles:
        raise Refused(f"unknown role {role!r}; policy has "
                      f"{', '.join(policy.roles_named())}")
    if role not in HAND_ROLES[hand]:
        allowed = ", ".join(sorted(HAND_ROLES[hand])) or "no roles at all"
        raise Refused(
            f"{hand} cannot run the {role} role.\n"
            f"    {HAND_LIMITS.get(hand, '')}\n"
            f"    On {hand} this supports: {allowed}.\n"
            f"    Claude supports all four."
        )
    tools = policy.tools_for(role)
    if not tools:
        raise Refused(f"the {role} role has no tools in the policy, so the host "
                      f"has nothing to enforce")
    cmd = list(HAND_COMMANDS[hand])
    if hand == "claude":
        # The prompt goes FIRST, before any option, because `--allowedTools`
        # takes `<tools...>` — a variadic list that consumes every following
        # token until the next `-`-prefixed one. With the prompt appended last
        # it was swallowed as one more tool name and the run died with "Input
        # must be provided either through stdin or as a prompt argument".
        # Nothing in the command's shape said so; a real run did.
        cmd.append(prompt)
        cmd += ["--mcp-config", str(mcp_config),
                "--agent", f"sky:{role}",
                "--allowedTools", ",".join(tools)]
        return cmd
    if hand == "codex":
        # Codex has no `--mcp-config`. It has `-c key=value`, which layers a
        # value over `~/.codex/config.toml` — verified against codex-cli
        # 0.149.0. Without these the managed run quietly used whatever the
        # person's own configuration pointed at, which may be another tenant
        # entirely: the isolation the launcher exists for, absent.
        server = _server_from(mcp_config)
        if not server:
            raise Refused(
                "the knowledge base could not be read back from "
                f"{mcp_config}, and a Codex run that cannot be given one would "
                "silently use your own configuration instead")
        cmd += ["-c", f"mcp_servers.kb.url={server['url']}",
                "-c", "mcp_servers.kb.bearer_token_env_var=SKY_KB_PAT",
                "--strict-config"]
        cmd.append(prompt)
        return cmd

    cmd.append(prompt)
    return cmd


def _server_from(mcp_config: Path) -> dict | None:
    """The `kb` server out of the per-run config core just wrote."""
    try:
        body = json.loads(Path(mcp_config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    server = (body.get("mcpServers") or {}).get("kb")
    return server if isinstance(server, dict) and server.get("url") else None


def write_mcp_config(env: HandEnv, kb: KB, directory: Path,
                     catalogue: KB | None = None) -> Path:
    """One KB, and only one. `--strict-mcp-config` then hides every other server.

    Without this the hand inherits every MCP server the user has configured —
    on this machine that is fourteen, including ones with write access
    elsewhere. The point of choosing a KB is lost if all of them are reachable.
    """
    import json
    servers = {"kb": {"type": "http", "url": kb.url,
                      "headers": {"Authorization": f"Bearer {kb.token()}"}}}
    if kb.code_url:
        servers["code"] = {"type": "http", "url": kb.code_url,
                           "headers": {"Authorization": f"Bearer {kb.token()}"}}
    # The shared skill catalogue, reached ALONGSIDE the task KB. It is a third
    # server rather than a second task KB precisely so the two cannot be
    # confused: `resolve` never returns it, and the only tools a role holds for
    # it are reads. A catalogue is optional — a machine without one simply has
    # no skill discovery, and everything else works.
    if catalogue is not None and catalogue.name != kb.name:
        servers["catalogue"] = {"type": "http", "url": catalogue.url,
                                "headers": {"Authorization": f"Bearer {catalogue.token()}"}}
    path = directory / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}, indent=2))
    path.chmod(0o600)
    return path
