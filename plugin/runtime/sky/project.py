"""SH-065: worktree-local managed configuration and installed org discovery.

Discovery never creates files. Invalid present configuration is an error, not
an invitation to fall back to an ungoverned policy. Development overrides are
handled by Policy.load; callers of resolve can use the same override check.
"""
from __future__ import annotations

import copy
import os
import re
import subprocess
from pathlib import Path

from . import yamlish
from .policy import PolicyError, _installed_policy, _repo_policy, _version_key
from . import policy as policy_module

PROJECT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:sky:schema:project", "title": "Managed project",
    "type": "object", "additionalProperties": False, "required": ["managed"],
    "properties": {
        "managed": {"type": "boolean"},
        "org_plugin": {"type": ["string", "null"], "minLength": 1,
                       "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)?$"},
        "kb": {"type": ["string", "null"], "minLength": 1},
        "sessions_dir": {"type": "string", "minLength": 1, "default": ".sky/sessions"},
        "context": {"type": "object", "additionalProperties": False,
                    "properties": {"max_chars": {"type": "integer", "minimum": 1,
                                                 "default": 40000}}},
    },
}


def schema() -> dict:
    """The published JSON schema; path containment also needs filesystem checks."""
    return copy.deepcopy(PROJECT_SCHEMA)


def contained(root: Path, relative: str) -> Path:
    """Resolve symlinks before deciding whether a relative path stays in root."""
    if (not isinstance(relative, str) or not relative.strip() or
            Path(relative).is_absolute() or re.match(r"^[A-Za-z]:", relative) or
            relative.startswith(("/", "\\"))):
        raise PolicyError(f"path {relative!r} must be relative inside the repository")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PolicyError(f"path {relative!r} escapes the repository")
    return path


def validate_config(body, root: Path) -> dict:
    if not isinstance(body, dict):
        raise PolicyError("project.yaml must be a mapping")
    unknown = set(body) - set(PROJECT_SCHEMA["properties"])
    if unknown:
        raise PolicyError(f"project.yaml: unknown keys: {', '.join(sorted(unknown))}")
    if type(body.get("managed")) is not bool:
        raise PolicyError("project.yaml: managed must be a boolean")
    result = copy.deepcopy(body)
    for key in ("org_plugin", "kb"):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise PolicyError(f"project.yaml: {key} must be a nonempty string or null")
    if result.get("org_plugin") and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?", result["org_plugin"]):
        raise PolicyError("project.yaml: org_plugin must name marketplace/plugin or plugin")
    context = result.get("context", {})
    if not isinstance(context, dict) or set(context) - {"max_chars"}:
        raise PolicyError("project.yaml: context accepts only max_chars")
    maximum = context.get("max_chars", 40000)
    if type(maximum) is not int or maximum < 1:
        raise PolicyError("project.yaml: context.max_chars must be a positive integer")
    result["context"] = {"max_chars": maximum}
    result.setdefault("sessions_dir", ".sky/sessions")
    contained(root, result["sessions_dir"])
    return result


def git_root(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (out.stdout or "").strip()
    return Path(text).resolve() if out.returncode == 0 and text else None


def read_mapping(path: Path) -> dict:
    try:
        body = yamlish.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yamlish.YamlishError) as exc:
        raise PolicyError(f"{path}: {exc}") from exc
    if not isinstance(body, dict):
        raise PolicyError(f"{path}: must be a mapping")
    return body


def explicit_override() -> str | Path | None:
    if os.environ.get("SKY_POLICY"):
        return os.environ["SKY_POLICY"]
    configured = Path(policy_module.CONFIG_POLICY).expanduser()
    return configured if configured.is_file() else None


def org_root(name: str, cache: Path | None = None) -> Path:
    """A bare name must identify one marketplace, then choose its newest version."""
    cache = Path(cache or Path(policy_module.PLUGIN_CACHE).expanduser())
    parts = name.split("/")
    if len(parts) not in (1, 2) or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", p) for p in parts):
        raise PolicyError(f"org plugin {name!r}: invalid installed plugin name")
    found = {}
    if cache.is_dir():
        for marketplace in sorted(cache.iterdir()):
            if not marketplace.is_dir() or (len(parts) == 2 and marketplace.name != parts[0]):
                continue
            plugin = marketplace / parts[-1]
            if not plugin.is_dir():
                continue
            versions = [v for v in plugin.iterdir() if v.is_dir() and (v / "policy.yaml").is_file()]
            if versions:
                found[f"{marketplace.name}/{plugin.name}"] = max(versions, key=lambda v: (_version_key(v.name), v.name))
    if not found:
        raise PolicyError(f"org plugin {name} is not installed")
    if len(found) != 1:
        raise PolicyError(f"org plugin {name} is ambiguous: {', '.join(sorted(found))}")
    return next(iter(found.values())).resolve()


def resolve(cwd: Path | str, *, shipped: Path | None = None,
            cache: Path | None = None, ignore_overrides: bool = False):
    """Return EffectivePolicy or None; each worktree owns its own configuration."""
    from .policy_layers import Layer, merge
    if not ignore_overrides and explicit_override() is not None:
        return None
    root = git_root(Path(cwd).resolve())
    if root is None:
        return None
    config_file = root / ".sky" / "project.yaml"
    if not config_file.is_file():
        return None
    config = validate_config(read_mapping(config_file), root)
    if not config["managed"]:
        return None
    if shipped is None:
        plugin_env = os.environ.get("SKY_PLUGIN_ROOT")
        shipped = (Path(plugin_env) / "policy.yaml") if plugin_env else (_installed_policy() or _repo_policy())
    if shipped is None:
        raise PolicyError("managed project: no shipped policy.yaml found")
    shipped = Path(shipped).resolve()
    layers = [Layer("plugin", read_mapping(shipped), shipped.parent, "sky")]
    if config.get("org_plugin"):
        org = org_root(config["org_plugin"], cache)
        layers.append(Layer("org", read_mapping(org / "policy.yaml"), org, org.parent.name))
    patch = root / ".sky" / "policy.yaml"
    layers.append(Layer("project", read_mapping(patch) if patch.is_file() else {}, root / ".sky", ""))
    return merge(layers, root=root, config=config)
