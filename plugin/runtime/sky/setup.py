"""Turning an installed plugin into a working one — the config contract (H2).

Three files, and **which one holds what is the whole design**:

===========================  ====================================================
`~/.config/sky/env`          0600. Tokens, and only tokens.
`~/.config/sky/kb-map.json`  Which knowledge bases exist. The *names* of token
                             variables, never their values.
`~/.config/sky/sky-headers`  The helper the host runs to get the token.
`~/.claude.json`             One user-scoped MCP server per knowledge base:
                             its address, and that helper.
===========================  ====================================================

**Why the knowledge base is registered here and not left to the plugin.**
Measured against Claude Code 2.1.152, not assumed:

* `headersHelper` runs for a **user-scoped** server — proven by a helper that
  left a marker file when the host ran it.
* For a **plugin-provided** server it does not run at all. Same helper, same
  absolute path, no marker, and the request reached the server with no
  `Authorization` header.

So a plugin that declares its own server can only be authenticated by putting
`${SKY_KB_PAT}` in the host's environment — which means the token in the host's
settings file, a second copy of the one secret, in the kind of file people
paste into issues. Registering the server here instead keeps the token in one
0600 file that the host never opens, and keeps the *plugin* free of any address
at all, which is what D-2 asks for.

**The helper's contract, read out of the executable** (see `HELPER_CONTRACT`):
run through a shell, 10-second timeout, `CLAUDE_CODE_MCP_SERVER_NAME` and
`CLAUDE_CODE_MCP_SERVER_URL` added to the environment, and it must exit 0
having printed a JSON object whose values are all strings. Anything else is
refused by the host — which is why the helper prints nothing on failure.

**The helper is copied here rather than pointed at in the plugin cache.** That
path carries the plugin's version number, so a pointer into it becomes a
dangling path on the next `claude plugin update` — and the symptom would be an
authentication failure that looks exactly like a revoked token.

Three rules this module will not bend:

**A token is never printed.** Not in a diff, not in an error, not by `doctor`.
The value is compared and counted; it is never rendered.

**A prompt needs a terminal.** `init` refuses to read a token when standard
input is not a terminal, because the usual reason for that is a transcript, a
log, or an agent — and a token that reaches any of those is already spent.

**Nothing is written to a file this did not create without showing the change
first.** `~/.claude.json` belongs to the user and holds every other MCP server
they have. `init` prints the exact change and waits, and `uninstall` removes
only what the manifest says was added.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from .kbmap import CONFIG_DIR, MAP_FILE, PRIVACY_CLASSES, KBMap, KBMapError

#: What the host guarantees the helper, taken from the executable rather than
#: from documentation. Quoted in the helper's own docstring too.
HELPER_CONTRACT = (
    "run via a shell, 10s timeout, env + CLAUDE_CODE_MCP_SERVER_NAME and "
    "CLAUDE_CODE_MCP_SERVER_URL; must exit 0 and print a JSON object of strings"
)

ENV_FILE = "env"
MANIFEST_FILE = "installed.json"
HELPER_FILE = "sky-headers"
#: Where a user-installed command belongs on a Unix machine. `~/.local/bin` is
#: on PATH by default on most systems and is the conventional place for one.
LAUNCHER_DIR = Path("~/.local/bin").expanduser()
#: Where the host keeps user-scoped MCP servers. The user's file, not ours.
CLAUDE_JSON = Path("~/.claude.json").expanduser()

_KEY_OK = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SetupError(Exception):
    """Something the person running this can fix, said in those terms."""


# ── the token file ───────────────────────────────────────────────────────
def read_env(path: Path | None = None) -> dict[str, str]:
    """`KEY=value` lines. Missing file is an empty dict, not an error.

    Deliberately not a shell parser: no quoting, no substitution, no `export`.
    A token is an opaque string, and a parser that interprets its contents is
    a parser that can mangle one.
    """
    path = Path(path or CONFIG_DIR / ENV_FILE)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SetupError(f"{path}:{number} is not KEY=value")
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY_OK.match(key):
            raise SetupError(
                f"{path}:{number} has the name {key!r}; an environment variable "
                "name is upper-case letters, digits and underscores")
        values[key] = value.strip()
    return values


def write_env(values: dict[str, str], path: Path | None = None) -> Path:
    """Replace the token file, 0600, atomically.

    Atomically because the alternative — truncate, then write — leaves an empty
    token file if anything interrupts it, and the symptom of an empty token
    file is an authentication error that looks like a revoked token.
    """
    path = Path(path or CONFIG_DIR / ENV_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ["# Tokens for SKY. One line per variable; nothing else belongs here.",
            "# Written by `sky setup`. Keep it at mode 600.", ""]
    body += [f"{k}={values[k]}" for k in sorted(values)]
    temporary = path.with_name(path.name + ".new")
    temporary.write_text("\n".join(body) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    return path


def token_variable(instance: str) -> str:
    """`example-kb` → `SKY_PAT_EXAMPLE_KB`. One token per instance, not per KB.

    The platform issues one key per person per instance, so per-KB variables
    would be several names for one secret — and rotating one of them would look
    like it worked while the others kept a dead token.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", instance).strip("_").upper()
    if not cleaned:
        raise SetupError(f"{instance!r} does not give a usable variable name")
    return f"SKY_PAT_{cleaned}"


# ── the profile an administrator sends ───────────────────────────────────
@dataclass(frozen=True)
class Profile:
    """What a new user is given: an address, a tenant, an ontology.

    Everything else has a defensible default, because every field in this file
    is a field somebody has to be told, and a field nobody is told is a field
    nobody gets wrong.
    """
    name: str
    url: str
    tenant: str
    ontology: str
    instance: str
    privacy: str = "work"
    purpose: str = ""
    code_url: str = ""
    kind: str = "task"
    default: bool = True
    #: Directories this knowledge base owns. Without them every run falls back
    #: to the default, which is the wrong KB for every repository but one.
    repos: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Path) -> "Profile":
        path = Path(path).expanduser()
        if not path.is_file():
            raise SetupError(f"no profile at {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SetupError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise SetupError(f"{path} should hold one JSON object")
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "Profile":
        missing = [k for k in ("mcp_url", "tenant_code", "ontology") if not raw.get(k)]
        if missing:
            raise SetupError(
                "the profile is missing " + ", ".join(missing)
                + ". A profile needs the address, the tenant and the ontology; "
                "your administrator produces it.")
        privacy = str(raw.get("privacy", "work"))
        if privacy not in PRIVACY_CLASSES:
            raise SetupError(f"privacy {privacy!r} is not one of "
                             f"{', '.join(PRIVACY_CLASSES)}")
        instance = str(raw.get("instance") or _instance_from(raw["mcp_url"]))
        return cls(
            name=str(raw.get("name") or "team_kb"),
            url=str(raw["mcp_url"]),
            tenant=str(raw["tenant_code"]),
            ontology=str(raw["ontology"]),
            instance=instance,
            privacy=privacy,
            purpose=str(raw.get("purpose", "")),
            code_url=str(raw.get("code_url", "")),
            kind=str(raw.get("kind", "task")),
            default=bool(raw.get("default", True)),
            repos=tuple(str(r) for r in (raw.get("repos") or ())
                        if str(r).strip()),
        )

    def entry(self) -> dict:
        """This profile as one `kb-map.json` entry. No token, by construction."""
        body = {
            "purpose": self.purpose or f"{self.name} knowledge base",
            "mcp_url": self.url,
            "tenant_code": self.tenant,
            "ontology": self.ontology,
            "privacy": self.privacy,
            "pat_env": token_variable(self.instance),
        }
        if self.code_url:
            body["code_url"] = self.code_url
        if self.repos and self.kind == "task":
            body["repos"] = list(self.repos)
        if self.kind != "task":
            body["kind"] = self.kind
        else:
            body["write"] = True
        if self.default and self.kind == "task":
            body["default"] = True
        return body


def _instance_from(url: str) -> str:
    """A name for the host, when the profile does not give one."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host.split(".")[0] if host else "default"


# ── the helper, and the servers that point at it ─────────────────────────
def install_helper(source: Path | None = None,
                   config_dir: Path | None = None) -> Path:
    """Put the headers helper somewhere whose path does not carry a version.

    The shipped copy lives under the plugin cache, whose path contains the
    plugin's version — so a server pointing there stops working at the next
    `claude plugin update`, and the symptom is an authentication failure that
    reads exactly like a revoked token. Copying it out costs five kilobytes.
    """
    config = Path(config_dir or CONFIG_DIR)
    source = Path(source) if source else find_shipped_helper()
    if source is None or not source.is_file():
        raise SetupError(
            "cannot find the shipped `sky-headers`. Install the plugin first, "
            "or pass --helper with the path to it.")
    config.mkdir(parents=True, exist_ok=True)
    target = config / HELPER_FILE
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(target, 0o755)
    return target


def _reads(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def install_launcher(into: Path | None = None,
                     config_dir: Path | None = None) -> tuple[Path, bool]:
    """Put a `sky` on PATH, so the skills' `sky setup doctor` actually works.

    Every skill says `sky …`, and after a plugin-only install there was no
    `sky` — only `<plugin>/bin/sky`, which no skill knows the path to and Codex
    and Kimi could not spell anyway. So `setup init` installs a two-line
    launcher pointing at whichever runtime it is running from.

    Returns the path and whether its directory is actually on PATH; the caller
    says so out loud, because "installed somewhere PATH does not look" is the
    failure this is meant to end, not repeat.

    Returns the launcher; the runtime copy it points at is `config_dir/runtime`.
    """
    # Copy the runtime to a stable place and point at THAT. `__file__` here may
    # be inside `<plugin cache>/<version>/runtime`, whose path contains the
    # version — so a launcher pointing at it breaks on the next plugin update,
    # and the symptom is `sky: command not found` with the file still sitting
    # there. Same lesson as the headers helper, one directory over.
    source = Path(__file__).resolve().parent                 # …/sky
    # **Both destinations come from `config_dir`.** They used to disagree: the
    # launcher honoured `into` while the runtime copy always went to the real
    # `~/.config/sky/runtime`, so anything that redirected the launcher — a
    # test, a second profile, a dry run — still wrote twenty modules into the
    # user's own home. Nothing failed, so nothing said so.
    # One destination, derived in one place. When a caller names only `into`,
    # the runtime goes BESIDE it — not into the user's real config dir, which
    # is what made a redirected launcher still write twenty modules into a home
    # nobody asked it to touch.
    config = Path(config_dir) if config_dir else (
        Path(into).parent if into else CONFIG_DIR)
    runtime = config / "runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    shutil.copytree(source, runtime / "sky")
    target = Path(into or LAUNCHER_DIR) / "sky"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never over a `sky` this did not write. Somebody may have their own, and
    # silently replacing a command on a person's PATH is not ours to do.
    if target.exists() and "Installed by `sky setup init`" not in _reads(target):
        raise SetupError(
            f"{target} already exists and was not written by this tool. It is "
            f"not ours to replace — remove it yourself, or put SKY's launcher "
            f"somewhere else on your PATH.")
    # A Python file with a shebang, not a shell wrapper around `python -c`:
    # the quoting in that version was wrong in a way that only showed up once
    # somebody actually ran the installed command, which is exactly the class
    # of bug this whole exercise is about.
    target.write_text(
        f"#!{sys.executable}\n"
        '"""The `sky` command. Installed by `sky setup init`."""\n'
        "import sys\n"
        f"sys.path.insert(0, {str(runtime)!r})\n"
        "from sky.cli import main\n"
        "sys.exit(main())\n",
        encoding="utf-8")
    os.chmod(target, 0o755)
    on_path = str(target.parent) in os.environ.get("PATH", "").split(os.pathsep)
    return target, on_path


def find_shipped_helper() -> Path | None:
    """Where the shipped helper is, whichever way this was installed.

    `$SKY_PLUGIN_ROOT` comes first because the plugin's own `bin/sky` sets it,
    and that is the case the search used to miss entirely: a plugin installed
    anywhere but the default cache found no helper, and `setup init` refused
    with "install the plugin first" to somebody who just had.
    """
    root = os.environ.get("SKY_PLUGIN_ROOT", "")
    if root:
        candidate = Path(root) / "bin" / HELPER_FILE
        if candidate.is_file():
            return candidate
    # Same order as `hosts.skills_dir`: the repository this runtime lives in
    # beats an unrelated installed copy, and `cache/sky/sky` rather than
    # `cache/*/*/*` so another product's plugin is never picked up.
    here = Path(__file__).resolve().parents[2] / "plugin" / "bin" / HELPER_FILE
    if here.is_file():
        return here
    cached = sorted(Path("~/.claude/plugins/cache/sky/sky").expanduser()
                    .glob(f"*/bin/{HELPER_FILE}"))
    return cached[-1] if cached else None


def server_entry(url: str, helper: Path) -> dict:
    """One user-scoped HTTP server: an address, and where to get the header."""
    return {"type": "http", "url": url, "headersHelper": str(helper)}


def read_servers(path: Path | None = None) -> dict:
    return dict(_read_json(Path(path or CLAUDE_JSON)).get("mcpServers") or {})


def _has_task_server(path: Path | None = None) -> bool:
    """Is a task knowledge base already wired into this session?"""
    return "kb" in read_servers(path)


def collisions(servers: dict, path: Path | None = None) -> dict:
    """Servers already in the user's file that are not ours to replace.

    "Ours" means one pointing at our own helper — anything else is a
    connection the person set up, quite possibly to a different knowledge base,
    and silently overwriting it is how somebody loses access to their own data
    and cannot work out why.
    """
    have = read_servers(path)
    out = {}
    for name in servers:
        current = have.get(name)
        if isinstance(current, dict) and not str(
                current.get("headersHelper", "")).endswith(HELPER_FILE):
            out[name] = current
    return out


def apply_servers(servers: dict, path: Path | None = None,
                  replace: bool = False) -> Path:
    """Merge our servers in, leaving every other one alone.

    Refuses a name already taken by somebody else's server unless told to
    replace it — and when it does replace one, the old entry goes into the
    manifest so `uninstall` can put it back rather than deleting it.

    The file's mode is preserved. It was being recreated at the process
    default, which turned a 600 file into a 644 one — quietly widening read
    access to whatever else the person keeps in it.
    """
    path = Path(path or CLAUDE_JSON)
    if not replace:
        clash = collisions(servers, path)
        if clash:
            raise SetupError(
                "these MCP servers already exist in " + str(path) + " and were "
                "not created by this tool: " + ", ".join(sorted(clash))
                + ". Replacing one would take away a connection you set up. "
                "Re-run with a different --name, or pass --replace-servers if "
                "you really mean to take the name over.")
    body = _read_json(path)
    existing = dict(body.get("mcpServers") or {})
    existing.update(servers)
    body["mcpServers"] = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, mode)
    temporary.replace(path)
    return path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SetupError(
            f"{path} is not valid JSON ({exc}). This is your own file, so it is "
            "not something this will rewrite — fix it and run again.") from exc
    return body if isinstance(body, dict) else {}


@dataclass(frozen=True)
class Change:
    path: Path
    what: str
    #: Rendered for the person. Never contains a token — see the module rules.
    detail: str = ""

    def __str__(self) -> str:
        head = f"  {self.what:<8} {self.path}"
        return head if not self.detail else head + "\n" + self.detail


# ── the manifest: uninstall removes only what init added ─────────────────
def read_manifest(path: Path | None = None) -> dict:
    return _read_json(Path(path or CONFIG_DIR / MANIFEST_FILE))


def write_manifest(body: dict, path: Path | None = None) -> Path:
    path = Path(path or CONFIG_DIR / MANIFEST_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


# ── init ─────────────────────────────────────────────────────────────────
def server_names(profile: Profile) -> dict[str, str]:
    """Which servers this profile needs, and at which address.

    Named `kb` and `code` because that is what the role agents' tool lists
    already say — `mcp__kb__kb_search`. A server named anything else here
    produces tool ids no allowlist mentions, and the agent silently has no
    knowledge base at all, which is a failure this project has already paid
    for twice.
    """
    if profile.kind == "catalogue":
        # `mcp__catalogue__*` is what the role allowlists name for the shared
        # skill library. Registering it as `kb` would both take the task
        # knowledge base's name and hand the agent tool ids no allowlist
        # mentions — the silent-no-tools failure, again.
        return {"catalogue": profile.url}
    names = {"kb": profile.url}
    if profile.code_url:
        names["code"] = profile.code_url
    return names


def plan(profile: Profile, *, config_dir: Path | None = None,
         claude_json: Path | None = None) -> list[Change]:
    """Everything `init` would do, as text, before it does any of it."""
    config = Path(config_dir or CONFIG_DIR)
    changes = [
        Change(config / ENV_FILE,
               "update" if (config / ENV_FILE).exists() else "create",
               f"           {token_variable(profile.instance)}=<the token you "
               f"are about to type>   (mode 600)"),
        Change(config / MAP_FILE,
               "update" if (config / MAP_FILE).exists() else "create",
               f"           + {profile.name}: tenant {profile.tenant}, "
               f"ontology {profile.ontology}, class {profile.privacy}"),
        Change(config / HELPER_FILE,
               "update" if (config / HELPER_FILE).exists() else "create",
               "           a copy of the plugin's headers helper (mode 755)"),
    ]
    path = Path(claude_json or CLAUDE_JSON)
    have = read_servers(path)
    detail = []
    for name, url in server_names(profile).items():
        was = (have.get(name) or {}).get("url")
        detail.append(f"           mcpServers.{name}: "
                      + (f"{was} → {url}" if was else f"+ {url}"))
    changes.append(Change(path, "update" if path.exists() else "create",
                          "\n".join(detail)))
    return changes


def init(profile: Profile, token: str, *, config_dir: Path | None = None,
         claude_json: Path | None = None, helper_source: Path | None = None,
         register: bool = True, replace_servers: bool = False) -> list[Path]:
    """Write the files. The caller has already shown `plan` and had a yes.

    **Everything is checked before anything is written.** An earlier version
    wrote the token and the map and *then* validated, so a profile the runtime
    rejects left a real token and a broken map on disk and reported failure —
    the worst of both. The map is now built in memory, loaded from a temporary
    file to prove it loads, and only then does anything permanent happen.
    """
    if not token.strip():
        raise SetupError("no token was given, so nothing was written")
    config = Path(config_dir or CONFIG_DIR)
    variable = token_variable(profile.instance)
    was = read_manifest(config / MANIFEST_FILE)

    # ── check, in memory ─────────────────────────────────────────────────
    entries = _read_json(config / MAP_FILE)
    if profile.default and profile.kind == "task":
        for body in entries.values():
            if isinstance(body, dict):
                body.pop("default", None)
    entries[profile.name] = profile.entry()
    import tempfile
    probe = Path(tempfile.mkdtemp()) / MAP_FILE
    probe.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    try:
        KBMap.load(probe)
    except KBMapError as exc:
        raise SetupError(
            f"that profile does not make a knowledge-base map the runtime will "
            f"load: {exc}. Nothing was written.") from exc

    servers = {}
    # A session talks to ONE task knowledge base. A second one does not get a
    # second server — it would either take the name `kb` from the first or
    # arrive as tool ids no allowlist mentions. The session-level server
    # follows the default; every other KB is reached per run by `sky build`,
    # which resolves it from the directory. A catalogue is the exception: it is
    # read ALONGSIDE the task KB and has its own name.
    session_server = (profile.kind == "catalogue"
                      or profile.default
                      or not _has_task_server(claude_json))
    if register and not session_server:
        register = False
        servers = {}
    if register:
        helper_src = Path(helper_source) if helper_source else find_shipped_helper()
        if helper_src is None or not Path(helper_src).is_file():
            raise SetupError(
                "cannot find the shipped `sky-headers`. Install the plugin "
                "first, or pass --helper with the path to it. Nothing was "
                "written.")
        servers = {name: server_entry(url, config / HELPER_FILE)
                   for name, url in server_names(profile).items()}
        clash = collisions(servers, claude_json) if not replace_servers else {}
        if clash:
            raise SetupError(
                "these MCP servers already exist in "
                + str(Path(claude_json or CLAUDE_JSON))
                + " and were not created by this tool: "
                + ", ".join(sorted(clash))
                + ". Nothing was written. Re-run with a different --name, or "
                "pass --replace-servers if you really mean to take the name "
                "over — the old entry is then recorded so uninstall restores "
                "it rather than deleting it.")

    # ── write: stage everything, then commit, then roll back on failure ──
    # Validation first is necessary and not sufficient: a disk filling up
    # between the token file and the map still leaves half a setup. Each file
    # is written to a temporary beside it, every original is remembered, and a
    # failure part-way through puts them all back.
    values = read_env(config / ENV_FILE)
    values[variable] = token.strip()
    map_path = config / MAP_FILE
    map_path.parent.mkdir(parents=True, exist_ok=True)
    claude_path = Path(claude_json or CLAUDE_JSON)
    launcher_dir = (config / "bin") if config.resolve() != CONFIG_DIR.resolve() \
        else Path(LAUNCHER_DIR)
    touched = [config / ENV_FILE, map_path, config / HELPER_FILE,
               launcher_dir / "sky", claude_path]
    # The runtime copy is a directory, so it is undone separately — leaving
    # twenty modules behind after a failed setup is the same half-configured
    # machine the rest of this rollback exists to prevent.
    runtime_dir = config / "runtime"
    runtime_existed = runtime_dir.exists()
    previous = {q: q.read_bytes() for q in touched if q.exists()}
    written = []

    def undo(exc):
        """Everything back as it was — every file, not the first two.

        The earlier version rolled back the token and the map and left the
        helper, the launcher and the host's server file wherever the failure
        found them, which is a half-configured machine reported as an error.
        """
        for q, was in previous.items():
            try:
                q.write_bytes(was)
            except OSError:
                pass
        for q in touched:
            if q not in previous and q.exists():
                try:
                    q.unlink()
                except OSError:
                    pass
        if not runtime_existed and runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)
        raise SetupError(f"nothing was changed: {exc}") from exc

    try:
        written.append(write_env(values, config / ENV_FILE))
        map_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        written.append(map_path)
    except OSError as exc:
        undo(exc)

    try:
        # **A redirected setup never touches the real `~/.local/bin`.** If a
        # caller names its own `config_dir` it is not configuring this machine
        # — it is a test, a second profile or a dry run — and installing a
        # command onto the person's PATH from one of those is how a working
        # `sky` ended up pointing at a temporary directory that the operating
        # system would later delete. The launcher follows the configuration.
        redirected = config.resolve() != CONFIG_DIR.resolve()
        launcher, on_path = install_launcher(
            into=(config / "bin") if redirected else None, config_dir=config)
    except (OSError, SetupError) as exc:
        undo(exc)
    written.append(launcher)

    replaced = {}
    if register:
        try:
            written.append(install_helper(helper_src, config))
            replaced = collisions(servers, claude_json)
            written.append(apply_servers(servers, claude_json, replace=True))
        except (OSError, SetupError) as exc:
            undo(exc)

    write_manifest({
        "version": 1,
        "kbs": sorted({profile.name} | set(was.get("kbs", []))),
        "token_variables": sorted({variable} | set(was.get("token_variables", []))),
        "servers": sorted(set(servers) | set(was.get("servers", []))),
        # What each one looked like when written, so uninstall can tell an
        # untouched entry from one the person has since changed.
        "server_entries": {**(was.get("server_entries") or {}), **servers},
        # What was there before, so uninstall puts it back rather than
        # removing a connection this tool did not create.
        "replaced": {**(was.get("replaced") or {}), **replaced},
        "claude_json": str(Path(claude_json or CLAUDE_JSON)),
        "helper": str(config / HELPER_FILE) if register else "",
        "launcher": str(launcher),
        "launcher_on_path": on_path,
    }, config / MANIFEST_FILE)
    return written


def use(name: str, *, config_dir: Path | None = None,
        claude_json: Path | None = None) -> str:
    """Point this session's `kb` server at another knowledge base in the map.

    A session talks to one task knowledge base, and `sky build` picks the right
    one per run from the directory. An *interactive* session has no such
    moment, so switching was documented and not implemented — a person on a
    second project had no way to do it but edit JSON by hand.

    Refuses a catalogue, for the same reason `resolve` does: it holds skills
    and no project knowledge.
    """
    config = Path(config_dir or CONFIG_DIR)
    kbs = KBMap.load(config / MAP_FILE)
    chosen = kbs.get(name)
    if chosen.is_catalogue:
        raise SetupError(
            f"{name!r} is the shared skill catalogue, not a task knowledge "
            f"base. It is read alongside whichever KB you are using; it cannot "
            f"be the one you work against.")
    helper = config / HELPER_FILE
    if not helper.is_file():
        raise SetupError(f"no helper at {helper} — run `sky setup init` first")
    apply_servers({"kb": server_entry(chosen.url, helper)},
                  claude_json, replace=True)
    return (f"this session's knowledge base is now {chosen.name} "
            f"(tenant {chosen.tenant}). Restart Claude for it to take effect.")


# ── rotate ───────────────────────────────────────────────────────────────
def rotate(instance: str, token: str, *, config_dir: Path | None = None) -> Path:
    """One instance's token, replaced. Everything else in the file untouched."""
    if not token.strip():
        raise SetupError("no token was given, so nothing was changed")
    config = Path(config_dir or CONFIG_DIR)
    variable = token_variable(instance)
    values = read_env(config / ENV_FILE)
    if variable not in values:
        known = ", ".join(sorted(k for k in values if k.startswith("SKY_PAT_"))) or "none"
        raise SetupError(
            f"{variable} is not in {config / ENV_FILE}, so there is nothing to "
            f"rotate for instance {instance!r}. Token variables there: {known}")
    if values[variable] == token.strip():
        raise SetupError(
            "that is the token already stored. Rotation means a new one — the "
            "old value stays valid until you revoke it at the source.")
    values[variable] = token.strip()
    return write_env(values, config / ENV_FILE)


# ── doctor ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    ok: bool
    name: str
    detail: str

    def __str__(self) -> str:
        return f"{'ok  ' if self.ok else 'FAIL'}  {self.name:<28} {self.detail}"


def doctor(*, config_dir: Path | None = None,
           claude_json: Path | None = None) -> list[Finding]:
    """Is the configuration sound? Not "is the KB alive" — that is `sky doctor`.

    The split is deliberate. This answers questions a person fixes with a text
    editor in ten seconds; the readiness probes answer questions about a running
    system. Mixed into one table, a typo and an outage look the same.
    """
    config = Path(config_dir or CONFIG_DIR)
    out: list[Finding] = []
    values: dict[str, str] = {}

    env_path = config / ENV_FILE
    if not env_path.exists():
        out.append(Finding(False, "token file",
                           f"{env_path} does not exist — run `sky setup init`"))
    else:
        mode = stat.S_IMODE(env_path.stat().st_mode)
        out.append(Finding(mode == 0o600, "token file permissions",
                           f"{oct(mode)[2:]} on {env_path}"
                           + ("" if mode == 0o600 else " — should be 600")))
        try:
            values = read_env(env_path)
        except SetupError as exc:
            out.append(Finding(False, "token file", str(exc)))
        else:
            named = sorted(k for k in values if k.startswith("SKY_PAT_"))
            # Counted and named. Never shown.
            out.append(Finding(bool(named), "tokens",
                               ", ".join(named) if named
                               else "no SKY_PAT_* variable is set"))
            empty = sorted(k for k in named if not values[k])
            if empty:
                out.append(Finding(False, "empty tokens", ", ".join(empty)
                                   + " — set but blank, which fails exactly as "
                                   "though the token had been revoked"))

    try:
        kbs = KBMap.load(config / MAP_FILE)
    except KBMapError as exc:
        out.append(Finding(False, "kb map", str(exc)))
        kbs = None
    else:
        out.append(Finding(True, "kb map",
                           f"{len(kbs)} entr{'y' if len(kbs) == 1 else 'ies'}: "
                           + ", ".join(kbs.names())))
        for kb in kbs:
            if not kb.pat_env:
                out.append(Finding(False, f"kb {kb.name}",
                                   "names no token variable (pat_env)"))
            elif kb.pat_env not in values:
                out.append(Finding(False, f"kb {kb.name}",
                                   f"wants ${kb.pat_env}, which {env_path} "
                                   f"does not have"))

    helper = config / HELPER_FILE
    if not helper.is_file():
        out.append(Finding(False, "headers helper",
                           f"{helper} is missing — run `sky setup init`"))
    else:
        runnable = os.access(helper, os.X_OK)
        out.append(Finding(runnable, "headers helper",
                           str(helper) if runnable else
                           f"{helper} is not executable, so the host cannot run it"))

    path = Path(claude_json or CLAUDE_JSON)
    servers = read_servers(path)
    ours = {n: s for n, s in servers.items()
            if isinstance(s, dict) and str(s.get("headersHelper", "")).endswith(HELPER_FILE)}
    out.append(Finding(bool(ours), "registered servers",
                       ", ".join(sorted(ours)) + f" in {path}" if ours else
                       f"no server in {path} uses the helper — the plugin's own "
                       f"servers cannot authenticate on their own"))

    if kbs is not None:
        known = {kb.url for kb in kbs}
        for name, server in sorted(ours.items()):
            url = server.get("url", "")
            if name == "kb" and url not in known:
                out.append(Finding(False, f"server {name}",
                                   f"{url} is not any KB's mcp_url — the session "
                                   f"would reach a host the map does not describe"))
            stale = str(server.get("headersHelper", ""))
            if stale and not Path(stale).is_file():
                out.append(Finding(False, f"server {name}",
                                   f"its helper {stale} no longer exists"))
    return out


# ── uninstall ────────────────────────────────────────────────────────────
def uninstall(*, config_dir: Path | None = None, claude_json: Path | None = None,
              remove_tokens: bool = False) -> list[str]:
    """Undo what the manifest records, and nothing else.

    Tokens are kept unless asked for explicitly: a token is minted by hand at
    the source, and the usual reason to uninstall is to install again.
    """
    config = Path(config_dir or CONFIG_DIR)
    manifest = read_manifest(config / MANIFEST_FILE)
    if not manifest:
        raise SetupError(
            f"no manifest at {config / MANIFEST_FILE}, so there is no record of "
            "what was added. Nothing was removed — remove by hand rather than "
            "have this guess.")
    done = []

    path = Path(claude_json or manifest.get("claude_json") or CLAUDE_JSON)
    named = list(manifest.get("servers") or [])
    if named and path.exists():
        body = _read_json(path)
        servers = dict(body.get("mcpServers") or {})
        # Only if it is still OURS. A person who re-pointed `kb` at a
        # different knowledge base after setup should not lose it because they
        # later ran uninstall — at that point the entry is theirs, not ours.
        helper = str(manifest.get("helper") or "")
        removed, kept = [], []
        for n in named:
            current = servers.get(n)
            if not isinstance(current, dict):
                continue
            # The whole entry, not just the helper: a person who re-pointed
            # the URL at another knowledge base still has a server that is
            # theirs now, and comparing one field missed exactly that.
            installed = (manifest.get("server_entries") or {}).get(n)
            if installed and current != installed:
                kept.append(n)
                continue
            if not installed and helper and str(
                    current.get("headersHelper", "")) != helper:
                kept.append(n)
                continue
            removed.append(n)
        for n in kept:
            done.append(f"kept {n} in {path} — it has been changed since setup, "
                        f"so it is yours now")
        for name in removed:
            servers.pop(name)
        # Put back anything this tool took the name of, rather than leaving
        # the person without a connection they had before they met us.
        restored = {n: e for n, e in (manifest.get("replaced") or {}).items()
                    if n in removed}
        servers.update(restored)
        if removed:
            if servers:
                body["mcpServers"] = servers
            else:
                body.pop("mcpServers", None)
            if restored:
                done.append("restored " + ", ".join(sorted(restored))
                            + " to what it was before setup")
            path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
            done.append(f"removed server(s) {', '.join(removed)} from {path}")

    launcher = manifest.get("launcher")
    if launcher and Path(launcher).is_file():
        Path(launcher).unlink()
        done.append(f"removed {launcher}")

    runtime_dir = config / "runtime"
    if runtime_dir.is_dir():
        shutil.rmtree(runtime_dir, ignore_errors=True)
        done.append(f"removed {runtime_dir}")

    for name in (MAP_FILE, HELPER_FILE):
        target = config / name
        if target.exists():
            target.unlink()
            done.append(f"removed {target}")

    env_path = config / ENV_FILE
    if env_path.exists():
        if remove_tokens:
            env_path.unlink()
            done.append(f"removed {env_path}")
        else:
            done.append(f"kept {env_path} — pass --remove-tokens to delete it")

    (config / MANIFEST_FILE).unlink(missing_ok=True)
    return done
