"""The ten probes, built to the contracts agreed in gate G23a.

Every probe here makes a real call and looks at what came back. None of them
passes because a value was configured, and none passes on the absence of an
error. That is not fastidiousness: ingest reported `COMPLETED` with zero
entities for two days, and every configuration-level check called it healthy
the whole time.

Two probes are inverted, and deliberately so. For **safety** and **actions**,
the healthy answer is a *failure* — a guard that denies, a push that cannot
happen. A probe that reported those as errors would have the truth backwards.

Not all ten are implemented yet; the ones that are not report MISSING with the
reason, which is the honest state rather than a silent omission.

SH-053 Windows follow-up: decode subprocess output as UTF-8 with replacement.
The host may print characters absent from the Windows code page; a failed
reader thread can otherwise leave stdout as None and crash the probe.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .kbmap import KB, KBMapError
from .readiness import Brain, Part, State

TIMEOUT = 30


# ── talking to a knowledge base ──────────────────────────────────────────
#: The knowledge port's tool prefix (docs/knowledge-port.md). Tools are named
#: `<prefix>_<operation>`. This is the only place the runtime spells it.
KB_PREFIX = "kb"

#: Every port operation a probe calls. A test checks each one against the
#: policy, so a probe cannot drift onto a name no agent is allowed to call.
PROBE_OPERATIONS = ("similarity_search", "documents_ingest", "jobs_status",
                    "jobs_output", "ontologies_get")


def kb_tool(operation: str) -> str:
    """The tool name a knowledge base built to the port offers."""
    return f"{KB_PREFIX}_{operation}"


def _rpc(url: str, token: str, method: str, params: dict) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    # Streamable HTTP wants both; with only one the request hangs rather than
    # failing, which is a much worse way to find out.
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read().decode()
    for line in raw.splitlines():
        if line.startswith("data: "):
            raw = line[6:]
            break
    out = json.loads(raw)
    if "error" in out:
        raise RuntimeError(out["error"].get("message", out["error"]))
    return out.get("result", {})


def _call_tool(url: str, token: str, name: str, args: dict) -> str:
    result = _rpc(url, token, "tools/call", {"name": name, "arguments": args})
    parts = result.get("content", [])
    return parts[0].get("text", "") if parts else ""


# ── 5. Knowledge — the KB itself, and the code index beside it ───────────
def probe_knowledge(brain: Brain, kb: KB) -> None:
    try:
        token = kb.token()
    except KBMapError as exc:
        brain.add(Part.KNOWLEDGE, State.MISSING, str(exc))
        return
    try:
        started = time.monotonic()
        result = _rpc(kb.url, token, "tools/list", {})
        ms = int((time.monotonic() - started) * 1000)
        tools = result.get("tools", [])
        if not tools:
            brain.add(Part.KNOWLEDGE, State.DOWN,
                      "the endpoint answered but published no tools")
            return
        brain.add(Part.KNOWLEDGE, State.OK,
                  f"{len(tools)} tools, {ms} ms, tenant {kb.tenant}")
    except Exception as exc:
        brain.add(Part.KNOWLEDGE, State.DOWN, f"{type(exc).__name__}: {exc}")


def probe_code_index(kb: KB) -> str:
    """The code index, which is a separate endpoint. Returns a note, not a state.

    It deliberately does NOT write a state. An earlier version had it write
    Focus, which then caused `run_all` to skip the search entirely — so Focus
    could report `ok` without any retrieval ever being tried. A code index is
    not retrieval; it answers structural questions about code, and a KB without
    one is still a working KB.
    """
    if not kb.code_url:
        return "no code index configured"
    try:
        text = _call_tool(kb.code_url, kb.token(), "list_indexed_repos",
                          {"tenant_code": kb.tenant})
        if "failed" in text.lower():
            return "code index published but not answering"
        return "code index answered"
    except Exception as exc:
        return f"code index unreachable ({type(exc).__name__})"


# ── 2. Focus — retrieval actually returns something OF THIS TENANT'S ─────
def _hit_tenants(text: str) -> tuple[int, int, int] | None:
    """(own-tenant, other-tenant, untagged) hit counts, or None if unparseable.

    A hit carries `metadata.tenant_code`. Only the `project` layer is isolated
    per tenant; the other layers are shared across every tenant on the host, so
    a search against an EMPTY knowledge base still returns other tenants'
    shared documents — and a probe that counts hits reports that as healthy.
    Measured on 2026-09-17: a tenant with no searchable documents of its own
    got five hits, every one from somebody else's tenant.
    """
    try:
        body = json.loads(text)
    except ValueError:
        return None
    hits = body.get("hits") or body.get("results") or []
    if not isinstance(hits, list):
        return None
    own = other = untagged = 0
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        tenant = meta.get("tenant_code") or hit.get("tenant_code")
        if not tenant:
            untagged += 1
        elif tenant == _hit_tenants.wanted:
            own += 1
        else:
            other += 1
    return own, other, untagged


_hit_tenants.wanted = ""


def probe_focus(brain: Brain, kb: KB, code_note: str = "") -> None:
    """Retrieval must return something, and something that is actually ours."""
    suffix = f"; {code_note}" if code_note else ""
    if brain.state_of(Part.KNOWLEDGE) is not State.OK:
        brain.add(Part.FOCUS, State.MISSING,
                  f"not probed: the KB did not answer{suffix}")
        return
    try:
        started = time.monotonic()
        text = _call_tool(kb.url, kb.token(), kb_tool("similarity_search"),
                          {"tenant_code": kb.tenant, "query": "design", "k": 5})
        ms = int((time.monotonic() - started) * 1000)
        _hit_tenants.wanted = kb.tenant
        counted = _hit_tenants(text)
        if counted is None:
            # Not JSON we understand: fall back to counting ids, and say that
            # ownership was not checked rather than implying it was.
            hits = text.count('"doc_id"') or text.count("document_id")
            own, other, untagged = 0, 0, hits
        else:
            own, other, untagged = counted
        hits = own + other + untagged
        if hits == 0:
            # G23a: zero hits is DOWN. An empty KB and a broken index cannot be
            # told apart from here, and either way retrieval cannot answer a
            # question — which is what this part is for.
            brain.add(Part.FOCUS, State.DOWN,
                      f"search ran in {ms} ms and returned nothing — an empty KB "
                      f"and a broken index look the same from here{suffix}")
            return
        if own == 0 and other > 0:
            # Retrieval works — for everybody else's documents. This tenant has
            # nothing searchable of its own, or its index is broken; either
            # way a question about THIS project cannot be answered from here.
            # Degraded, not down: the shared layers still answer general
            # questions, and saying so is more useful than a red row.
            brain.add(Part.FOCUS, State.DEGRADED,
                      f"{hits} hits in {ms} ms, NONE from tenant {kb.tenant} — "
                      f"retrieval works, but this knowledge base has no "
                      f"searchable documents of its own (empty, or its index "
                      f"is broken); the hits are other tenants' shared layers"
                      f"{suffix}")
            return
        if own == 0:
            brain.add(Part.FOCUS, State.OK,
                      f"{hits} hits, {ms} ms — hits carry no tenant code, so "
                      f"ownership was not checked{suffix}")
            return
        brain.add(Part.FOCUS, State.OK,
                  f"{hits} hits ({own} from this tenant), {ms} ms{suffix}")
    except Exception as exc:
        brain.add(Part.FOCUS, State.DOWN, f"{type(exc).__name__}: {exc}{suffix}")


# ── 3 / 6. The hand: its version, and which model it is ──────────────────
def probe_hand(brain: Brain, command: str = "claude") -> None:
    binary = shutil.which(command)
    if not binary:
        brain.add(Part.SHORT_TERM, State.MISSING, f"{command} is not on PATH")
        brain.add(Part.THINKING, State.MISSING, f"{command} is not on PATH")
        return
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=20, stdin=subprocess.DEVNULL)
        version = (out.stdout or "").strip() or (out.stderr or "").strip()
        if out.returncode != 0 or not version:
            brain.add(Part.SHORT_TERM, State.DOWN,
                      f"{command} --version exited {out.returncode}")
            brain.add(Part.THINKING, State.DOWN, "the hand did not answer")
            return
        brain.add(Part.SHORT_TERM, State.OK, version.splitlines()[0][:60])
        _probe_model(brain, binary, command)
    except subprocess.TimeoutExpired:
        brain.add(Part.SHORT_TERM, State.DOWN, f"{command} --version timed out")
        brain.add(Part.THINKING, State.DOWN, "the hand did not answer")


def _probe_model(brain: Brain, binary: str, command: str) -> None:
    """G23a asks for the running model's identifier, not merely that a hand exists.

    A version string says the binary is installed. It says nothing about which
    model is behind it, and a hand pointed at a model the account cannot use
    installs perfectly well. Where the identifier cannot be obtained this
    degrades and says so, rather than claiming an answer it does not have.
    """
    try:
        out = subprocess.run([binary, "--help"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=20, stdin=subprocess.DEVNULL)
        blob = (out.stdout or "") + (out.stderr or "")
        if "--model" not in blob:
            brain.add(Part.THINKING, State.DEGRADED,
                      f"{command} does not report which model it runs — "
                      "installed, but the model behind it is unverified")
            return
        brain.add(Part.THINKING, State.DEGRADED,
                  f"{command} accepts --model, but the running model is only "
                  "confirmed once a hand is started — unverified until then")
    except (subprocess.TimeoutExpired, OSError):
        brain.add(Part.THINKING, State.DOWN, f"{command} did not answer --help")


# ── 10. Actions — the inverted one: a push that CANNOT happen ────────────
def probe_actions(brain: Brain) -> None:
    """Healthy is a push that fails.

    This only means something inside a launched environment. Run from an
    ordinary shell the push may well succeed, and that is not a fault — it is
    the developer's own shell, with the developer's own credentials.
    """
    import os
    if os.environ.get("SKY_LAUNCHED") != "1":
        brain.add(Part.ACTIONS, State.DEGRADED,
                  "not a launched session — the git block is not applied here, "
                  "so this cannot be checked")
        return
    try:
        out = subprocess.run(["git", "push", "--dry-run"], capture_output=True,
                             encoding="utf-8", errors="replace",
                             text=True, timeout=30, stdin=subprocess.DEVNULL)
        if out.returncode == 0:
            brain.add(Part.ACTIONS, State.DOWN,
                      "A DRY-RUN PUSH SUCCEEDED inside a launched session. The git "
                      "block is not working; do not build in this environment.")
            return
        brain.add(Part.ACTIONS, State.OK, "dry-run push refused, as it must be")
    except subprocess.TimeoutExpired:
        brain.add(Part.ACTIONS, State.DOWN, "the dry-run push hung — treat as unblocked")
    except FileNotFoundError:
        brain.add(Part.ACTIONS, State.MISSING, "git is not on PATH")


def probe_safety(brain: Brain, policy=None) -> None:
    """Safety has two halves, and only one of them is built.

    The **rules** are `policy.yaml`: loaded, holding together, and denying
    something it should deny. The **enforcement during a run** is the guard
    hook, built in H5.

    Both halves are observed by being used, never by being found. The policy is
    asked to deny a push and must; the guard is then **run**, with a denied
    command on its standard input, and must answer `deny`. A hooks file that
    exists proves nothing — an unreadable script, a runtime not on PATH and a
    guard that stands aside all leave that file looking perfect.

    Rules without a working guard is still worth more than nothing: the
    launcher applies the allowlist from this same file before the model exists,
    which is tier A. But it is not the whole of Safety, so that case is
    DEGRADED — calling it OK would let a build start believing an outward write
    would be stopped mid-run when it would not.
    """
    if policy is None:
        brain.add(Part.SAFETY, State.MISSING,
                  "no policy.yaml — nothing says what this agent must not do")
        return
    try:
        denied = policy.denied_command("git push origin main")
        merge = policy.decide("developer", "pr.merge")
    except Exception as exc:                                # pragma: no cover
        brain.add(Part.SAFETY, State.DOWN, f"the policy could not be asked: {exc}")
        return
    if denied is None or merge.allowed:
        # A policy that permits what it exists to forbid is worse than none,
        # because something is relying on it.
        brain.add(Part.SAFETY, State.DOWN,
                  "the policy loaded but does not deny a push or a merge — "
                  "check policy.yaml")
        return
    rules = (f"{len(policy.actions)} actions, {len(policy.roles)} roles")
    answered = _guard_answers(getattr(policy, "path", None))
    if answered is True:
        brain.add(Part.SAFETY, State.OK,
                  f"rules loaded and denying ({rules}); the guard ran and "
                  f"refused a push")
    elif answered is False:
        brain.add(Part.SAFETY, State.DOWN,
                  f"rules loaded and denying ({rules}), but the guard ALLOWED a "
                  f"push when asked — the hook is present and not enforcing")
    else:
        brain.add(Part.SAFETY, State.DEGRADED,
                  f"rules loaded and denying ({rules}); the guard could not be "
                  f"run here, so nothing enforces them during a session")


#: What `sky build` gives a run and the guard reads to decide it is in one.
#: Without it the guard stands aside — correct in a person's own session, and
#: exactly why asking it from the caller's environment always read "allowed".
RUN_MARKER = "SKY_LAUNCHED"

#: Variables that would make the probe's question land in a real run's ledger.
RUN_RECORD_VARS = ("SKY_RUN_DIR", "SKY_RUN_ID", "SKY_AGENT_ID")


def _guard_command() -> list[str]:
    """This runtime's own guard — not whichever `sky` is first on PATH.

    A checkout probed by an older installed copy reported on the installed
    copy's guard. Running the package this file belongs to, with the same
    interpreter, asks the code that is actually running.
    """
    return [sys.executable, "-m", "sky", "guard"]


def _guard_env(policy_path=None) -> dict:
    """The environment a managed run would hand the guard.

    The run marker is set, so the guard decides instead of standing aside.
    The run-record variables are removed, so this question is not written into
    a run's ledger. The policy is the one the probe just loaded, so the guard
    is asked about the same rules.
    """
    env = {k: v for k, v in os.environ.items() if k not in RUN_RECORD_VARS}
    env[RUN_MARKER] = "1"
    package_root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (package_root, env.get("PYTHONPATH", "")) if p)
    if policy_path:
        env["SKY_POLICY"] = str(policy_path)
    return env


def _guard_answers(policy_path=None) -> bool | None:
    """Run the guard on a command the policy denies. True/False/None-if-absent.

    None is a real third answer and must not collapse into False: "the guard
    could not be run here" and "the guard ran and let a push through" are
    different emergencies.
    """
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "git push origin main"}})
    try:
        out = subprocess.run(_guard_command(), input=payload, text=True,
                             encoding="utf-8", errors="replace",
                             capture_output=True, timeout=20,
                             env=_guard_env(policy_path))
        body = json.loads(out.stdout or "{}")
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    decision = (body.get("hookSpecificOutput") or {}).get("permissionDecision")
    if decision is None:
        return None
    return decision == "deny"


def probe_quality(brain: Brain, cwd=None) -> None:
    """Can this repository's own tests be run at all?

    The G23a mechanism: run the repository's test command with a selector that
    matches nothing. Healthy is the runner starting and reporting zero tests —
    a positive observation that costs nothing, because the suite never runs.

    Whether the tests *pass* is not this probe's business. A repository whose
    tests are currently red still has working Quality control; a repository
    whose runner is not installed does not.
    """
    from pathlib import Path as _Path
    from . import quality
    result = quality.check(_Path(cwd) if cwd else _Path.cwd())
    brain.add(Part.QUALITY, State(result.state), result.detail)


#: Fallbacks only. The real numbers are counted from the installed plugin — a
#: constant here was still 10 skills when the plugin shipped 20, so a
#: half-installed v1 reported itself healthy, which is precisely the failure
#: this probe exists to catch.
EXPECTED_SKILLS, EXPECTED_AGENTS = 20, 6


def _shipped_counts() -> tuple[int, int]:
    """What the plugin on this machine actually contains."""
    import os
    roots = []
    if os.environ.get("SKY_PLUGIN_ROOT"):
        roots.append(Path(os.environ["SKY_PLUGIN_ROOT"]))
    # `cache/sky/sky/*` and not `cache/*/*/*`: the glob matched ANY installed
    # plugin, so this counted a different product's ten skills and three agents
    # and reported a complete SKY install as incomplete.
    roots += sorted(Path("~/.claude/plugins/cache/sky/sky").expanduser().glob("*"))
    roots.append(Path(__file__).resolve().parents[2] / "plugin")
    for root in roots:
        skills, agents = root / "skills", root / "agents"
        if skills.is_dir() and agents.is_dir():
            return (len(list(skills.glob("*/SKILL.md"))),
                    len(list(agents.glob("*.md"))))
    return EXPECTED_SKILLS, EXPECTED_AGENTS


def probe_habits(brain: Brain, hand: str = "claude") -> None:
    """Can the hand actually see the skills and role agents?

    G23a row 8, and its stated failure: *zero — the plugin did not load, which
    no config check reveals.* So this does not read a settings file. It asks
    **the host** what it has installed and enabled, and then counts what the
    host resolved.

    That is one step short of the ideal — the ideal is a running session
    listing what it loaded — and one step past a configuration check, because
    the answer comes from the product rather than from a file we wrote.
    """
    if hand != "claude":
        brain.add(Part.HABITS, State.NA,
                  f"{hand} has no host package yet, so it loads no skills — H6")
        return
    if shutil.which("claude") is None:
        brain.add(Part.HABITS, State.MISSING, "claude is not on PATH")
        return
    try:
        out = subprocess.run(["claude", "plugin", "list"], capture_output=True,
                             encoding="utf-8", errors="replace",
                             text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        brain.add(Part.HABITS, State.DOWN, "the host did not answer `plugin list`")
        return
    except OSError as exc:
        brain.add(Part.HABITS, State.DOWN, f"could not ask the host: {exc}")
        return

    text = (out.stdout or "") + (out.stderr or "")
    entry = re.search(r"^\s*[^\s]*\s*(sky@\S+)\s*$(.*?)(?=^\s*[^\s]*\s*\S+@|\Z)",
                      text, re.M | re.S)
    if entry is None:
        brain.add(Part.HABITS, State.MISSING,
                  "the host lists no `sky` plugin — install it from the marketplace")
        return
    if "enabled" not in entry.group(2):
        brain.add(Part.HABITS, State.DOWN,
                  f"{entry.group(1)} is installed but not enabled, so none of its "
                  f"skills or agents load")
        return

    version = re.search(r"Version:\s*(\S+)", entry.group(2))
    installed = _plugin_cache(version.group(1) if version else None)
    if installed is None:
        brain.add(Part.HABITS, State.DEGRADED,
                  f"{entry.group(1)} is enabled, but its files were not found on "
                  f"disk — the host may not have finished installing it")
        return
    skills = len(list((installed / "skills").glob("*/SKILL.md")))
    agents = len(list((installed / "agents").glob("*.md")))
    if not skills or not agents:
        brain.add(Part.HABITS, State.DOWN,
                  f"{entry.group(1)} is enabled but resolved to {skills} skills and "
                  f"{agents} agents — the install is incomplete")
        return
    want_skills, want_agents = _shipped_counts()
    state = State.OK if (skills >= want_skills and agents >= want_agents) \
        else State.DEGRADED
    short = "" if state is State.OK else \
        f" — fewer than the {want_skills} skills and {want_agents} agents this " \
        f"version ships"
    brain.add(Part.HABITS, state,
              f"{entry.group(1)} enabled: {skills} skills, {agents} agents{short}")


def _plugin_cache(version=None):
    """Where the host put the plugin it resolved. Newest version if unstated."""
    root = Path("~/.claude/plugins/cache").expanduser()
    if not root.is_dir():
        return None
    found = []
    for marketplace in root.iterdir():
        for plugin in (marketplace.iterdir() if marketplace.is_dir() else ()):
            if plugin.name != "sky":
                continue
            for got in (plugin.iterdir() if plugin.is_dir() else ()):
                if (got / "skills").is_dir():
                    found.append(got)
    if version:
        exact = [f for f in found if f.name == version]
        if exact:
            return exact[0]
    return max(found, key=lambda f: f.name) if found else None


def probe_remembering(brain: Brain, kb: KB, deep: bool = False) -> None:
    """Does an ingest actually extract anything?

    G23a row 4, and it names the failure precisely: *job status `COMPLETED`
    with `entities == 0` — the failure that hid for two days.* Nothing short of
    reading the entity count catches that; the job says COMPLETED either way.

    **This one writes**, which makes it different from every other probe. A
    knowledge base is shared and long-lived, so a probe document ingested on
    every `doctor` would be pollution that outlives the question it answered.
    So it is **opt-in**: `--deep` runs it, and the default says plainly that it
    did not run rather than reporting a state it did not observe.
    """
    if not deep:
        brain.add(Part.REMEMBERING, State.DEGRADED,
                  "not probed — this is the one probe that writes to the KB, so "
                  "it runs only with `sky doctor --deep`")
        return
    if not kb.write:
        brain.add(Part.REMEMBERING, State.NA,
                  f"KB '{kb.name}' is read-only in the map, so nothing may be "
                  f"ingested into it")
        return
    try:
        token = kb.token()
    except KBMapError as exc:
        brain.add(Part.REMEMBERING, State.MISSING, str(exc))
        return

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    # The probe document must be written FOR the ontology it is ingested
    # under. A fixed one cannot be: the first version said "the ProbeModule
    # component depends on the ProbeStore datastore", which is SDLC
    # vocabulary — ingested under `sky_skill`, whose types are Skill, Step and
    # Tool, it correctly extracted nothing, and the probe reported the very
    # failure it exists to detect. A false DOWN on a healthy KB is worse than
    # no probe, because it refuses builds.
    #
    # So the ontology is asked what it extracts, and the document is written to
    # contain those things. Both ends of a relation go in ONE sentence: the
    # extractor sees a single chunk at a time and cannot link across chunks.
    try:
        types = _entity_types(kb, token)
    except Exception as exc:
        brain.add(Part.REMEMBERING, State.DOWN,
                  f"could not read ontology '{kb.ontology}': {exc}")
        return
    if not types:
        brain.add(Part.REMEMBERING, State.DOWN,
                  f"ontology '{kb.ontology}' declares no entity types, so nothing "
                  f"could be extracted from any document")
        return
    named = [f"Probe{t}{stamp[-4:]}" for t in types[:3]]
    sentence = " ".join(
        f"{name} is a {kind.lower()}." for name, kind in zip(named, types[:3]))
    if len(named) > 1:
        sentence += f" {named[0]} is related to {named[1]}."
    body = (f"SKY readiness probe {stamp}.\n\n{sentence}\n\n"
            f"This document exists only to confirm that ingestion extracts "
            f"entities under the {kb.ontology} ontology. It carries no decision "
            f"and may be deleted.\n")
    try:
        started = _rpc(kb.url, token, "tools/call", {
            "name": kb_tool("documents_ingest"),
            "arguments": {"tenant_code": kb.tenant, "text": body,
                          "filename": f"sky-probe-{stamp}.md",
                          "ontology": kb.ontology, "layer": "project"}})
        # A tool that fails answers 200 with `isError` set and the reason in
        # its text. Reporting "no job id" instead of that reason turns an
        # actionable message — "Ontology 'sky_sdlc' not found" — into a
        # mystery, which is how an hour gets lost.
        refusal = _tool_error(started)
        if refusal:
            brain.add(Part.REMEMBERING, State.DOWN, refusal)
            return
        job = _job_id(started)
        if not job:
            brain.add(Part.REMEMBERING, State.DOWN,
                      "the ingest call returned neither a job id nor an error — "
                      f"it answered: {' '.join(_texts(started))[:200] or '(nothing)'}")
            return
        entities, status = _await_job(kb, token, job)
    except Exception as exc:
        brain.add(Part.REMEMBERING, State.DOWN, f"{type(exc).__name__}: {exc}")
        return

    if entities is None:
        brain.add(Part.REMEMBERING, State.DOWN,
                  f"job {job} ended {status} without reporting an entity count")
        return
    if entities == 0:
        brain.add(Part.REMEMBERING, State.DOWN,
                  f"job {job} reported {status} and extracted ZERO entities — "
                  f"ingestion is silently broken; documents are being stored and "
                  f"nothing is being learned from them")
        return
    brain.add(Part.REMEMBERING, State.OK,
              f"a probe document extracted {entities} entities (job {job}) — "
              f"ingestion is learning, not just storing")


def _job_id(result) -> str:
    """The job id, wherever this platform version put it."""
    for text in _texts(result):
        try:
            body = json.loads(text)
        except ValueError:
            continue
        for key in ("job_id", "id", "jobId"):
            if isinstance(body, dict) and body.get(key):
                return str(body[key])
    return ""


def _tool_error(result) -> str:
    """The server's own words when a tool call fails, or empty."""
    if not isinstance(result, dict) or not result.get("isError"):
        return ""
    said = " ".join(_texts(result)).strip()
    return said or "the tool reported an error with no message"


def _texts(result):
    content = result.get("content") if isinstance(result, dict) else None
    for item in content or ():
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            yield item["text"]


def _await_job(kb: KB, token: str, job: str, limit: int = 180):
    """Poll until the job finishes, then read what it produced.

    **Two calls, not one.** `jobs.status` reports progress and stages and does
    *not* carry the entity count; the count is in `jobs.output`. A probe that
    polls only the status sees `COMPLETED` and can say nothing about whether
    anything was learned — which is precisely the failure this probe exists to
    catch, so it would have been blind to it. Measured on a live run.
    """
    deadline = time.monotonic() + limit
    status = "unknown"
    while time.monotonic() < deadline:
        result = _rpc(kb.url, token, "tools/call", {
            "name": kb_tool("jobs_status"),
            "arguments": {"tenant_code": kb.tenant, "job_id": job}})
        for text in _texts(result):
            try:
                body = json.loads(text)
            except ValueError:
                continue
            if not isinstance(body, dict):
                continue
            status = str(body.get("status") or status).upper()
            if status in ("COMPLETED", "FAILED", "ERROR"):
                return _job_entities(kb, token, job), status
        time.sleep(3)
    return None, f"still {status} after {limit}s"


def _entity_types(kb: KB, token: str) -> list:
    """What this ontology actually extracts, asked rather than assumed."""
    result = _rpc(kb.url, token, "tools/call", {
        "name": kb_tool("ontologies_get"),
        "arguments": {"tenant_code": kb.tenant, "name": kb.ontology}})
    refusal = _tool_error(result)
    if refusal:
        raise RuntimeError(refusal)
    for text in _texts(result):
        try:
            body = json.loads(text)
        except ValueError:
            continue
        if not isinstance(body, dict):
            continue
        # The body may be structured, or a YAML string. Read names either way
        # without taking a YAML dependency: core has none.
        raw = body.get("entity_types")
        if isinstance(raw, list):
            names = [e.get("name") if isinstance(e, dict) else e for e in raw]
            return [n for n in names if isinstance(n, str)]
        yaml_body = body.get("body_yaml") or body.get("body") or ""
        if isinstance(yaml_body, str) and "entity_types" in yaml_body:
            return _names_under(yaml_body, "entity_types")
    return []


def _names_under(text: str, section: str) -> list:
    """`- name: X` lines under one top-level key. Enough for this, no more."""
    names, inside = [], False
    for line in text.splitlines():
        if line.startswith(section + ":"):
            inside = True
            continue
        if inside and line and not line[0].isspace():
            break
        if inside:
            stripped = line.strip()
            if stripped.startswith("- name:"):
                names.append(stripped.split(":", 1)[1].strip().strip("'\""))
    return names


def _job_entities(kb: KB, token: str, job: str):
    """The entity count, from the job's output."""
    try:
        result = _rpc(kb.url, token, "tools/call", {
            "name": kb_tool("jobs_output"),
            "arguments": {"tenant_code": kb.tenant, "job_id": job}})
    except Exception:
        return None
    for text in _texts(result):
        try:
            body = json.loads(text)
        except ValueError:
            continue
        if isinstance(body, dict):
            found = _entity_count(body)
            if found is not None:
                return found
    return None


def _entity_count(body):
    """The number that matters, wherever it is reported."""
    for key in ("entities", "entity_count", "entities_extracted"):
        value = body.get(key)
        if isinstance(value, int):
            return value
    stats = body.get("stats") or body.get("result") or body.get("output")
    if isinstance(stats, dict):
        return _entity_count(stats)
    return None


# ── Not yet built. Named, with the reason. ───────────────────────────────
_PENDING = {
    Part.INPUTS: "adapters are harness step H6",
}


def probe_agent_definitions(brain: Brain, policy=None, hand: str = "claude") -> None:
    """Compare every offered Claude role to its expanded policy tool set.

    A bad definition is MISSING authority, including drift: a file's presence
    is not proof that the host will hold the intended boundary.
    """
    from .agent_definitions import DefinitionError, check_definition
    from .launcher import HAND_ROLES
    # Definitions are policy-derived Safety diagnostics, not an independent
    # readiness part. Removing policy changes Safety alone. The launcher still
    # refuses a bad requested definition directly, including for review roles.
    def report(state, detail):
        brain.add(Part.SAFETY, state, detail, name="agent definitions")
    if hand != "claude":
        report(State.NA, "this hand does not use Claude agent definitions")
        return
    if policy is None:
        report(State.MISSING, "no policy to compare")
        return
    try:
        roles = policy.roles_named() if hasattr(policy, "definition_for") else sorted(HAND_ROLES["claude"])
        for role in roles:
            check_definition(policy, role)
    except DefinitionError as exc:
        report(State.MISSING, str(exc))
        return
    detail = f"all {len(roles)} effective role definitions match" if hasattr(policy, "definition_for") else \
        "all four role definitions match the expanded policy tools"
    report(State.OK, detail)


def run_all(kb: KB | None, hand: str = "claude", policy=None, cwd=None,
            deep: bool = False, no_kb: str = "") -> Brain:
    """Probe every part. With no knowledge base, still probe the rest.

    A fresh clone has no KB map. Stopping at that one line hid the hand,
    policy, guard and test-runner rows — the parts that do work without an
    account — so the first thing a newcomer saw was a dead end.
    """
    brain = Brain()
    if kb is None:
        why = no_kb or "no knowledge base is configured"
        brain.add(Part.KNOWLEDGE, State.MISSING, why)
        brain.add(Part.FOCUS, State.MISSING, "not probed: no knowledge base")
    else:
        probe_knowledge(brain, kb)
        # The search always runs. It is the thing Focus means.
        probe_focus(brain, kb, code_note=probe_code_index(kb))
    probe_hand(brain, hand)
    probe_actions(brain)
    probe_safety(brain, policy)
    probe_agent_definitions(brain, policy, hand)
    probe_quality(brain, cwd)
    probe_habits(brain, hand)
    if kb is None:
        brain.add(Part.REMEMBERING, State.MISSING, "not probed: no knowledge base")
    else:
        probe_remembering(brain, kb, deep=deep)
    for part, reason in _PENDING.items():
        if brain.state_of(part) is State.MISSING:
            brain.add(part, State.MISSING, f"not built yet — {reason}")
    return brain
