"""Which knowledge base a task uses, and how to reach it.

One entry per KB. A KB is one knowledge-base tenant: an address, a tenant code,
an ontology. It is memory and knowledge and nothing else — the brain is the
whole assembly, of which this is one part.

The resolution order is fixed and it matters:

    the repository's path  ->  an explicit override  ->  the default

and there is one rule that is not a convenience:

    **A repository belonging to a KB of one privacy class never falls back to a
    default of another.** It gets no KB and a clear message.

That rule exists because the failure it prevents is silent. Without it, running
a skill inside a client repository whose KB is unreachable would quietly answer
from the team's own KB — mixing two bodies of knowledge that must not mix, and
looking exactly like success while doing it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("SKY_CONFIG_DIR", "~/.config/sky")).expanduser()
MAP_FILE = "kb-map.json"

# A name is what a person types after `/sky:kb`, and it is also the key that
# joins a skill document to its usage records in the graph. Keep it plain.
_NAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_")

PRIVACY_CLASSES = ("personal", "work", "client")


class KBMapError(Exception):
    """Something about the map itself is wrong. Always actionable."""


class NoKBForPath(KBMapError):
    """Deliberate refusal: a path that must not use the KB on offer."""


@dataclass(frozen=True)
class KB:
    name: str
    purpose: str
    url: str
    tenant: str
    ontology: str
    privacy: str
    write: bool = False
    code_url: str = ""
    pat_env: str = ""
    hints: tuple[str, ...] = ()
    repos: tuple[Path, ...] = ()
    default: bool = False
    #: "task" — a knowledge base a run works against, chosen by repository.
    #: "catalogue" — the shared skill library, reached ALONGSIDE the task KB
    #: and never instead of it. A catalogue is never returned by `resolve`,
    #: not even with `--kb`: it holds no project knowledge, so selecting it as
    #: a task KB would give a run a library and no context.
    kind: str = "task"

    @property
    def is_catalogue(self) -> bool:
        return self.kind == "catalogue"

    def token(self) -> str:
        """The token, from the environment variable this KB names.

        The map holds the variable's NAME, never its value — so the map can be
        read, diffed and shared without carrying a secret.
        """
        if not self.pat_env:
            raise KBMapError(f"KB {self.name!r} names no token variable (pat_env)")
        value = os.environ.get(self.pat_env, "")
        if not value:
            raise KBMapError(
                f"KB {self.name!r} needs ${self.pat_env}, which is not set. "
                f"It belongs in {CONFIG_DIR / 'env'}."
            )
        return value


def _as_kb(name: str, raw: dict) -> KB:
    bad = set(name) - _NAME_OK
    if bad:
        raise KBMapError(
            f"KB name {name!r} contains {''.join(sorted(bad))!r}. "
            "Use lower-case letters, digits and underscores — the name is typed "
            "by people and is matched exactly when joining records in the graph."
        )
    missing = [k for k in ("mcp_url", "tenant_code", "ontology", "privacy") if not raw.get(k)]
    if missing:
        raise KBMapError(f"KB {name!r} is missing {', '.join(missing)}")
    privacy = raw["privacy"]
    if privacy not in PRIVACY_CLASSES:
        raise KBMapError(
            f"KB {name!r} has privacy {privacy!r}; expected one of "
            f"{', '.join(PRIVACY_CLASSES)}"
        )
    kind = str(raw.get("kind", "task"))
    if kind not in ("task", "catalogue"):
        raise KBMapError(
            f"KB {name!r} has kind {kind!r}; it must be 'task' or 'catalogue'.")
    if kind == "catalogue":
        if raw.get("write"):
            raise KBMapError(
                f"KB {name!r} is a catalogue and has write: true. A catalogue is "
                "read alongside a task KB, so a writable one is a way for one "
                "project's work to end up in everybody's library.")
        if raw.get("default"):
            raise KBMapError(
                f"KB {name!r} is a catalogue and is marked default. A catalogue "
                "is never the KB a task resolves to.")
        if _repo_list(raw):
            # `resolve` refuses a catalogue given as an override, but a
            # catalogue that OWNS a directory was reached by `owner_of` before
            # the override check ever ran — so a run in that directory got the
            # skill library as its task knowledge base and nothing to work on.
            raise KBMapError(
                f"KB {name!r} is a catalogue and lists repository paths. A "
                "catalogue owns no repository: it is read alongside whichever "
                "KB a directory resolves to, never instead of it.")

    if privacy == "personal" and not _is_local(raw["mcp_url"]):
        raise KBMapError(
            f"KB {name!r} is class 'personal' but lives at {raw['mcp_url']}. "
            "A personal KB stays on this machine."
        )
    return KB(
        name=name,
        purpose=raw.get("purpose", ""),
        url=raw["mcp_url"],
        tenant=raw["tenant_code"],
        ontology=raw["ontology"],
        privacy=privacy,
        write=bool(raw.get("write", False)),
        code_url=raw.get("code_url", ""),
        pat_env=raw.get("pat_env", ""),
        hints=tuple(h.lower() for h in raw.get("hints", ())),
        repos=tuple(Path(p).expanduser().resolve() for p in _repo_list(raw)),
        default=bool(raw.get("default", False)),
        kind=kind,
    )


def _repo_list(raw: dict) -> list[str]:
    repos = list(raw.get("repos", ()))
    if raw.get("repo"):
        repos.append(raw["repo"])
    return repos


#: Hosts that really are this machine. Compared exactly against the parsed
#: hostname — `https://localhost.evil.example/` starts with "https://localhost"
#: and is somebody else's server entirely.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})


def _is_local(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in LOCAL_HOSTS


class KBMap:
    """The loaded map, and the resolution rules over it."""

    def __init__(self, entries: dict[str, KB]):
        if not entries:
            raise KBMapError("the KB map is empty — run `sky setup init` first")
        self._entries = entries
        defaults = [k for k in entries.values() if k.default]
        if len(defaults) > 1:
            raise KBMapError(
                "more than one KB is marked default: "
                + ", ".join(k.name for k in defaults)
            )
        self._default = defaults[0] if defaults else None
        catalogues = [k for k in entries.values() if k.is_catalogue]
        if len(catalogues) > 1:
            raise KBMapError(
                "more than one KB is marked kind: catalogue — there is one shared "
                "skill library, not several: "
                + ", ".join(k.name for k in catalogues))
        self._catalogue = catalogues[0] if catalogues else None

    # ── loading ──────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: Path | None = None) -> "KBMap":
        path = path or (CONFIG_DIR / MAP_FILE)
        if not path.exists():
            raise KBMapError(
                f"no KB map at {path}. Run `sky setup init` with the profile your "
                "administrator sent you."
            )
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise KBMapError(f"{path} is not valid JSON: {exc}") from exc
        return cls({
            name: _as_kb(name, body)
            for name, body in raw.items()
            if not name.startswith("_")           # `_comment` and friends
        })

    # ── access ───────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries.values())

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def names(self) -> list[str]:
        return sorted(self._entries)

    def catalogue(self) -> KB | None:
        """The shared skill library, if this machine is configured with one.

        Reached *alongside* whatever KB the task resolves to, never instead of
        it. None is an ordinary answer: a user with no catalogue simply has no
        skill discovery, and everything else works.
        """
        return self._catalogue

    def get(self, name: str) -> KB:
        try:
            return self._entries[name]
        except KeyError:
            raise KBMapError(
                f"no KB called {name!r}. This map has: {', '.join(self.names())}"
            ) from None

    # ── resolution ───────────────────────────────────────────────────────
    def owner_of(self, path: Path) -> KB | None:
        """The KB that owns a directory, by the longest matching repo path.

        Longest wins so a repository nested inside another — a POC beside its
        main checkout — resolves to the more specific one.
        """
        path = Path(path).expanduser().resolve()
        best: KB | None = None
        best_len = -1
        for kb in self._entries.values():
            if kb.is_catalogue:
                continue            # belt and braces; `_as_kb` refuses the data
            for repo in kb.repos:
                if path == repo or repo in path.parents:
                    if len(repo.parts) > best_len:
                        best, best_len = kb, len(repo.parts)
        return best

    def resolve(self, cwd: Path | None = None, override: str | None = None) -> KB:
        """Which KB this task uses: repository path, then override, then default.

        Raises NoKBForPath rather than crossing a privacy boundary — see the
        module docstring for why that is a refusal and not an inconvenience.
        """
        cwd = Path(cwd or Path.cwd()).expanduser().resolve()
        owner = self.owner_of(cwd)

        if override:
            chosen = self.get(override)
            if chosen.is_catalogue:
                # Not a preference. A catalogue holds skills and no project
                # knowledge, so a run pointed at one has a library and nothing
                # to work on — and would then be one write away from putting
                # this project's material in everybody's library.
                raise NoKBForPath(
                    f"{chosen.name!r} is the shared skill catalogue, not a task "
                    f"knowledge base. It is read alongside whichever KB this "
                    f"directory resolves to; it cannot be the one a task uses.")
            if owner and owner.privacy != chosen.privacy:
                raise NoKBForPath(
                    f"{cwd} belongs to {owner.name!r} (class {owner.privacy!r}), "
                    f"and {chosen.name!r} is class {chosen.privacy!r}. "
                    "Crossing privacy classes needs a deliberate move, not a flag: "
                    "work outside that repository, or change what owns it."
                )
            return chosen

        if owner:
            return owner

        if self._default is None:
            raise KBMapError(
                "no KB owns this directory and no default is set. Add a repos entry, "
                "mark one KB default, or pass --kb."
            )

        # Nothing owns this path. That is fine for a scratch directory, but NOT
        # if a non-work KB is the only thing that could have owned it — see the
        # rule in the module docstring.
        if self._default.privacy != "work":
            raise NoKBForPath(
                f"nothing owns {cwd}, and the default KB {self._default.name!r} is "
                f"class {self._default.privacy!r}. Falling back into a "
                f"{self._default.privacy} KB from an unknown directory is not "
                "something this will do by accident — pass --kb to say you meant it."
            )
        return self._default

    def by_hint(self, text: str) -> KB | None:
        """A keyword in the ask that pins the KB with no model call at all."""
        low = text.lower()
        for kb in self._entries.values():
            if kb.is_catalogue:
                # Same rule as `resolve`: a catalogue holds skills and no
                # project knowledge, so a task pinned to one has a library and
                # nothing to work on. A hint is a shortcut past the resolution
                # order, not past its rules.
                continue
            if any(h in low for h in kb.hints):
                return kb
        return None
