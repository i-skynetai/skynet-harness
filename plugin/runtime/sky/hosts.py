"""The same content, packaged for a coding agent that is not Claude (H6).

Claude's packaging *is* the plugin. Codex and Kimi each want their own layout,
and everything host-specific lives here so adding a third does not touch
`core/` or `plugin/`.

**What each host can actually enforce, measured rather than assumed** — from
`codex --help` and `kimi --help` on the versions named in `SUPPORTED`:

===== ================================ ==================================
host   the mechanism it really has      what that buys
===== ================================ ==================================
codex  `--profile <name>` layering a    an OS sandbox, and per-run config
       `$CODEX_HOME/<name>.config.toml` overrides. **No named agent, so no
       on the base config; `--sandbox`  per-role tool allowlist.**
kimi   `--skills-dir <dir>`, and        the skills load. **No role
       `~/.kimi-code/config.toml`       selection and no tool allowlist.**
===== ================================ ==================================

That table is the whole reason the roles are not offered everywhere. Only
Claude takes a named agent with a tool allowlist, which is tier A — the one
layer that is a boundary. On Codex, `--sandbox read-only` is a real boundary
for *reading* roles and nothing at all for a build. On Kimi there is no
enforcement beyond prose.

So the packages generated here are honest about their own limits: each one
ships the rules, and each one says in its first paragraph which of them the
host can hold the agent to. **A package that implied otherwise would be worse
than no package**, because someone would run a build on it.
"""
from __future__ import annotations

import json

from dataclasses import dataclass
from pathlib import Path

#: Versions these packages were written against. Printed into the package, so
#: a mismatch later is visible rather than mysterious.
SUPPORTED = {"codex": "codex-cli 0.149.0", "kimi": "0.20.0"}

#: What each host can enforce. `roles` is what it may therefore be asked to do.
CAN_ENFORCE = {
    "codex": ("an operating-system sandbox (`--sandbox read-only`), and "
              "per-run configuration overrides — but nothing that tells one "
              "read role from another",
              ("reviewer",)),
    "kimi": ("nothing beyond the prose in these files — there is no role "
             "selection and no tool allowlist",
             ("reviewer",)),
}


#: What every generated configuration says about itself, and the record of
#: everything one run wrote — the two ways a file proves it is ours.
MARKER = "Written by `sky host"
MANIFEST = ".sky-host-manifest.json"


class HostError(Exception):
    """A host this does not package, or a target it will not write to."""


@dataclass(frozen=True)
class Package:
    host: str
    files: dict[str, str]

    def write(self, into: Path) -> list[Path]:
        """Write the package — and never over a file that is not ours.

        `~/.codex/AGENTS.md` and `~/.kimi-code/config.toml` are exactly the
        files a person already has, and the first version of this replaced
        them without a word. The same rule as the launcher: a file may be
        replaced if it does not exist, if it says `sky host` wrote it, or if a
        manifest from an earlier run lists it. Anything else is refused BEFORE
        anything is written, so a refusal leaves the directory as it was.
        """
        import os
        into = Path(into).expanduser()
        manifest = into / MANIFEST
        ours = set()
        if manifest.is_file():
            try:
                ours = set(json.loads(manifest.read_text(encoding="utf-8")))
            except ValueError:
                ours = set()
        theirs = []
        for name in sorted(self.files):
            path = into / name
            if not path.exists() or name in ours:
                continue
            try:
                if MARKER in path.read_text(encoding="utf-8", errors="replace"):
                    continue
            except OSError:
                pass
            theirs.append(str(path))
        if theirs:
            raise HostError(
                "these files already exist and were not written by `sky host`, "
                "so they are not ours to replace: " + ", ".join(theirs)
                + ". Nothing was written. Move them aside, or pass a different "
                "--into directory.")
        written = []
        for name, body in sorted(self.files.items()):
            path = into / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            if name.startswith("bin/") or "/scripts/" in name \
                    or name.startswith("scripts/"):
                os.chmod(path, 0o755)     # a wrapper nobody can run is no wrapper
            written.append(path)
        manifest.write_text(json.dumps(sorted(self.files)) + "\n", encoding="utf-8")
        return written


def _preamble(host: str, policy) -> str:
    enforces, roles = CAN_ENFORCE[host]
    denied = ", ".join(sorted(n for n, s in policy.actions.items()
                              if getattr(s, "never", ""))) if policy else "see policy.yaml"
    return f"""# SKY on {host}

**Written against {SUPPORTED[host]}.** If your version differs, check that the
options named here still exist before relying on them.

## What this host can hold you to

{host} enforces {enforces}.

Everything else in these files is **prose**, and prose works because you are
cooperative. Claude is the only host that takes a named agent with a tool
allowlist, which is the one layer that is a boundary rather than a request.

**Roles you may be asked to run here: {', '.join(roles)}.** Not because the
others are unimportant, but because this host cannot keep them inside their
limits, and a role that is not enforced is a label.

## Denied to everyone, on every host

{denied}

An agent that can widen its own permission has none. If one of these looks
necessary, stop and say so — do not find another way to do it.
"""


def _roles_section(policy) -> str:
    if policy is None:
        return "\n(No policy was available when this package was generated.)\n"
    out = ["\n## The roles\n"]
    for name in sorted(policy.roles):
        role = policy.roles[name]
        may = ", ".join(sorted(role.get("may") or ())) or "nothing"
        human = ", ".join(sorted(role.get("needs_human") or ())) or "nothing"
        out.append(f"### {name}\n\n{role.get('purpose', '')}\n\n"
                   f"- **may**: {may}\n"
                   f"- **needs a person**: {human}\n")
    return "\n".join(out)


def codex(policy, kb_url: str = "${SKY_KB_URL}",
          pat_var: str = "SKY_KB_PAT") -> Package:
    """A Codex profile plus the rules, as `$CODEX_HOME` content.

    `--profile <name>` layers `<name>.config.toml` over the user's own config,
    which is the only mechanism Codex has for shipping settings without
    rewriting a file that belongs to the person.
    """
    config = f"""# SKY profile for Codex — layer it with:  codex exec --profile sky
#
# Written by `sky host codex`. This file is a LAYER: it is applied on top of
# your own ~/.codex/config.toml and does not replace it.

# Read-only is the default here on purpose. Codex has no per-role tool
# allowlist, so the sandbox is the only real boundary this host offers, and a
# writable default would make every role look like a developer.
sandbox = "read-only"

[mcp_servers.kb]
url = "{kb_url}"
bearer_token_env_var = "{pat_var}"

# The knowledge base is reached with YOUR token. Every ingest and every search
# is recorded against you, which is the intended behaviour and the reason a
# shared token is never used.
"""
    agents = (_preamble("codex", policy) + _roles_section(policy) + """
## Working here

1. Read `CONFIG.md` before touching the knowledge base: the tenant, the
   ontology and the ticket pattern are configuration, not facts, and the tool
   names depend on how this session started.
2. The knowledge-base tools arrive as `mcp__kb__*` — Codex names the server
   from the config above.
3. Outward actions — push, pull request, ticket comment or transition — are
   **rendered, never run**. Produce the exact command and stop.
4. Every artifact carries the stamp from `sky stamp --json`. Do not compose it.

## What the sandbox does and does not do

`--sandbox read-only` stops writes to the filesystem. It does not stop a
network call, it does not know what a knowledge base is, and it has no idea
which role you were asked to play. It is a good boundary for reading and not a
substitute for one when building.
""")
    return Package("codex", {"sky.config.toml": config, "AGENTS.md": agents,
                             "bin/sky-codex": _wrapper("codex", pat_var)})


def kimi(policy, kb_url: str = "${SKY_KB_URL}",
         pat_var: str = "SKY_KB_PAT") -> Package:
    """Kimi loads skills from a directory; the rules travel beside them."""
    config = f"""# SKY settings for Kimi — merge into ~/.kimi-code/config.toml
#
# Written by `sky host kimi`. Kimi has no role selection and no tool
# allowlist, so this configures reach and nothing else. Run skills with:
#
#     kimi --skills-dir <this directory>/skills -p '<the ask>'

[mcp_servers.kb]
url = "{kb_url}"
bearer_token_env_var = "{pat_var}"
"""
    rules = (_preamble("kimi", policy) + _roles_section(policy) + """
## Working here

Read-only work only. This host cannot stop you editing a file, which is exactly
why you are asked not to: the limit is yours to keep, and there is no second
layer behind it.

1. `CONFIG.md` first — the tenant, the ontology and the ticket pattern are
   configuration.
2. Never push, open a pull request, comment on a ticket or transition one.
   Render the command and stop.
3. Never write to the knowledge base without a person saying yes to that exact
   document.
4. If a task needs edits, say that this host is not the right one for it rather
   than doing it carefully.
""")
    return Package("kimi", {"config.toml": config, "RULES.md": rules,
                            "bin/sky-kimi": _wrapper("kimi", pat_var)})


BUILDERS = {"codex": codex, "kimi": kimi}


def _wrapper(host: str, pat_var: str) -> str:
    """Start the host with the token loaded from SKY's own 0600 file.

    The generated configuration names an environment variable; nothing was
    putting the value into it, so the package was configured and unable to
    authenticate. This reads the one token file — it is not exported into the
    shell, so it lives only as long as the command.
    """
    run = {"codex": 'exec "$@"', "kimi": '"$@"'}[host]
    return f"""#!/bin/sh
# Start {host} with the knowledge-base token from SKY's own file.
# Written by `sky host {host}`. The token is never echoed and never exported
# beyond this command.
ENV_FILE="${{SKY_CONFIG_DIR:-$HOME/.config/sky}}/env"
if [ ! -r "$ENV_FILE" ]; then
    echo "sky-{host}: no token file at $ENV_FILE - run 'sky setup init' first" >&2
    exit 1
fi
VALUE=$(sed -n "s/^{pat_var}=//p" "$ENV_FILE" | head -n 1)
if [ -z "$VALUE" ]; then
    echo "sky-{host}: {pat_var} is not in $ENV_FILE" >&2
    exit 1
fi
SKY_KB_PAT="$VALUE" {pat_var}="$VALUE" exec {host} {run}
"""


def skills_dir() -> Path | None:
    """Where the shipped skills are, whichever way this was installed."""
    import os
    root = os.environ.get("SKY_PLUGIN_ROOT", "")
    if root and (Path(root) / "skills").is_dir():
        return Path(root) / "skills"
    # The repository this runtime is running out of comes BEFORE any installed
    # copy: running `sky host` from a checkout should package that checkout,
    # not whatever older version happens to be installed on the machine.
    here = Path(__file__).resolve().parents[2] / "plugin" / "skills"
    if here.is_dir():
        return here
    cached = sorted(Path("~/.claude/plugins/cache/sky/sky").expanduser().glob("*"))
    for candidate in reversed(cached):
        if (candidate / "skills").is_dir():
            return candidate / "skills"
    return None


def build(host: str, policy, *, profile=None) -> Package:
    if host == "claude":
        raise HostError(
            "Claude's packaging is the plugin itself — install it with "
            "`claude plugin install sky@sky`, not with this command.")
    try:
        builder = BUILDERS[host]
    except KeyError:
        raise HostError(f"no package for {host!r}; have "
                        f"{', '.join(sorted(BUILDERS))}") from None
    if profile is None:
        profile = _default_profile()
    if profile is None:
        # A configuration whose URL is the literal `${SKY_KB_URL}` is not a
        # configuration: neither Codex nor Kimi expands it, so the package
        # installs perfectly and reaches nothing. Better to refuse and say what
        # is needed than to hand over a file that looks finished.
        raise HostError(
            "no knowledge base to point this package at. Pass --profile with "
            "the JSON your administrator sent you, or run `sky setup init` "
            "first so there is a default in the map — a package with an "
            "unfilled address reaches nothing and looks fine.")
    package = builder(policy, kb_url=profile.url,
                      pat_var=_token_variable(profile.instance))

    # The skills, as files. A package of rules with no skills in it is a
    # package that cannot do anything: `--skills-dir` and `AGENTS.md` both
    # point at procedures, and shipping the pointer without the procedure is
    # the same "documented, not built" mistake in another shape.
    source = skills_dir()
    files = dict(package.files)
    if source is not None:
        for skill in sorted(source.glob("*/SKILL.md")):
            files[f"skills/{skill.parent.name}/SKILL.md"] = _for_host(
                skill.read_text(encoding="utf-8"), host)
        for name in ("CONFIG.md", "policy.md", "identity.md", "SKILLS.md"):
            beside = source.parent / name
            if beside.is_file():
                files[f"skills/{name}"] = _for_host(
                    beside.read_text(encoding="utf-8"), host)
        # The templates four skills tell the agent to fill in. A package that
        # names a file it does not contain sends the agent to invent the shape
        # of a solution design, which is the opposite of why templates exist.
        for template in sorted((source.parent / "templates").glob("*.md")):
            files[f"templates/{template.name}"] = template.read_text(
                encoding="utf-8")
        # Saved scripts, shared and skill-owned. A package that ships the
        # procedure and not the code it runs sends the agent to re-derive it —
        # which is the whole thing `SKILLS.md` rule 1 exists to stop.
        for script in sorted((source.parent / "scripts").glob("*")):
            if script.is_file():
                files[f"scripts/{script.name}"] = script.read_text(
                    encoding="utf-8")
        for script in sorted(source.glob("*/scripts/*")):
            if script.is_file():
                files[f"skills/{script.parent.parent.name}/scripts/"
                      f"{script.name}"] = script.read_text(encoding="utf-8")
    return Package(host, files)


def _for_host(text: str, host: str) -> str:
    """Take Claude's vocabulary out of a skill before another host reads it.

    `${CLAUDE_PLUGIN_ROOT}` means nothing to Codex or Kimi, and a step that
    tells an agent to read a path that does not exist is a step it either skips
    or invents its own answer to. Same for the two tool spellings: outside
    Claude there is one server, named `kb`.
    """
    text = text.replace("${CLAUDE_PLUGIN_ROOT}/", "")
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", ".")
    text = text.replace("`mcp__plugin_sky_kb__…`", "`mcp__kb__…`")
    text = text.replace("`mcp__kb__…` or\n> `mcp__plugin_sky_kb__…`", "`mcp__kb__…`")
    return text


def _default_profile():
    """The default knowledge base from this machine's map, if there is one."""
    try:
        from .kbmap import KBMap
        from .setup import Profile
        kbs = KBMap.load()
    except Exception:
        return None
    for kb in kbs:
        if kb.default and not kb.is_catalogue:
            return Profile(name=kb.name, url=kb.url, tenant=kb.tenant,
                           ontology=kb.ontology,
                           instance=(kb.pat_env or "SKY_PAT_DEFAULT")
                           .removeprefix("SKY_PAT_").lower(),
                           privacy=kb.privacy, code_url=kb.code_url)
    return None


def _token_variable(instance: str) -> str:
    """The same rule `sky setup` uses: one token per instance."""
    import re as _re
    cleaned = _re.sub(r"[^A-Za-z0-9]+", "_", instance).strip("_").upper()
    return f"SKY_PAT_{cleaned}" if cleaned else "SKY_KB_PAT"
