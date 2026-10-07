"""SH-065: additive patches under the shipped ceiling and owned project renders.

Revocations name exact expanded tools per role, not semantic MCP aliases. The
effective Policy is validated after merging a patch, never by loading that
partial patch as a complete policy. No plugin file is written here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import yamlish
from .policy import Policy, PolicyError

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_PATCH_KEYS = {"tools", "tool_groups", "skills", "roles", "routing", "workflows", "sessions_dir"}
_ROLE_PATCH = {"skills_add", "skills_remove", "tools_remove", "may_remove", "needs_human_remove"}


@dataclass(frozen=True)
class Layer:
    name: str
    body: dict
    root: Path
    namespace: str = ""


def _error(layer: str, reason: str):
    raise PolicyError(f"{layer} layer: {reason}")


def _names(value, layer: str, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(n, str) or not n.strip() for n in value):
        _error(layer, f"{where} must be a list of nonempty strings")
    return value


def _union(first, second):
    return list(dict.fromkeys([*first, *second]))


def _identity_order(tools, plugin_tools=()):
    """Keep shared tools in plugin order, then new tools in grant order."""
    held = set(tools)
    shared = set(plugin_tools)
    return tuple([t for t in plugin_tools if t in held] +
                 [t for t in tools if t not in shared])


def _expand(body: dict, names, stack=()) -> list[str]:
    result = []
    for name in names:
        if name.startswith("+"):
            group = name[1:]
            if group not in body.get("tool_groups", {}):
                raise PolicyError(f"tool group {group!r} is not defined")
            if group in stack:
                raise PolicyError(f"tool group cycle: {' -> '.join((*stack, group))}")
            result = _union(result, _expand(body, body["tool_groups"][group], (*stack, group)))
        else:
            result = _union(result, [name])
    return result


def _role_tools(body, role, revocations) -> list[str]:
    spec = body["roles"][role]
    names = list(spec.get("tools", spec.get("base_tools", [])))
    for skill in spec.get("skills", []):
        if skill not in body.get("skills", {}):
            raise PolicyError(f"{role}: skill {skill!r} is not defined")
        names.extend(body["skills"][skill]["tools"])
    denied = revocations.get(role, {}).get("tools", {})
    return [tool for tool in _expand(body, names) if tool not in denied]


def _validated(body, revocations, layer) -> Policy:
    # Flatten groups and per-role revocations for the existing strict evaluator.
    # Preserve the raw merged mapping separately for provenance and future patches.
    normalized = copy.deepcopy(body)
    try:
        for skill, spec in normalized.get("skills", {}).items():
            spec["tools"] = _expand(body, spec["tools"])
        for role, spec in normalized["roles"].items():
            tools = _role_tools(body, role, revocations)
            if "tools" in spec:
                spec["tools"] = tools
            else:
                spec["base_tools"] = tools
                spec["skills"] = []
        # Inactive groups remain in the raw merged policy, but cannot turn the
        # effective evaluator red merely because their last grant was removed.
        normalized["tool_groups"] = {}
        return Policy.from_dict(normalized)
    except (PolicyError, KeyError, TypeError) as exc:
        _error(layer, str(exc))


def merge(layers: list[Layer], *, root: Path, config: dict | None = None):
    if not layers or layers[0].name != "plugin":
        raise PolicyError("first policy layer must be plugin")
    if [l.name for l in layers] not in (["plugin"], ["plugin", "project"],
                                      ["plugin", "org"], ["plugin", "org", "project"]):
        raise PolicyError("policy layer order must be plugin, org, project")
    body = copy.deepcopy(layers[0].body)
    Policy.from_dict(body)  # The shipped policy is complete and strict, too.
    for key in ("tools", "tool_groups", "skills"):
        body.setdefault(key, {})
    revocations, provenance, sources, history, snapshots = {}, {}, {}, {}, {}
    for role, spec in body["roles"].items():
        if not _NAME.fullmatch(role):
            _error("plugin", f"unsafe role name {role!r}")
        sources[role] = "plugin"
        history[role] = [("plugin", f"sky:{role}")]
        for key in ("skills", "may", "needs_human"):
            for name in spec.get(key, []):
                provenance[f"roles.{role}.{key}.{name}"] = "plugin"
        for tool in _role_tools(body, role, revocations):
            provenance[f"roles.{role}.tools.{tool}"] = "plugin"
    snapshots["plugin"] = {r: tuple(_role_tools(body, r, revocations)) for r in sources}
    skill_sources = {name: "plugin" for name in body["skills"]}
    for layer in layers[1:]:
        patch = layer.body
        if not isinstance(patch, dict) or set(patch) - _PATCH_KEYS:
            unknown = sorted(set(patch) - _PATCH_KEYS) if isinstance(patch, dict) else ["not a mapping"]
            _error(layer.name, f"forbidden patch keys: {', '.join(unknown)}")
        before = {r: (copy.deepcopy(body["roles"][r]), tuple(_role_tools(body, r, revocations))) for r in sources}
        added_tools, grants = {}, {}
        for key in ("tools", "tool_groups", "skills", "roles"):
            if key in patch and not isinstance(patch[key], dict):
                _error(layer.name, f"{key} must be a mapping")
        for key in ("tools", "tool_groups"):
            for name, value in patch.get(key, {}).items():
                if name in body[key]:
                    _error(layer.name, f"{key}: existing name {name!r} cannot be redefined")
                if not isinstance(name, str) or not name:
                    _error(layer.name, f"{key}: invalid name {name!r}")
                if key == "tool_groups":
                    _names(value, layer.name, f"group {name}")
                    if not value:
                        _error(layer.name, f"group {name} is empty")
                else:
                    action = value if isinstance(value, str) else value.get("action") if isinstance(value, dict) else None
                    if not isinstance(action, str) or action not in body["actions"]:
                        _error(layer.name, f"tool {name}: binding to unknown action {action!r}")
                    if name.startswith("mcp__") and (not isinstance(value, dict) or
                            not isinstance(value.get("reviewed_by"), str) or not value["reviewed_by"].strip()):
                        _error(layer.name, f"tool {name}: MCP binding requires reviewed_by")
                body[key][name] = copy.deepcopy(value)
                provenance[f"{key}.{name}"] = layer.name
        for name, spec in patch.get("skills", {}).items():
            if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(spec, dict):
                _error(layer.name, f"invalid skill {name!r}")
            if name not in body["skills"]:
                if set(spec) != {"tools"}:
                    _error(layer.name, f"new skill {name}: requires only tools")
                _names(spec["tools"], layer.name, f"skill {name}.tools")
                body["skills"][name] = copy.deepcopy(spec)
                skill_sources[name] = layer.name
                provenance[f"skills.{name}"] = layer.name
            else:
                if set(spec) - {"tools_add", "tools_remove"}:
                    _error(layer.name, f"existing skill {name}: accepts only tools_add/tools_remove")
                held = _expand(body, body["skills"][name]["tools"])
                remove = _expand(body, _names(spec.get("tools_remove", []), layer.name, f"skill {name}.tools_remove"))
                if set(remove) - set(held):
                    _error(layer.name, f"skill {name}: unknown removal {sorted(set(remove) - set(held))[0]}")
                affected = {role: _role_tools(body, role, revocations)
                            for role, role_spec in body["roles"].items()
                            if name in role_spec.get("skills", [])}
                additions = _expand(body, _names(spec.get("tools_add", []), layer.name, f"skill {name}.tools_add"))
                body["skills"][name]["tools"] = _union([t for t in held if t not in remove], additions)
                for role, held_tools in affected.items():
                    remaining = _role_tools(body, role, revocations)
                    revoked = revocations.setdefault(role, {"tools": {}, "skills": {}})
                    for tool in held_tools:
                        if tool not in remaining:
                            revoked["tools"].setdefault(tool, layer.name)
                            provenance[f"removed.roles.{role}.tools.{tool}"] = layer.name
                added_tools[name] = additions
            for tool in _expand(body, body["skills"][name]["tools"]):
                provenance.setdefault(f"skills.{name}.tools.{tool}", layer.name)
        for role, spec in patch.get("roles", {}).items():
            if not isinstance(role, str) or not _NAME.fullmatch(role) or not isinstance(spec, dict):
                _error(layer.name, f"invalid role {role!r}")
            if "tools" in spec:
                _error(layer.name, f"role {role}: legacy tools is forbidden in lower layers")
            if role not in body["roles"]:
                required = {"base_tools", "skills", "may", "needs_human"}
                if not required <= set(spec) or set(spec) - (required | {"purpose"}):
                    _error(layer.name, f"new role {role}: requires base_tools/skills/may/needs_human")
                for key in required:
                    _names(spec[key], layer.name, f"role {role}.{key}")
                body["roles"][role] = copy.deepcopy(spec)
                history[role] = []
            else:
                if "tools" in body["roles"][role]:
                    _error(layer.name, f"legacy shipped role {role} cannot accept skill patches")
                if set(spec) - _ROLE_PATCH:
                    _error(layer.name, f"existing role {role}: forbidden patch keys {sorted(set(spec) - _ROLE_PATCH)}")
                current = body["roles"][role]
                revoked = revocations.setdefault(role, {"tools": {}, "skills": {}})
                for key in ("skills", "may", "needs_human"):
                    remove = _names(spec.get(key + "_remove", []), layer.name, f"role {role}.{key}_remove")
                    unknown = set(remove) - set(current.get(key, []))
                    if unknown:
                        _error(layer.name, f"role {role}: unknown {key} removal {sorted(unknown)[0]}")
                    if key == "skills":
                        held_tools = _role_tools(body, role, revocations)
                        for skill in remove:
                            revoked["skills"].setdefault(skill, layer.name)
                    for item in remove:
                        provenance[f"removed.roles.{role}.{key}.{item}"] = layer.name
                    current[key] = [item for item in current.get(key, []) if item not in remove]
                    if key == "skills":
                        # Revoke only lost tools: another skill or base grant
                        # still authorizes overlapping tools. tools_remove below
                        # is an outright revocation regardless of other grants.
                        remaining = _role_tools(body, role, revocations)
                        for tool in held_tools:
                            if tool not in remaining:
                                revoked["tools"].setdefault(tool, layer.name)
                                provenance[f"removed.roles.{role}.tools.{tool}"] = layer.name
                remove_tools = _expand(body, _names(spec.get("tools_remove", []), layer.name, f"role {role}.tools_remove"))
                available = before[role][1]
                unknown = set(remove_tools) - set(available)
                if unknown:
                    _error(layer.name, f"role {role}: unknown tool removal {sorted(unknown)[0]}")
                for tool in remove_tools:
                    revoked["tools"].setdefault(tool, layer.name)
                    provenance[f"removed.roles.{role}.tools.{tool}"] = layer.name
                additions = _names(spec.get("skills_add", []), layer.name, f"role {role}.skills_add")
                current["skills"] = _union(current.get("skills", []), additions)
                grants[role] = additions
            for key in ("skills", "may", "needs_human"):
                for item in body["roles"][role].get(key, []):
                    provenance.setdefault(f"roles.{role}.{key}.{item}", layer.name)
        # Check explicit lower additions, not still-present upper references to
        # tools already excluded by a revocation. New roles have no revocations.
        for role, spec in body["roles"].items():
            revoked = revocations.get(role, {"tools": {}, "skills": {}})
            for skill in grants.get(role, []):
                if skill not in body["skills"]:
                    _error(layer.name, f"role {role}: unknown skill {skill}")
                if skill in revoked["skills"]:
                    _error(layer.name, f"role {role}: skill {skill} revoked by {revoked['skills'][skill]}")
            additions = []
            for skill in spec.get("skills", []):
                if skill in grants.get(role, []):
                    additions.extend(_expand(body, body["skills"][skill]["tools"]))
                additions.extend(added_tools.get(skill, []))
            for tool in additions:
                if tool in revoked["tools"]:
                    _error(layer.name, f"role {role}: tool {tool} revoked by {revoked['tools'][tool]}")
        for key in ("routing", "workflows"):
            if key in patch:
                if not isinstance(patch[key], dict):
                    _error(layer.name, f"{key} must be a mapping")
                body[key] = {**body.get(key, {}), **copy.deepcopy(patch[key])}
                provenance[key] = layer.name
        if "sessions_dir" in patch:
            from .project import contained
            contained(root, patch["sessions_dir"])
            body["sessions_dir"] = patch["sessions_dir"]
            provenance["sessions_dir"] = layer.name
        validated = _validated(body, revocations, layer.name)
        for role, spec in body["roles"].items():
            tools = tuple(_role_tools(body, role, revocations))
            if role in snapshots["plugin"] and set(tools) == set(snapshots["plugin"][role]):
                sources[role] = "plugin"
                history[role] = [("plugin", f"sky:{role}")]
            elif role not in before or set(tools) != set(before[role][1]):
                sources[role] = layer.name
                identity = f"{layer.namespace}:{role}" if layer.name == "org" else f"sky-{role}"
                history[role].append((layer.name, identity))
            for tool in tools:
                provenance.setdefault(f"roles.{role}.tools.{tool}", layer.name)
        snapshots[layer.name] = {
            r: _identity_order(_role_tools(body, r, revocations), snapshots["plugin"].get(r, ()))
            for r in sources}
    validated = _validated(body, revocations, layers[-1].name)
    return EffectivePolicy(validated, body, Path(root).resolve(), tuple(layers),
                           provenance, revocations, sources, history, snapshots,
                           skill_sources, copy.deepcopy(config or {}))


@dataclass
class AgentDocument:
    text: str
    name: str
    tools: tuple[str, ...]
    name_index: int
    tools_index: int
    tools_end: int

    def rendered(self, name: str, tools: tuple[str, ...]) -> bytes:
        lines = self.text.splitlines(keepends=True)
        newline = "\r\n" if lines[self.tools_index].endswith("\r\n") else "\n"
        lines[self.name_index] = "name: " + name + newline
        lines[self.tools_index:self.tools_end] = ["tools: " + ", ".join(tools) + newline]
        return "".join(lines).encode("utf-8")


def read_agent(path: Path, expected_name: str | None = None) -> AgentDocument:
    """Claude rest-of-line metadata, with strict, delimited tools parsing."""
    try:
        text = path.read_bytes().decode("utf-8")
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            raise ValueError("missing opening frontmatter delimiter")
        end = next(i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---")
        fields, indices, field_name = {}, {}, ""
        for i in range(1, end):
            raw = lines[i].rstrip("\r\n")
            if not raw.strip() or raw.startswith("#"):
                continue
            if raw.startswith((" ", "- ")) and field_name == "tools":
                fields[field_name] += "\n" + raw
                continue
            match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)", raw)
            if not match:
                raise ValueError("unparsable frontmatter line")
            field_name, value = match.groups()
            if field_name in fields:
                raise ValueError(f"duplicate field {field_name}")
            fields[field_name], indices[field_name] = value, i
        name = fields.get("name", "")
        if not _NAME.fullmatch(name) or (expected_name is not None and name != expected_name):
            raise ValueError(f"frontmatter name must be {expected_name or 'a safe identifier'}")
        if "tools" not in fields:
            raise ValueError("missing tools")
        value = yamlish.parse("tools: " + fields["tools"])["tools"]
        tools = [t.strip() for t in value.split(",")] if isinstance(value, str) else value
        if not isinstance(tools, list) or not tools or any(not isinstance(t, str) or not t.strip() for t in tools):
            raise ValueError("empty or invalid tools")
        stop = indices["tools"] + 1
        while stop < end and lines[stop].startswith((" ", "- ")):
            stop += 1
        return AgentDocument(text, name, tuple(tools), indices["name"], indices["tools"], stop)
    except (OSError, UnicodeError, ValueError, StopIteration, yamlish.YamlishError) as exc:
        raise PolicyError(f"agent {path}: {exc or 'unterminated frontmatter'}") from exc


@dataclass
class EffectivePolicy:
    policy: Policy
    body: dict
    root: Path
    layers: tuple[Layer, ...]
    provenance: dict
    revocations: dict
    role_sources: dict
    history: dict
    snapshots: dict
    skill_sources: dict
    config: dict = field(default_factory=dict)

    def __getattr__(self, name):
        return getattr(self.policy, name)

    @property
    def path(self):
        return self.layers[0].root / "policy.yaml"

    @property
    def roles(self):
        return self.body["roles"]

    def skills_for(self, role):
        if role not in self.roles:
            raise PolicyError(f"{role!r} is not a role in this policy")
        return tuple(self.roles[role].get("skills", []))

    def tools_for(self, role):
        return _identity_order(self.policy.tools_for(role), self.snapshots["plugin"].get(role, ()))

    def digest(self):
        canonical = json.dumps({"policy": self.body, "revocations": self.revocations},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def requires_identity_selection(self, role):
        return self.role_sources.get(role) in ("org", "project")

    def layers_notice(self):
        line = f"effective policy: plugin {self.path} + project .sky/policy.yaml"
        for layer in self.layers:
            if layer.name == "org":
                line += f" + org {layer.root.parent.parent.name}/{layer.namespace}"
        return line

    def layer_lines(self):
        """Readable attribution for active grants and recorded removals."""
        active = set()
        for role, spec in self.roles.items():
            for key in ("skills", "may", "needs_human"):
                active.update(f"roles.{role}.{key}.{n}" for n in spec.get(key, []))
            active.update(f"roles.{role}.tools.{t}" for t in self.tools_for(role))
        return [f"{key}: {self.provenance[key]}" for key in sorted(self.provenance)
                if key in active or key.startswith("removed.")]

    def _source_path(self, source, role):
        layer = next(l for l in self.layers if l.name == source)
        if source == "project":
            from .project import contained
            return contained(self.root, f".sky/agents/{role}.md")
        return layer.root / "agents" / f"{role}.md"

    def _owned_path(self, relative):
        from .project import contained
        if not re.fullmatch(r"\.claude/(?:agents/sky-[A-Za-z0-9_-]+\.md|skills/[A-Za-z0-9_-]+/SKILL\.md)", relative):
            raise PolicyError(f"registry owned_files: invalid path {relative!r}")
        path = contained(self.root, relative)
        if (self.root / relative).is_symlink():
            raise PolicyError(f"registry owned file is a symlink: {relative}")
        return path

    def _old_registry(self):
        from .project import contained
        if (self.root / ".sky" / "registry.json").is_symlink():
            raise PolicyError("effective registry must not be a symlink")
        path = contained(self.root, ".sky/registry.json")
        if not path.exists():
            return {}
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(old, dict) or not isinstance(old.get("owned_files"), dict):
                raise ValueError("owned_files must be a mapping")
            for relative, digest in old["owned_files"].items():
                self._owned_path(relative)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("owned_files must record SHA-256 hashes")
            return old
        except (OSError, UnicodeError, ValueError) as exc:
            raise PolicyError(f"cannot trust effective registry ownership: {exc}") from exc

    def registry(self, owned_files=None):
        agents, active = {}, {}
        digest = self.digest()
        for role, identities in self.history.items():
            for i, (source, identity) in enumerate(identities):
                if identity in agents:
                    raise PolicyError(f"agent identity collision: {identity}")
                agents[identity] = {"role": role, "tools": list(self.snapshots[source][role]),
                                    "source": source, "status": "active" if i == len(identities) - 1 else "superseded",
                                    "digest": digest}
            active[role] = identities[-1][1]
        return {"digest": digest, "agents": agents, "active_roles": active,
                "revocations": copy.deepcopy(self.revocations),
                "owned_files": owned_files or {}}

    def _plan(self):
        old = self._old_registry()
        owned = old.get("owned_files", {})
        files, plugin_names = {}, set()
        # Validate all source definitions, including helpers used in collision checks.
        for layer in self.layers:
            if layer.name == "project":
                continue
            for path in sorted((layer.root / "agents").glob("*.md")):
                plugin_names.add(read_agent(path).name)
        for role, identities in self.history.items():
            for source, _ in identities:
                if source == "project":
                    continue
                document = read_agent(self._source_path(source, role), role)
                expected = set(self.snapshots[source][role])
                difference = sorted(set(document.tools) ^ expected)
                if difference:
                    raise PolicyError(f"{source} agent {role}: first differing tool {difference[0]}")
            if self.role_sources[role] == "project":
                previous = identities[-2][0] if len(identities) > 1 else "project"
                document = read_agent(self._source_path(previous, role), role)
                name = f"sky-{role}"
                if name in plugin_names:
                    raise PolicyError(f"project agent name collision with plugin: {name}")
                relative = f".claude/agents/{name}.md"
                files[relative] = document.rendered(name, self.tools_for(role))
        for skill, source in self.skill_sources.items():
            if source == "project":
                from .project import contained
                path = contained(self.root, f".sky/skills/{skill}/SKILL.md")
                try:
                    files[f".claude/skills/{skill}/SKILL.md"] = path.read_bytes()
                    files[f".claude/skills/{skill}/SKILL.md"].decode("utf-8")
                except (OSError, UnicodeError) as exc:
                    raise PolicyError(f"project skill {skill}: cannot read {path}: {exc}") from exc
        desired_names = {f"sky-{r}" for r, source in self.role_sources.items() if source == "project"}
        seen = set()
        for path in sorted((self.root / ".claude" / "agents").glob("*.md")):
            relative = path.relative_to(self.root).as_posix()
            if relative in owned and relative not in files:
                continue  # Preflight ownership, then remove this stale generated file.
            name = read_agent(path).name
            if name in seen or name in plugin_names:
                raise PolicyError(f"project agent name collision: {name}")
            seen.add(name)
            if name in desired_names and relative != f".claude/agents/{name}.md":
                raise PolicyError(f"project agent name collision: {name}")
        for relative in set(owned) | set(files):
            path = self._owned_path(relative)
            if path.exists():
                if relative not in owned:
                    raise PolicyError(f"refusing to overwrite unowned file {relative}")
                if hashlib.sha256(path.read_bytes()).hexdigest() != owned[relative]:
                    raise PolicyError(f"owned file changed outside render: {relative}")
        hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
        registry = self.registry(hashes)
        return files, sorted(set(owned) - set(files)), registry, old

    def render(self, directory=None):
        """Preflight sources, collisions and ownership before any mutation."""
        files, stale, registry, old = self._plan()
        changed = []
        for relative, contents in files.items():
            path = self._owned_path(relative)
            if not path.exists() or path.read_bytes() != contents:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
                changed.append(relative)
        for relative in stale:
            path = self._owned_path(relative)
            if path.exists():
                path.unlink()
                changed.append("removed " + relative)
        if old != registry:
            path = self.root / ".sky" / "registry.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            changed.append(".sky/registry.json")
        return changed

    def artifact_problems(self, directory=None):
        try:
            files, stale, registry, old = self._plan()
            problems = [f"stale generated file {f}" for f in stale]
            for relative, contents in files.items():
                path = self._owned_path(relative)
                if not path.exists() or path.read_bytes() != contents:
                    problems.append(f"rendered file drift: {relative}")
            if old != registry:
                problems.append("effective registry is missing or stale")
            return [p + "; run sky policy render" for p in problems]
        except (PolicyError, OSError) as exc:
            return [str(exc) + "; run sky policy render"]

    def definition_for(self, role):
        """Verify the effective registry before returning one active definition."""
        if role not in self.roles:
            raise PolicyError(f"unknown role {role!r}")
        old = self._old_registry()
        wanted = self.registry(old.get("owned_files", {}))
        if old != wanted:
            raise PolicyError("effective registry is missing or stale; run sky policy render")
        identity = old["active_roles"][role]
        entry = old["agents"].get(identity, {})
        if entry.get("status") != "active":
            raise PolicyError(f"effective identity {identity} is superseded")
        source = entry["source"]
        if source == "project":
            relative = f".claude/agents/{identity}.md"
            path = self._owned_path(relative)
            expected_name = identity
            if relative not in old["owned_files"] or not path.is_file() or \
                    hashlib.sha256(path.read_bytes()).hexdigest() != old["owned_files"][relative]:
                raise PolicyError(f"effective agent {role}: {path}: missing or changed owned definition")
        else:
            path, expected_name = self._source_path(source, role), role
        document = read_agent(path, expected_name)
        difference = sorted(set(document.tools) ^ set(self.tools_for(role)))
        if difference:
            raise PolicyError(f"effective agent {role}: {path}: first differing tool {difference[0]}")
        return path, expected_name
