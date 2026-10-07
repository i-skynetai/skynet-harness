"""Check the agent definition that carries Claude's role boundary.

`--allowedTools` pre-approves calls; it does not remove tools. Refuse a missing
or different definition rather than launch a role whose authority is unknown.
This checks local plugin data, not which plugin a running host has loaded.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import yamlish
from .policy import CONFIG_POLICY, Policy, PolicyError, _installed_policy, _repo_policy


class DefinitionError(Exception):
    """A role's definition cannot be trusted to match its policy."""


def plugin_root(policy: Policy) -> Path:
    """Use the selected plugin policy, or the existing plugin discovery order.

    A configured standalone policy has no agents beside it. Its definitions
    come from SKY_PLUGIN_ROOT, the installed plugin, or this runtime's checkout.
    An explicit plugin policy must never fall back to another plugin on drift.
    """
    if policy.path is not None:
        path = Path(policy.path).expanduser().resolve()
        if path != Path(CONFIG_POLICY).expanduser().resolve():
            return path.parent
    root = os.environ.get("SKY_PLUGIN_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    found = _installed_policy() or _repo_policy()
    if found is None:
        raise DefinitionError("cannot locate plugin agent definitions")
    return found.parent


def check_definition(policy: Policy, role: str) -> Path:
    """Return the checked file; otherwise name the role, file and first defect.

    Read only the delimited frontmatter, never a tools line in the prose. The
    shipped format is a flat header with a comma-separated tools scalar; YAML
    flow lists are also understood by the core's strict reader. Unsupported
    syntax, duplicate fields and empty tool names are refused, never guessed.
    """
    if hasattr(policy, "definition_for"):
        try:
            path, _ = policy.definition_for(role)
            return path
        except PolicyError as exc:
            raise DefinitionError(f"{role}: effective agent definition: {exc}") from exc
    if role not in policy.roles or not re.fullmatch(r"[A-Za-z0-9_-]+", role):
        raise DefinitionError(f"unknown role {role!r}")
    try:
        path = plugin_root(policy) / "agents" / f"{role}.md"
    except DefinitionError as exc:
        raise DefinitionError(f"{role}: agents/{role}.md: {exc}") from exc

    def fail(reason: str) -> None:
        raise DefinitionError(f"{role}: {path}: {reason}")

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read agent definition ({exc})")
    if not lines or lines[0] != "---":
        fail("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail("missing closing frontmatter delimiter")
    fields = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)", line)
        if not match:
            fail("unparsable frontmatter line")
        key, value = match.groups()
        if key in fields:
            fail(f"duplicate frontmatter field {key!r}")
        fields[key] = value
    if fields.get("name") != role:
        fail(f"frontmatter name must be {role!r}")
    if "tools" not in fields:
        fail("missing frontmatter tools: line")
    try:
        value = yamlish.parse("tools: " + fields["tools"])["tools"]
    except yamlish.YamlishError as exc:
        fail(f"unparsable tools: line ({exc})")
    if isinstance(value, str):
        tools = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        tools = value
    else:
        fail("tools: must be a comma-separated string or flow list")
    if not tools or any(not isinstance(t, str) or not t.strip() for t in tools):
        fail("tools: contains an empty or non-string tool")
    actual, expected = set(tools), set(policy.tools_for(role))
    differences = sorted(actual ^ expected)
    if differences:
        tool = differences[0]
        fail(f"{'extra' if tool in actual else 'missing'} tool {tool!r}")
    return path
