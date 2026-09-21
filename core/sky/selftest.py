"""Is this repository still the thing it claims to be?

Every check here exists because something drifted once, or would drift
silently. They fall into two groups:

**Does it hold together** — the policy lints, the agent files match the policy,
the published schemas match the code. These are drift checks, and each has a
matching `sync` or `publish` command that fixes what it reports.

**Is anything in `plugin/` that must not leave this machine** — a URL, a
credential, somebody's home directory, one organisation's vocabulary. `plugin/`
is the only thing that reaches a teammate's machine (gate G11), so it is the
only thing this scans, and a mistake here is published rather than local.

Two rules learned elsewhere and applied here:

*A false positive is not free.* The word "widgets" contains "widget"; a substring
scan for an organisation's name flags four ordinary sentences in this very
repository. A check people learn to ignore is not a check, so matching is on
word boundaries and the test suite carries a corpus that must NOT match.

*Say what was not checked.* The organisation-specific vocabulary cannot live in
this file — core ships, and a list of one company's names shipping inside the
tool that removes them would be absurd. It is read from a local file, and when
that file is absent this says so rather than reporting a clean run it did not
perform.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import redaction

#: Optional, local, never committed: one word or phrase per line, `#` comments
#: allowed. Anything listed must not appear in `plugin/`.
WORDS_FILE = "~/.config/sky/selftest-words"

#: A URL in shipped content pins the plugin to one deployment. The config
#: placeholders are how a URL is *supposed* to be written.
_URL = re.compile(r"https?://(?!(?:example|localhost)\b)[a-zA-Z0-9.-]+")
_PLACEHOLDER_URL = re.compile(r"\$\{[A-Z_]+\}|<[^>]+>")

#: Someone's home directory. Ships fine, works nowhere else.
_HOME_PATH = re.compile(r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9._-]+")

#: Names this product used to use. Unlike the organisation's vocabulary these
#: are product facts, so they live here rather than in a local file. Each one
#: was found in shipped content after the rename was believed finished.
RETIRED_NAMES = {
    "brain-map": "the KB map — `kb-map.json`",
    "BRAIN_MAP": "`SKY_KB_MAP`",
    "architect-reviewer": "the `architect` and `reviewer` agents, which it was split into",
    # The 2026-09-16 rename. Retired for the same reason as the two above: the
    # old words are still in everybody's fingers, in the backups and in three
    # changelog entries, and a rename is only finished when the old name can no
    # longer come back without something saying so.
    "VAI_HARNESS": "Skynet Harness",
    "vai_harness": "`skynet-harness`",
}

#: Retired **prefixes**, which is a different match. `RETIRED_NAMES` requires a
#: word boundary on both sides — right for a whole name like `brain-map`, and
#: useless for a fragment: `VAI_` is always followed by a word character, so
#: `VAI_KB_URL` never matched it. Three rules written that way were decoration,
#: caught by testing each one against a relapse instead of trusting the table.
RETIRED_PREFIXES = {
    "VAI_": "`SKY_`",
    "mcp__plugin_vai_": "`mcp__plugin_sky_`",
    "/vai:": "`/sky:`",
    "vai-": "`sky-` (the shipped scripts are `sky-guard`, `sky-headers`, …)",
}

#: Retired *sources*, not retired words. CLAUDE.md is a real convention and
#: `learn` correctly tells a developer to record a team rule there — so the
#: pattern is "tenant or ontology, read from CLAUDE.md", not the filename.
#: The first version of this check flagged that legitimate instruction, which
#: is how a check earns being switched off.
RETIRED_SOURCES = (
    (re.compile(r"(?i)(tenant_code|ontology)[^.\n]{0,40}\bCLAUDE\.md"),
     "the tenant and ontology come from $SKY_TENANT / $SKY_ONTOLOGY, then the KB map"),
)

#: A knowledge-base tenant is eight upper-case alphanumerics, and always
#: contains at least one digit — which is what separates one from an ordinary
#: shouted word like REQUIRED or ADDITIVE.
_TENANT = re.compile(r"\b(?=[A-Z0-9]{8}\b)(?=[A-Z0-9]*\d)[A-Z0-9]{8}\b")


def _published(root: Path):
    """Everything that reaches a teammate's machine.

    `plugin/` is what the install cache holds (gate G11). The marketplace file
    is fetched from the repository itself when someone adds the marketplace, so
    it is published too even though it sits outside `plugin/`.
    """
    yield from _files(root / "plugin")
    marketplace = root / ".claude-plugin" / "marketplace.json"
    if marketplace.is_file():
        yield marketplace


@dataclass
class Result:
    name: str
    passed: bool
    detail: str = ""
    problems: list[str] = field(default_factory=list)
    #: True when the check could not run at all. Distinguished from a pass,
    #: because "nothing was checked" and "nothing was wrong" are different
    #: claims and only one of them is reassuring.
    skipped: bool = False

    def __str__(self) -> str:
        mark = "SKIP" if self.skipped else ("ok  " if self.passed else "FAIL")
        head = f"{mark}  {self.name:<34} {self.detail}"
        return "\n".join([head] + [f"          {p}" for p in self.problems])


#: The vendored runtime is code, and two of the scans below would be reading
#: their own rule tables out of it — `selftest.py` lists every retired name by
#: definition, and `probes.py` must say `kb_search` because that is what the
#: platform calls its tools. Prose checks skip it. The credential and endpoint
#: checks do NOT: a token or a real address in the runtime would ship.
RUNTIME_DIR = ("runtime",)


def _authored(root: Path):
    """Published files a person wrote, for the checks that are about wording."""
    for path in _published(root):
        if not any(part in RUNTIME_DIR for part in path.parts):
            yield path


def _files(root: Path):
    """Shipped text files. Skips caches and anything not meant to be read.

    Called with `plugin/`, and separately with the repository's own
    `.claude-plugin/` — the marketplace file is fetched from the repository, so
    it reaches a teammate even though gate G11 showed the install cache holds
    only `plugin/`.
    """
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in (".png", ".jpg", ".gif", ".pdf", ".pyc"):
            continue
        yield path


# ── does it hold together ────────────────────────────────────────────────
def check_shape(root: Path) -> Result:
    wanted = ("core", "plugin", "schemas", "hosts", "docs")
    missing = [d for d in wanted if not (root / d).is_dir()]
    if missing:
        return Result("repository shape", False,
                      f"{len(missing)} missing", [f"no {d}/" for d in missing])
    return Result("repository shape", True, f"{', '.join(wanted)}")


def check_the_wall(root: Path) -> Result:
    """`core/` must never import from `plugin/`.

    That wall is what lets Ethan reuse the runtime without taking the content.
    It is one grep, and it is the kind of thing that is true until somebody is
    in a hurry.
    """
    offenders = []
    for path in (root / "core").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(?:from|import)\s+plugin\b", line):
                offenders.append(f"{path.relative_to(root)}:{n}  {line.strip()}")
    return Result("core does not import plugin", not offenders,
                  "the wall holds" if not offenders else f"{len(offenders)} import(s)",
                  offenders)


def check_policy(root: Path) -> Result:
    from .policy import Policy, PolicyError
    try:
        policy = Policy.load(root / "plugin" / "policy.yaml")
    except PolicyError as exc:
        return Result("policy holds together", False, "did not load",
                      str(exc).splitlines())
    return Result("policy holds together", True,
                  f"{len(policy.roles)} roles, {len(policy.actions)} actions")


def check_agents(root: Path) -> Result:
    from .policy import Policy, PolicyError
    try:
        policy = Policy.load(root / "plugin" / "policy.yaml")
    except PolicyError:
        return Result("agent allowlists match the policy", False,
                      "the policy did not load")
    drifted = policy.sync_agents(root / "plugin" / "agents", write=False)
    return Result("agent allowlists match the policy", not drifted,
                  f"{len(policy.roles)} agents" if not drifted
                  else "run `sky policy sync-agents`", drifted)


def agent_tools(path: Path) -> list[str]:
    """The `tools:` line of one agent file, as a list. Empty when it has none."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("tools:"):
            return [t.strip() for t in line[len("tools:"):].split(",") if t.strip()]
    return []


def plugin_servers(root: Path) -> tuple[str, tuple[str, ...]]:
    """The plugin's own name, and the MCP servers its `.mcp.json` declares.

    Read rather than hardcoded, so a third server added tomorrow is covered
    without anyone remembering to update this file.
    """
    import json
    name = ""
    manifest = root / "plugin" / ".claude-plugin" / "plugin.json"
    if manifest.is_file():
        try:
            name = str(json.loads(manifest.read_text(encoding="utf-8")).get("name") or "")
        except ValueError:
            name = ""
    mcp = root / "plugin" / ".mcp.json"
    if not name or not mcp.is_file():
        return name, ()
    try:
        body = json.loads(mcp.read_text(encoding="utf-8"))
    except ValueError:
        return name, ()
    return name, tuple(sorted(body.get("mcpServers") or {}))


def check_both_tool_spellings(root: Path) -> Result:
    """One server, two tool names — and an agent must name both.

    A tool's id is `mcp__<server>__<tool>`, and **the server's name depends on
    how the session started.** The plugin's own `.mcp.json` calls its servers
    `kb` and `code`; the host namespaces a plugin's servers, so in a session
    started from the installed plugin those arrive as `mcp__plugin_sky_kb__*`.
    Core's `--mcp-config` writes a top-level server also called `kb`, which
    stays `mcp__kb__*`. Same server, two names, decided by the launch path.

    An allowlist naming only one of them **fails silently**: the host drops
    every tool it does not recognise, so the agent starts with no knowledge
    base and truthfully reports that it cannot find anything — which reads as
    an empty knowledge base, not a broken allowlist. That is why it cost two
    rounds to find, and why it then happened a second time.

    Both instances are the reason this exists: once in `policy.yaml`, for the
    four role agents, and once in `context-retriever`, which `check_agents`
    cannot see because it is not a policy role. This check covers every agent
    file, generated or hand-written.

    `catalogue` is deliberately **not** paired. Core creates it and the plugin
    never does, so it has one spelling and only one; pairing it would demand a
    tool name that can never exist.
    """
    name = "agents name both tool spellings"
    plugin, servers = plugin_servers(root)
    if not servers:
        return Result(name, True, "the plugin declares no MCP servers of its "
                                  "own, so there is no second spelling to hold",
                      skipped=True)

    problems, pairs = [], 0
    for path in sorted((root / "plugin" / "agents").glob("*.md")):
        tools = agent_tools(path)
        if not tools:
            continue
        for server in servers:
            core_side = {t.split("__", 2)[2] for t in tools
                         if t.startswith(f"mcp__{server}__")}
            host_side = {t.split("__", 2)[2] for t in tools
                         if t.startswith(f"mcp__plugin_{plugin}_{server}__")}
            if not core_side and not host_side:
                continue                       # this agent does not use it
            pairs += 1
            for held, missing_from, gap in (
                    (host_side, f"mcp__{server}__", host_side - core_side),
                    (core_side, f"mcp__plugin_{plugin}_{server}__", core_side - host_side)):
                if gap:
                    shown = ", ".join(sorted(gap)[:3])
                    more = f", +{len(gap) - 3} more" if len(gap) > 3 else ""
                    problems.append(
                        f"{path.name}  {server}: {len(gap)} tool(s) have no "
                        f"{missing_from}* twin — {shown}{more}")

    return Result(name, not problems,
                  f"{pairs} agent/server pair(s), both spellings" if not problems
                  else "an agent is blind on one launch path", problems)


def check_skills_read_configuration(root: Path) -> Result:
    """A skill must not have this installation's values written into it.

    Three things belong to the person running the plugin, not to the plugin:
    which tenant, which ontology, and what a ticket id looks like. A skill that
    names one of them ships one team's setup to everybody.

    And one that names a single MCP tool spelling — `mcp__kb__kb_search` or
    `mcp__plugin_sky_kb__kb_search` — is the same silent failure that has
    already been paid for in the policy and in an agent file: the tool is
    absent rather than refused, so the model concludes the knowledge base is
    empty. Skills name the bare tool and read `CONFIG.md` for the prefix.

    The `CONFIG.md` file itself is exempt: explaining both spellings is its job.
    """
    name = "skills hold no local configuration"
    directory = root / "plugin" / "skills"
    if not directory.is_dir():
        return Result(name, True, "no skills directory", skipped=True)

    ticket = re.compile(r"\b[A-Z]{2,}-(?:\d+|x{2,})\b")
    problems, checked = [], 0
    for path in sorted(directory.glob("*/SKILL.md")):
        checked += 1
        body = path.read_text(encoding="utf-8")
        uses_kb = "kb_" in body
        for n, line in enumerate(body.splitlines(), 1):
            if line.lstrip().startswith(">"):
                continue                      # the Configuration block explains them
            if "mcp__" in line:
                problems.append(f"{path.parent.name}:{n} names one session's tool "
                                f"spelling; use the bare tool name")
            found = ticket.search(line)
            if found and found.group(0) not in ("SKY-",):
                problems.append(f"{path.parent.name}:{n} has the ticket id "
                                f"{found.group(0)!r}; the prefix is configuration")
        if uses_kb and "CONFIG.md" not in body:
            problems.append(f"{path.parent.name} uses the knowledge base but does "
                            f"not point at CONFIG.md")
        # Shape: the host reads these two fields, and a skill whose `name`
        # disagrees with its directory is invoked by a name nobody will guess.
        head = body.split("---", 2)
        front = head[1] if body.startswith("---") and len(head) > 2 else ""
        declared = ""
        for line in front.splitlines():
            if line.startswith("name:"):
                declared = line.split(":", 1)[1].strip()
        if not declared:
            problems.append(f"{path.parent.name} has no `name:` in its front matter")
        elif declared != path.parent.name:
            problems.append(f"{path.parent.name} declares name {declared!r}")
        if "description:" not in front:
            problems.append(f"{path.parent.name} has no `description:` — the host "
                            f"selects a skill by it, so it is not optional")
    for shipped in ("CONFIG.md", "SKILLS.md"):
        if not (root / "plugin" / shipped).is_file():
            problems.append(f"plugin/{shipped} is missing — the skills rest on it")
    return Result(name, not problems,
                  f"{checked} skills" if not problems
                  else f"{len(problems)} place(s) carry local configuration",
                  problems)


def check_vendored_runtime(root: Path) -> Result:
    """The plugin ships a copy of the runtime; it must not have drifted.

    A plugin-only install has no `core/`, so the runtime is vendored into
    `plugin/runtime/sky`. `core/sky` is the one source of truth and this is the
    check that keeps the copy honest — the same shape as the published-schema
    check, and for the same reason: two copies of anything means one of them is
    quietly wrong, and it is always the one nobody looks at.
    """
    name = "the plugin's runtime matches core"
    source = root / "core" / "sky"
    target = root / "plugin" / "runtime" / "sky"
    if not source.is_dir():
        return Result(name, True, "no core/ here", skipped=True)
    if not target.is_dir():
        return Result(name, False,
                      "the plugin ships no runtime — run scripts/vendor-runtime.py",
                      ["plugin/runtime/sky is missing, so a plugin-only install "
                       "has no `sky` at all"])
    wanted = {p.name: p.read_text(encoding="utf-8")
              for p in sorted(source.glob("*.py"))}
    have = {p.name: p.read_text(encoding="utf-8")
            for p in sorted(target.glob("*.py"))}
    problems = [f"{n} is missing from the plugin" for n in sorted(wanted)
                if n not in have]
    problems += [f"{n} has drifted" for n in sorted(wanted)
                 if n in have and have[n] != wanted[n]]
    problems += [f"{n} is in the plugin and not in core" for n in sorted(have)
                 if n not in wanted]
    return Result(name, not problems,
                  f"{len(wanted)} modules" if not problems
                  else "run scripts/vendor-runtime.py", problems)


def _front_matter(body: str) -> dict:
    """`name` and `description` out of a skill's front matter."""
    if not body.startswith("---"):
        return {}
    head = body.split("---", 2)
    if len(head) < 3:
        return {}
    out = {}
    for line in head[1].splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


#: Words a person actually types, pulled out of a description's quoted
#: examples. Two skills claiming the same one is the ambiguity that leaves the
#: host guessing between them.
_QUOTED = re.compile(r'"([^"]{4,60})"')


def check_skills_can_be_found(root: Path) -> Result:
    """A skill the host cannot choose is a skill nobody has.

    Only `name` and `description` are read until one matches — that is what
    keeps twenty skills out of the context, and it means the description is the
    whole of how a skill gets selected. So it must say **what it does** and
    **when to use it, in the words a person would type**, and no two may claim
    the same trigger.

    This is a real failure mode and not a style preference: "helps with
    content" and "creates marketing assets" both describe the same request and
    name no trigger at all, so which one runs is a coin toss the user cannot
    see.
    """
    name = "skills say when to use them"
    directory = root / "plugin" / "skills"
    if not directory.is_dir():
        return Result(name, True, "no skills directory", skipped=True)

    problems, triggers = [], {}
    skills = sorted(directory.glob("*/SKILL.md"))
    for path in skills:
        front = _front_matter(path.read_text(encoding="utf-8"))
        skill = path.parent.name
        description = front.get("description", "")
        if not description:
            problems.append(f"{skill} has no description")
            continue
        # The requirement is that a description names the words a person would
        # actually type — a quoted example does that as well as the phrase
        # "use when" does, and better. Testing for one fixed wording flagged
        # three skills that already said when, including one whose description
        # begins "Use only when the user explicitly asks".
        low = description.lower()
        says_when = "use when" in low or "use for" in low or "use only when" in low \
            or "use this when" in low
        quoted = _QUOTED.findall(description)
        if not (says_when or quoted):
            problems.append(f"{skill} never says WHEN to use it — name the "
                            f"words a person would type, in quotes, or write "
                            f"\"Use when the user asks …\"")
        for phrase in _QUOTED.findall(description):
            key = " ".join(phrase.lower().split())
            if key in triggers and triggers[key] != skill:
                problems.append(f"{skill} and {triggers[key]} both claim the "
                                f"trigger {phrase!r} — the host has to guess")
            triggers[key] = skill
    return Result(name, not problems,
                  f"{len(skills)} skills, {len(triggers)} distinct triggers"
                  if not problems else f"{len(problems)} ambiguous", problems)


def check_skills_verify_before_returning(root: Path) -> Result:
    """A skill that hands over its first attempt leaves the last 30% to you.

    Every skill that produces something — a document, a change, a rendered
    artifact — has to say how it checks that thing against evidence outside the
    draft before returning it. Reading your own output and concluding it is
    fine is not verification, and a skill that stops at the first draft is one
    whose user becomes the quality gate.

    Read-only skills that answer a question are exempt: their verification is
    the citation, which `SKILLS.md` covers separately.
    """
    name = "skills check their work"
    directory = root / "plugin" / "skills"
    if not directory.is_dir():
        return Result(name, True, "no skills directory", skipped=True)

    #: These answer rather than produce. `ask` cites; `skills` lists what the
    #: catalogue holds; `doctor` reports what a probe said.
    ANSWERS_ONLY = {"ask", "skills", "doctor", "impact", "context"}
    wanted = ("acceptance criteria", "before returning", "verify")
    problems, checked = [], 0
    for path in sorted(directory.glob("*/SKILL.md")):
        skill = path.parent.name
        if skill in ANSWERS_ONLY:
            continue
        checked += 1
        body = path.read_text(encoding="utf-8").lower()
        if not any(phrase in body for phrase in wanted):
            problems.append(f"{skill} returns its first attempt — it must say "
                            f"what it checks, against what evidence, before "
                            f"handing anything back (see SKILLS.md rule 4)")
    return Result(name, not problems,
                  f"{checked} producing skills" if not problems
                  else f"{len(problems)} return unchecked work", problems)


def check_schemas(root: Path) -> Result:
    import json
    from . import schemas
    drifted = []
    for name, schema in schemas.SCHEMAS.items():
        path = root / "schemas" / f"{name}.schema.json"
        if not path.is_file():
            drifted.append(f"{name}.schema.json has not been published")
        elif json.loads(path.read_text()) != schemas.json_schema(schema):
            drifted.append(f"{name}.schema.json has drifted")
    return Result("published schemas match the code", not drifted,
                  f"{len(schemas.SCHEMAS)} schemas" if not drifted
                  else "run `python3 -m sky.schemas`", drifted)


def check_agent_references(root: Path) -> Result:
    """Every agent a skill names must exist.

    Splitting one agent into two broke three skills that still named the old
    one, and nothing warned: a skill naming an agent that does not exist
    selects nothing at all.
    """
    agents = {p.stem for p in (root / "plugin" / "agents").glob("*.md")}
    named = re.compile(r"`([a-z][a-z-]{3,})` agent")
    problems = []
    for path in _files(root / "plugin"):
        if path.suffix != ".md":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in named.finditer(line):
                if match.group(1) not in agents:
                    problems.append(f"{path.relative_to(root)}:{n}  names the "
                                    f"`{match.group(1)}` agent, which does not exist")
    return Result("every agent named by a skill exists", not problems,
                  f"{len(agents)} agents" if not problems
                  else f"{len(problems)} stale reference(s)", problems)


# ── is anything in plugin/ that must not leave this machine ──────────────
def check_no_credentials(root: Path) -> Result:
    """The same gate that guards a knowledge-base write, pointed at the plugin.

    One implementation, so a pattern added for one path protects the other.
    """
    problems = []
    for path in _published(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for finding in redaction.find(text):
            problems.append(f"{path.relative_to(root)}:{finding}")
    return Result("no credentials in the plugin", not problems,
                  "clean" if not problems else f"{len(problems)} finding(s)",
                  problems)


#: Identifiers from published standards. Deliberately a short, exact list of
#: prefixes rather than a pattern — "it looks like a spec URL" is how a real
#: endpoint gets waved through.
STANDARDS_URLS = ("https://json-schema.org",)


def check_no_local_strings(root: Path) -> Result:
    """A URL, a tenant, or somebody's home directory in shipped content."""
    problems = []
    for path in _published(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            where = f"{path.relative_to(root)}:{n}"
            for match in _URL.finditer(line):
                # `${SKY_KB_URL}` and `<your-host>` are how a URL is supposed
                # to be written, and must not be reported as one.
                if _PLACEHOLDER_URL.search(line):
                    continue
                # A standards identifier is not an endpoint: nothing connects
                # to `https://json-schema.org/draft/2020-12/schema`, it is the
                # name of a specification. Reporting it trains people to skim
                # this list, which is how the real one gets missed.
                if any(match.group(0).rstrip("/").startswith(s)
                       for s in STANDARDS_URLS):
                    continue
                problems.append(f"{where}  URL {match.group(0)}")
            for match in _HOME_PATH.finditer(line):
                problems.append(f"{where}  home directory {match.group(0)}")
            for match in _TENANT.finditer(line):
                problems.append(f"{where}  looks like a tenant code "
                                f"{match.group(0)}")
    return Result("no endpoints, tenants or home paths", not problems,
                  "clean" if not problems else f"{len(problems)} finding(s)",
                  problems)


def load_words(path: str | Path | None = None) -> list[str]:
    source = Path(path or os.environ.get("SKY_SELFTEST_WORDS") or
                  WORDS_FILE).expanduser()
    if not source.is_file():
        return []
    out = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def check_no_local_vocabulary(root: Path, words: list[str] | None = None) -> Result:
    """Words one organisation uses, which mean nothing to anyone else.

    The list is local and never committed — a list of one company's names
    shipping inside the tool that removes them would be self-defeating.

    **Matched on word boundaries.** A substring scan for a three-letter
    organisation name flags "usual" and "because"; four such lines exist in
    this repository right now. A check that cries wolf gets switched off.
    """
    words = load_words() if words is None else words
    if not words:
        return Result("no local vocabulary in the plugin", True,
                      f"SKIPPED — no word list at {WORDS_FILE}", skipped=True)
    patterns = [(w, re.compile(rf"\b{re.escape(w)}\b", re.I)) for w in words]
    problems = []
    for path in _authored(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            for word, pattern in patterns:
                if pattern.search(line):
                    problems.append(f"{path.relative_to(root)}:{n}  {word!r}")
    return Result("no local vocabulary in the plugin", not problems,
                  f"{len(words)} words checked" if not problems
                  else f"{len(problems)} finding(s)", problems)


def check_no_retired_names(root: Path) -> Result:
    """Shipped content must not name something that no longer exists.

    A rename is believed finished long before it is. `brain-map` survived two
    renames in a skill nobody re-read, and a skill telling a model to read a
    file that is no longer the source of truth sends it somewhere wrong rather
    than failing.
    """
    problems = []
    for path in _authored(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            for name, instead in RETIRED_NAMES.items():
                if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", line):
                    problems.append(f"{path.relative_to(root)}:{n}  {name!r} is "
                                    f"retired — use {instead}")
            for prefix, instead in RETIRED_PREFIXES.items():
                # No trailing boundary: a prefix is meant to be followed by
                # more. The leading one still stands, so `SKY_VAI_` or a word
                # ending in `vai-` is not reported.
                if re.search(rf"(?<![\w-]){re.escape(prefix)}", line):
                    problems.append(f"{path.relative_to(root)}:{n}  {prefix!r} "
                                    f"is retired — use {instead}")
            for pattern, instead in RETIRED_SOURCES:
                if pattern.search(line):
                    problems.append(f"{path.relative_to(root)}:{n}  reads a "
                                    f"retired source — {instead}")
    return Result("no retired names in the plugin", not problems,
                  f"{len(RETIRED_NAMES) + len(RETIRED_PREFIXES) + len(RETIRED_SOURCES)} "
                  f"rules checked" if not problems
                  else f"{len(problems)} finding(s)", problems)


CHECKS = (
    check_shape,
    check_the_wall,
    check_policy,
    check_agents,
    check_both_tool_spellings,
    check_skills_read_configuration,
    check_skills_can_be_found,
    check_skills_verify_before_returning,
    check_vendored_runtime,
    check_schemas,
    check_agent_references,
    check_no_credentials,
    check_no_local_strings,
    check_no_retired_names,
    check_no_local_vocabulary,
)


def run_all(root: Path) -> list[Result]:
    results = []
    for check in CHECKS:
        try:
            results.append(check(root))
        except Exception as exc:                             # pragma: no cover
            results.append(Result(check.__name__, False, f"the check itself "
                                  f"failed: {exc}"))
    return results
