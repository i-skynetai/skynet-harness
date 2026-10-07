"""One answer to "may this role do that?".

The launcher asks before a hand starts. The guard hook asks during the run. The
broker will ask before an outward action. If each of them held its own list they
would drift, and the day they disagree is the day the weakest one is the real
policy. So all three read `policy.yaml` through this module.

Three rules the evaluator applies, in this order, and each is tested by removing
it and watching something fail:

**Default deny.** An action a role does not list is denied. An action that is
not in the file at all is denied too — an unknown action is not a harmless one,
and a typo in a skill must not become an allowance.

**Outward actions are never plainly allowed.** Anything that changes what other
people can see is `needs_human` or goes to the broker, whatever the file says.
`lint` refuses a policy that grants one directly, so this cannot be edited away
without the lint failing first.

**`never` beats everything.** An action marked `never` in the file is refused
for every role, even one that lists it. That is the line the file itself cannot
cross.

**And the limit.** This module decides; it does not enforce. Tier A — the host's
tool allowlist — is the only in-session control that a model cannot talk its way
past, and it is enforced by the coding agent, not here. Tier B, the guard, sees
a command string it can be fooled about. What this module guarantees is that all
of them are working from the same rules, not that the rules cannot be evaded.
"""
from __future__ import annotations

import os
import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from . import yamlish

#: Where the policy lives when nobody says otherwise. Core never imports from
#: `plugin/` — it reads a data file whose location is configuration, the same
#: way it reads `kb-map.json`.
#:
#: The first is what `sky setup` writes (H2). The second is the installed
#: plugin: gate G11 established the cache shape as
#: `cache/<marketplace>/<plugin>/<version>/`, and **several versions sit side by
#: side** — four of one plugin on this machine — so the version cannot be
#: written down here and the newest has to be found.
CONFIG_POLICY = "~/.config/sky/policy.yaml"
PLUGIN_CACHE = "~/.claude/plugins/cache"
PLUGIN_NAMES = ("skynet-harness", "sky")

#: Last, the copy this repository ships in `plugin/policy.yaml`. It is the lowest
#: priority on purpose: an installed policy is the one actually governing runs on that
#: machine, and a checkout sitting on disk must never quietly override it. But when
#: nothing is installed and nothing is configured — which is every fresh clone — the
#: file is right there, and refusing to read it taught a first-time reader that the
#: tool is broken rather than that it is unconfigured.
DEFAULT_LOCATIONS = (CONFIG_POLICY,
                     f"{PLUGIN_CACHE}/<marketplace>/<plugin>/<version>/policy.yaml",
                     "plugin/policy.yaml, beside a checkout of this repository")


def _version_key(name: str) -> tuple:
    """Order versions numerically. String order puts 0.10.0 below 0.9.0."""
    parts = []
    for piece in name.split("."):
        parts.append((0, int(piece)) if piece.isdigit() else (1, 0, piece))
    return tuple(parts)


def _repo_policy() -> Path | None:
    """`plugin/policy.yaml` in the checkout this runtime is running from.

    Resolved by walking up from this file, not from the working directory: `sky` is run
    from wherever the person happens to be standing, and the answer must not depend on
    that. Walking rather than counting parents because this module is vendored into
    `plugin/runtime/sky/` as well, and a fixed depth would be right in one copy and
    wrong in the other — the kind of difference that shows up only in the copy nobody
    tested.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "plugin" / "policy.yaml"
        if candidate.is_file():
            return candidate
    return None


def _installed_policy() -> Path | None:
    """The newest installed plugin's policy, if the plugin is installed."""
    cache = Path(os.path.expanduser(PLUGIN_CACHE))
    if not cache.is_dir():
        return None
    found: list[tuple[tuple, Path]] = []
    for marketplace in cache.iterdir():
        for plugin in (marketplace.iterdir() if marketplace.is_dir() else ()):
            if plugin.name not in PLUGIN_NAMES:
                continue
            for version in (plugin.iterdir() if plugin.is_dir() else ()):
                candidate = version / "policy.yaml"
                if candidate.is_file():
                    found.append((_version_key(version.name), candidate))
    if not found:
        return None
    return max(found)[1]

ALLOW = "allow"
NEEDS_HUMAN = "needs-human"
DENY = "deny"


class PolicyError(Exception):
    """The file is missing, unreadable, or says something contradictory."""


@dataclass(frozen=True)
class Decision:
    outcome: str              # allow · needs-human · deny
    action: str
    role: str
    why: str
    broker: str = ""          # the narrow operation that can carry it, if any

    @property
    def allowed(self) -> bool:
        """True only for a plain allow. `needs-human` is not permission."""
        return self.outcome == ALLOW

    def __str__(self) -> str:
        return f"{self.role} · {self.action}: {self.outcome} — {self.why}"


@dataclass(frozen=True)
class Action:
    name: str
    outward: bool
    description: str
    broker: str = ""
    never: str = ""


#: git's global options that take the next word as their value
#: (`git -C . push`). Skipped so the guard sees `git push`.
_GIT_GLOBALS_WITH_VALUE = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                           "--exec-path", "--config-env", "--super-prefix")
#: git's global options that stand alone.
_GIT_GLOBALS_ALONE = ("-p", "-P", "--paginate", "--no-pager", "--bare",
                      "--no-replace-objects", "--literal-pathspecs",
                      "--glob-pathspecs", "--noglob-pathspecs",
                      "--icase-pathspecs", "--no-optional-locks")


def _without_git_globals(command: str) -> str:
    """`git -C . -c a=b push` as `git push`, so a deny pattern still matches.

    Split into words first, so an option is skipped only where git would read
    it as one: after the word `git` and before the subcommand. This is still
    the string guard (tier B), not a shell parser.
    """
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    out: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        out.append(word)
        i += 1
        if word != "git" and not word.endswith("/git"):
            continue
        out[-1] = "git"
        while i < len(words):
            option = words[i]
            if option in _GIT_GLOBALS_WITH_VALUE:
                i += 2
            elif (option.startswith(tuple(f"{o}=" for o in _GIT_GLOBALS_WITH_VALUE))
                  or option in _GIT_GLOBALS_ALONE
                  or (option.startswith(("-C", "-c")) and len(option) > 2)):
                i += 1
            else:
                break
    return " ".join(out)


@dataclass
class Policy:
    version: int
    actions: dict[str, Action]
    roles: dict[str, dict]
    guard: dict
    ingest: dict
    tickets: dict
    tool_groups: dict[str, tuple[str, ...]] = None       # type: ignore[assignment]
    path: Path | None = None
    bindings: dict = None       # type: ignore[assignment]
    skills: dict = None         # type: ignore[assignment]
    body: dict = None           # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.tool_groups is None:
            self.tool_groups = {}
        if self.bindings is None:
            self.bindings = {}
        if self.skills is None:
            self.skills = {}

    # ── loading ──────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Policy":
        # Preserve find()->Path and the single-file development override API.
        # Partial org/project patches are composed before from_dict sees them.
        from . import project
        explicit = path or project.explicit_override()
        if explicit is None:
            effective = project.resolve(Path.cwd())
            if effective is not None:
                return effective
        found = Path(path).expanduser() if path else cls.find()
        if found is None:
            raise PolicyError(
                "no policy.yaml found.\n"
                "    Looked in: " + ", ".join(DEFAULT_LOCATIONS) + "\n"
                "    Without it there is no Safety, and a brain with no Safety "
                "may answer and review but may not build.")
        try:
            body = yamlish.parse(found.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PolicyError(f"cannot read {found}: {exc}") from exc
        except yamlish.YamlishError as exc:
            raise PolicyError(f"{found}: {exc}") from exc
        loaded = cls.from_dict(body, path=found)
        loaded.notice = "explicit policy: layers ignored" if explicit is not None else ""
        return loaded

    @classmethod
    def find(cls) -> Path | None:
        override = os.environ.get("SKY_POLICY")
        if override:
            candidate = Path(override).expanduser()
            return candidate if candidate.is_file() else None
        configured = Path(os.path.expanduser(CONFIG_POLICY))
        if configured.is_file():
            return configured
        # The plugin's own `bin/sky` sets this. Without it, a runtime running
        # from inside a plugin could not find the policy sitting beside it, so
        # the guard stood aside in the one installation that ships both.
        root = os.environ.get("SKY_PLUGIN_ROOT", "")
        if root:
            beside = Path(root) / "policy.yaml"
            if beside.is_file():
                return beside
        return _installed_policy() or _repo_policy()

    @classmethod
    def from_dict(cls, body, *, path: Path | None = None) -> "Policy":
        if not isinstance(body, dict):
            raise PolicyError("a policy file must be a mapping at the top level")
        actions: dict[str, Action] = {}
        raw_actions = body.get("actions") or {}
        if not isinstance(raw_actions, dict):
            raise PolicyError("`actions:` must be a mapping of name to definition")
        for name, spec in raw_actions.items():
            if not isinstance(spec, dict):
                raise PolicyError(f"action {name!r} must be a mapping")
            actions[name] = Action(
                name=name,
                outward=bool(spec.get("outward")),
                description=str(spec.get("description") or ""),
                broker=str(spec.get("broker") or ""),
                never=str(spec.get("never") or ""),
            )
        roles = body.get("roles") or {}
        if not isinstance(roles, dict):
            raise PolicyError("`roles:` must be a mapping of role to definition")
        raw_groups = body.get("tool_groups") or {}
        if not isinstance(raw_groups, dict):
            raise PolicyError("`tool_groups:` must be a mapping of name to tools")
        for name, tools in raw_groups.items():
            if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
                raise PolicyError(f"tool group {name!r}: tools must be a list of strings")
        groups = {name: tuple(tools) for name, tools in raw_groups.items()}
        bindings = body.get("tools", {})
        skills = body.get("skills", {})
        if not isinstance(bindings, dict) or not isinstance(skills, dict):
            raise PolicyError("`tools:` and `skills:` must be mappings")
        raw_version = body.get("version")
        if not isinstance(raw_version, int) or isinstance(raw_version, bool):
            raise PolicyError(
                f"`version:` must be a whole number, got {raw_version!r}")
        policy = cls(
            version=raw_version,
            actions=actions,
            roles=roles,
            guard=body.get("guard") or {},
            ingest=body.get("ingest") or {},
            tickets=body.get("tickets") or {},
            tool_groups=groups,
            path=path,
            bindings=bindings,
            skills=skills,
            body=body,
        )
        problems = policy.lint()
        if problems:
            # A policy that fails its own lint is not loaded at all. Loading it
            # "mostly" is how a file with one broken rule keeps being used.
            raise PolicyError(
                f"{path or 'policy'} does not hold together:\n"
                + "\n".join(f"    {p}" for p in problems))
        return policy

    # ── the decision ─────────────────────────────────────────────────────
    def decide(self, role: str, action: str) -> Decision:
        """May this role do this? The only place that question is answered."""
        if role not in self.roles:
            return Decision(DENY, action, role,
                            f"{role!r} is not a role in this policy. "
                            f"Roles: {', '.join(sorted(self.roles))}")
        spec = self.actions.get(action)
        if spec is None:
            # An unknown action is denied, not assumed harmless. A typo in a
            # skill would otherwise become an allowance.
            return Decision(DENY, action, role,
                            f"{action!r} is not an action this policy defines, "
                            f"so it is denied")
        if spec.never:
            # The file cannot grant this to anyone, including a role that lists
            # it. `lint` also refuses such a file, so this is belt and braces.
            return Decision(DENY, action, role, spec.never)

        may = set(self.roles[role].get("may") or ())
        needs = set(self.roles[role].get("needs_human") or ())
        if action in needs:
            return Decision(NEEDS_HUMAN, action, role,
                            "prepared by the agent, performed by you",
                            broker=spec.broker)
        if action in may:
            if spec.outward:
                # Belt and braces again: lint refuses this file, and if one
                # somehow loads, the outward action still does not pass.
                return Decision(NEEDS_HUMAN, action, role,
                                "this changes what other people can see, so it "
                                "is never a plain allow", broker=spec.broker)
            return Decision(ALLOW, action, role, spec.description or "allowed")
        return Decision(DENY, action, role,
                        f"the {role} role does not have {action!r}")

    # ── what the launcher needs ──────────────────────────────────────────
    def tools_for(self, role: str) -> tuple[str, ...]:
        """The host-enforced allowlist — tier A — flat, with groups resolved.

        The launcher used to hold its own copy of this. Two lists of tool names
        in two files is two policies, and the looser one wins on the day they
        differ. The role agent files are held to this same list, so there is
        one allowlist and three readers of it.

        Order is preserved and duplicates are dropped: the list goes on a
        command line, and an allowlist that reads differently from the file it
        came from is one nobody can check by eye.
        """
        if role not in self.roles:
            raise PolicyError(f"{role!r} is not a role in this policy")
        spec = self.roles[role]
        if "tools" in spec:
            return self._resolve(spec.get("tools") or (), role)
        names = list(spec.get("base_tools") or ())
        for skill in self.skills_for(role):
            if skill not in self.skills:
                raise PolicyError(f"{role}: skill {skill!r} is not defined")
            names.extend(self.skills[skill].get("tools") or ())
        resolved = self._resolve(names, role)
        # Even a mutated Policy cannot expose an outward or never tool.
        tools = []
        for tool in resolved:
            action = self.actions.get(self.binding(tool))
            if action is not None and not action.outward and not action.never:
                tools.append(tool)
        return tuple(tools)

    def binding(self, tool: str) -> str | None:
        spec = self.bindings.get(tool)
        action = spec if isinstance(spec, str) else \
            (spec.get("action") if isinstance(spec, dict) else None)
        return action if isinstance(action, str) and action else None

    def skills_for(self, role: str) -> tuple[str, ...]:
        if role not in self.roles:
            raise PolicyError(f"{role!r} is not a role in this policy")
        return tuple(self.roles[role].get("skills") or ())

    def annotation_problems(self, inventory: dict | None = None) -> list[str]:
        """SH-067 hook for provider annotations; SH-064 validates reviewed_by.

        No annotation claims are made until inventory checking is implemented.
        Offline policy loading never needs a provider inventory.
        """
        return []

    @property
    def new_style(self) -> bool:
        return any("tools" not in spec for spec in self.roles.values())

    def digest(self) -> str:
        canonical = json.dumps(self.body, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _resolve(self, names, where: str) -> tuple[str, ...]:
        out: list[str] = []
        for name in names:
            if isinstance(name, str) and name.startswith("+"):
                group = name[1:]
                if group not in self.tool_groups:
                    raise PolicyError(
                        f"{where}: tool group {group!r} is not defined "
                        f"({', '.join(sorted(self.tool_groups)) or 'none are'})")
                members = self.tool_groups[group]
            else:
                members = (name,)
            for member in members:
                if member not in out:
                    out.append(member)
        return tuple(out)

    def roles_named(self) -> tuple[str, ...]:
        return tuple(sorted(self.roles))

    def ticket_prefix(self) -> str:
        return str(self.tickets.get("prefix") or "")

    # ── what the guard needs ─────────────────────────────────────────────
    def denied_command(self, command: str) -> Decision | None:
        """Whether the guard should stop this command. None means stand aside.

        Matching is on a normalised form — repeated whitespace collapsed — so
        `git   push` is the same as `git push`. That is the ordinary attempt.
        It is not a boundary: a command string can be rewritten, and this is
        written down as tier B for that reason.

        **The most specific pattern wins, not the first one listed.** With
        first-match, `git push --force` was reported as an ordinary push and
        `gh pr merge` as opening a pull request. Both were still denied, so
        nothing got through — but the recorded action and the reason given were
        both wrong, and a denial recorded as the wrong thing is what an audit
        later reads.
        """
        flat = " ".join(command.split())
        forms = {flat, _without_git_globals(flat)}
        best = None
        best_length = -1
        for rule in self.guard.get("deny_commands") or ():
            if not isinstance(rule, dict):
                continue
            pattern = " ".join(str(rule.get("pattern", "")).split())
            if (pattern and any(pattern in f for f in forms)
                    and len(pattern) > best_length):
                best, best_length = rule, len(pattern)
        if best is None:
            return None
        action = str(best.get("action") or "")
        spec = self.actions.get(action)
        return Decision(DENY, action or "shell.free", "guard",
                        str(best.get("reason") or "denied by policy"),
                        broker=spec.broker if spec else "")

    @property
    def guard_fails_closed_in_run(self) -> bool:
        """What the policy says the guard does when it cannot load the policy.

        Informational: with no policy loaded, the guard cannot read this field,
        so the behaviour is fixed in `guard.decide` and this states it.
        """
        return str(self.guard.get("fails") or "closed-in-run") == "closed-in-run"

    # ── the role agent files ─────────────────────────────────────────────
    def agent_tools_line(self, role: str) -> str:
        """The `tools:` line a role agent's front matter must carry."""
        return "tools: " + ", ".join(self.tools_for(role))

    def sync_agents(self, directory: Path, *, write: bool = True) -> list[str]:
        """Make each role agent's allowlist match this policy, or say it does not.

        The `tools:` line in an agent file **is** that agent's authority — what
        is not listed is not visible to it. That makes the line load-bearing and
        a typo in it silent, and it makes the file a second copy of something
        the policy already says.

        So it is generated from the policy rather than kept in step by hand,
        the same way the JSON Schema files are. `write=False` reports drift
        without changing anything, which is what the test uses.

        Returns the roles that changed (or would change). An empty list means
        the files already agree with the policy.
        """
        replacements, problems = self._agent_replacements(Path(directory))
        if problems:
            if write:
                raise PolicyError("agent render refused before writing:\n" + "\n".join(problems))
            return problems + [role for role, _, _, _ in replacements]
        if write:
            structural = self.lint()
            if structural:
                raise PolicyError("\n".join(structural))
            for _, path, _, replaced in replacements:
                path.write_bytes(replaced.encode("utf-8"))
        return [role for role, _, _, _ in replacements]

    def _agent_replacements(self, directory: Path) -> tuple[list, list[str]]:
        """Preflight all targets before a render writes any of them."""
        replacements, problems = [], []
        for role in self.roles_named():
            path = directory / f"{role}.md"
            try:
                text = path.read_bytes().decode("utf-8")
                lines = text.splitlines(keepends=True)
                if not lines or lines[0].strip() != "---":
                    raise ValueError("missing opening frontmatter delimiter")
                end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
                # Claude agent headers use rest-of-line description scalars,
                # including VERDICT: APPROVED. Policy YAML's colon rules must
                # not reject or rewrite that host format. Only tools values
                # are interpreted; every other field is preserved verbatim.
                header, field = {}, ""
                for line in lines[1:end]:
                    raw = line.rstrip("\r\n")
                    if not raw.strip() or raw.startswith("#"):
                        continue
                    if raw.startswith((" ", "- ")) and field == "tools":
                        header[field] += "\n" + raw
                        continue
                    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)", raw)
                    if not match:
                        raise ValueError("unparsable frontmatter line")
                    field, value = match.groups()
                    if field in header:
                        raise ValueError(f"duplicate frontmatter field {field!r}")
                    header[field] = value
                if header.get("name") != role:
                    raise ValueError(f"frontmatter name must be {role!r}")
                if "tools" not in header:
                    raise ValueError("missing frontmatter tools: line")
                value = yamlish.parse("tools: " + header["tools"])["tools"]
                tools = [t.strip() for t in value.split(",")] if isinstance(value, str) else value
                if (not isinstance(tools, list) or not tools or
                        any(not isinstance(t, str) or not t.strip() for t in tools)):
                    raise ValueError("tools: contains an empty or non-string tool")
                indices = [i for i in range(1, end) if lines[i].startswith("tools:")]
                if len(indices) != 1:
                    raise ValueError("frontmatter must have one tools: line")
                i = indices[0]
                newline = "\r\n" if lines[i].endswith("\r\n") else \
                    ("\n" if lines[i].endswith("\n") else "")
                # A block tools list belongs to this generated field too.
                stop = i + 1
                while stop < end and (lines[stop].startswith((" ", "\t", "- "))):
                    stop += 1
                del lines[i + 1:stop]
                lines[i] = self.agent_tools_line(role) + newline
                replaced = "".join(lines)
                if text != replaced:
                    replacements.append((role, path, text, replaced))
            except (OSError, UnicodeError, ValueError, StopIteration, yamlish.YamlishError) as exc:
                problems.append(f"{role}: {path}: {exc or 'missing closing frontmatter delimiter'}")
        return replacements, problems

    def registry(self) -> dict:
        return {"digest": self.digest(), "agents": {
            f"sky:{role}": {"tools": list(self.tools_for(role)),
                            "source": "plugin", "status": "active"}
            for role in self.roles_named()}}

    def render(self, directory: Path) -> list[str]:
        """Render role templates and the plugin source registry after preflight."""
        changed = self.sync_agents(directory, write=True)
        if self.new_style:
            path = Path(directory).parent / "registry.json"
            wanted = json.dumps(self.registry(), indent=2, ensure_ascii=False) + "\n"
            if not path.is_file() or path.read_bytes() != wanted.encode("utf-8"):
                path.write_bytes(wanted.encode("utf-8"))
                changed.append("registry.json")
        return changed

    def artifact_problems(self, directory: Path) -> list[str]:
        """CLI-only artifact lint; loading never depends on generated files."""
        if not self.new_style:
            return []
        problems = [f"agent drift: {item}; run sky policy render"
                    for item in self.sync_agents(directory, write=False)]
        path = Path(directory).parent / "registry.json"
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
            if actual != self.registry():
                problems.append(f"{path}: stale registry; run sky policy render")
        except (OSError, UnicodeError, ValueError):
            problems.append(f"{path}: missing or malformed registry; run sky policy render")
        return problems

    # ── agent cards ──────────────────────────────────────────────────────
    def check_agent_card(self, card: dict) -> list[str]:
        """Every way a card disagrees with the policy. Empty means it agrees.

        `allowed_actions` and `denied_actions` on an agent card were lists of
        strings that nothing checked, so a typo in an action name was silently
        a card that granted nothing. There is a real vocabulary now, so it is
        checked against it.

        A card may be **narrower** than its role and never wider: an owner
        handing one agent less than the role allows is the point of a card, but
        a card that grants what the role does not is the card quietly becoming
        the policy.
        """
        problems: list[str] = []
        role = card.get("role")
        if role not in self.roles:
            return [f"role {role!r} is not in this policy "
                    f"({', '.join(self.roles_named())})"]

        for field in ("allowed_actions", "denied_actions"):
            for action in card.get(field) or ():
                if action not in self.actions:
                    problems.append(f"{field}: {action!r} is not an action this "
                                    f"policy defines")

        allowed = set(card.get("allowed_actions") or ())
        for action in sorted(allowed):
            if action not in self.actions:
                continue
            decision = self.decide(role, action)
            if decision.outcome == DENY:
                problems.append(
                    f"allowed_actions: the {role} role cannot do {action!r} — "
                    f"{decision.why}")

        contradictory = allowed & set(card.get("denied_actions") or ())
        if contradictory:
            problems.append(f"{', '.join(sorted(contradictory))} is both allowed "
                            f"and denied on this card")
        return problems

    # ── drift ────────────────────────────────────────────────────────────
    def lint(self) -> list[str]:
        """Every way this policy contradicts itself or the code that uses it.

        This is the drift check. A policy file is edited by hand, months after
        it was written, by someone who did not write it — so the invariants are
        checked rather than trusted.
        """
        problems: list[str] = []

        if self.version != 1:
            problems.append(f"version {self.version} is not a version this "
                            f"code understands (expected 1)")
        if not self.roles:
            problems.append("no roles are defined")
        if not self.actions:
            problems.append("no actions are defined")

        def string_list(spec, key, where):
            value = spec.get(key, [])
            if not isinstance(value, list) or any(not isinstance(t, str) or not t for t in value):
                problems.append(f"{where}: {key} must be a list of nonempty strings")
                return []
            return value

        for tool, binding in self.bindings.items():
            if isinstance(tool, str) and (tool == "index.refresh" or tool.endswith(("__index_refresh", "__index.refresh"))):
                problems.append(f"binding {tool}: index.refresh is runtime-only")
            if (not isinstance(tool, str) or not tool or
                    not isinstance(binding, (str, dict)) or
                    not isinstance(self.binding(tool), str) or not self.binding(tool)):
                problems.append(f"tool {tool!r}: binding must name an action")
                continue
            if self.binding(tool) not in self.actions:
                problems.append(f"tool {tool!r}: {self.binding(tool)!r} is not a defined action")
            if tool.startswith("mcp__") and (
                    not isinstance(binding, dict) or
                    not isinstance(binding.get("reviewed_by"), str) or
                    not binding["reviewed_by"].strip()):
                problems.append(f"tool {tool!r}: MCP binding requires reviewed_by")

        skill_tools = {}
        for skill, spec in self.skills.items():
            if not isinstance(skill, str) or not skill:
                problems.append(f"skill {skill!r}: name must be a nonempty string")
            if not isinstance(spec, dict):
                problems.append(f"skill {skill!r}: must be a mapping")
                continue
            if "tools" not in spec:
                problems.append(f"skill {skill!r}: missing tools list")
            if "roles" in spec:
                problems.append(f"skill {skill!r}: roles key is not allowed; roles grant skills")
            names = string_list(spec, "tools", f"skill {skill}")
            try:
                skill_tools[skill] = self._resolve(names, f"skill {skill}")
            except PolicyError as exc:
                problems.append(str(exc))
                continue
            for tool in skill_tools[skill]:
                if tool == "index.refresh" or tool.endswith(("__index_refresh", "__index.refresh")):
                    problems.append(f"skill {skill}: index.refresh is runtime-only")
                action = self.binding(tool)
                if action is None:
                    problems.append(f"skill {skill}: tool {tool!r} has no binding")
                elif action in self.actions and (self.actions[action].outward or self.actions[action].never):
                    problems.append(f"skill {skill}: tool {tool!r} action {action!r} is outward or never; "
                                    "outward actions are prepared as intents in .sky/outbox/, not called")

        write_tools = ("Edit", "Write", "NotebookEdit", "Bash")
        for role, spec in sorted(self.roles.items()):
            if not isinstance(spec, dict):
                problems.append(f"role {role!r} is not a mapping")
                continue
            may = list(spec.get("may") or ())
            needs = list(spec.get("needs_human") or ())
            if "tools" in spec and ("base_tools" in spec or "skills" in spec):
                problems.append(f"{role}: legacy tools cannot be mixed with base_tools or skills")
            try:
                if "tools" in spec:
                    tools = list(self._resolve(spec.get("tools") or (), role))
                else:
                    base = string_list(spec, "base_tools", role)
                    grants = string_list(spec, "skills", role)
                    sources = [("base_tools", self._resolve(base, role))]
                    for skill in grants:
                        if skill not in self.skills:
                            problems.append(f"{role}: skill {skill!r} is not defined")
                        else:
                            sources.append((skill, skill_tools.get(skill, ())))
                    tools = []
                    for source, members in sources:
                        for tool in members:
                            if tool not in tools:
                                tools.append(tool)
                            action = self.binding(tool)
                            context = f"{role}: skill {source}: tool {tool!r} action {action!r}"
                            if action is None:
                                problems.append(context + " has no binding")
                            elif action in self.actions:
                                if self.actions[action].outward or self.actions[action].never:
                                    problems.append(context + " is outward or never; outward actions are "
                                                    "prepared as intents in .sky/outbox/, not called")
                                elif action not in may + needs:
                                    problems.append(context + " is not in may or needs_human")
            except PolicyError as exc:
                problems.append(str(exc))
                tools = []

            for tool in tools:
                if tool == "index.refresh" or tool.endswith(("__index_refresh", "__index.refresh")):
                    problems.append(f"{role}: index.refresh is runtime-only")

            for action in may + needs:
                if action not in self.actions:
                    problems.append(f"{role}: {action!r} is not a defined action")
                elif self.actions[action].never:
                    problems.append(
                        f"{role}: {action!r} is marked never and cannot be "
                        f"granted to anyone — {self.actions[action].never}")

            # RULE: no outward action is plainly allowed.
            for action in may:
                spec_action = self.actions.get(action)
                if spec_action is not None and spec_action.outward:
                    problems.append(
                        f"{role}: {action!r} changes what other people can see "
                        f"and is in `may`. Outward actions belong in "
                        f"`needs_human`")

            overlap = set(may) & set(needs)
            if overlap:
                problems.append(f"{role}: {', '.join(sorted(overlap))} is in "
                                f"both `may` and `needs_human`")
            if not tools:
                problems.append(f"{role}: no tools — the host has nothing to enforce")

            # RULE: a role that cannot edit must not hold an editing tool.
            # A reviewer with Bash is a writer wearing a reviewer's name.
            can_edit = "repo.edit" in may
            held = [t for t in tools
                    if any(t == w or t.startswith(w + "(") for w in write_tools)]
            if held and not can_edit:
                problems.append(
                    f"{role}: holds {', '.join(held)} but does not have "
                    f"repo.edit. A read-only role with an editing tool is a "
                    f"writer wearing its name")
            if can_edit and not held:
                problems.append(f"{role}: has repo.edit but no tool to do it with")

        for name, members in sorted(self.tool_groups.items()):
            if not members:
                problems.append(f"tool group {name!r} is empty")
            used_names = []
            for spec in self.roles.values():
                if not isinstance(spec, dict):
                    continue
                used_names.extend(spec.get("tools") or ())
                base = spec.get("base_tools")
                if isinstance(base, list):
                    used_names.extend(base)
                grants = spec.get("skills")
                for skill in grants if isinstance(grants, list) else ():
                    definition = self.skills.get(skill, {})
                    if isinstance(definition, dict) and isinstance(definition.get("tools"), list):
                        used_names.extend(definition["tools"])
            unused = f"+{name}" not in used_names
            if unused:
                problems.append(f"tool group {name!r} is defined and used by no role")

        # RULE: the guard's rules must refer to real actions.
        for rule in self.guard.get("deny_commands") or ():
            if not isinstance(rule, dict):
                problems.append("guard: every deny_commands entry must be a mapping")
                continue
            if not rule.get("pattern"):
                problems.append("guard: a deny_commands entry has no pattern")
            if not rule.get("reason"):
                problems.append(
                    f"guard: {rule.get('pattern')!r} has no reason. A denial "
                    f"nobody understands gets worked around")
            action = rule.get("action")
            if action and action not in self.actions:
                problems.append(f"guard: {action!r} is not a defined action")

        # RULE: every outward action a role can reach names the broker
        # operation that carries it, or is marked never.
        for name, action in sorted(self.actions.items()):
            if not action.outward or action.never or action.broker:
                continue
            reachable = [r for r, s in self.roles.items()
                         if isinstance(s, dict)
                         and name in set(s.get("needs_human") or ())]
            if reachable and name != "kb.ingest":
                problems.append(
                    f"{name!r} is outward, reachable by {', '.join(sorted(reachable))}, "
                    f"and names no broker operation to carry it")
        return problems
