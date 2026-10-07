"""The seven contracts.

`agent-card` · `task` · `run-event` · `agent-result` · `context-manifest` ·
`session-summary` · `memory-candidate`

These are what make a second coding agent a packaging exercise rather than a
second implementation. A host package is "supported" exactly when it can
produce and consume all seven; nothing else about it has to match.

**What validation here is worth, stated plainly.** It checks *shape* — a field
is present, is the right type, holds one of the allowed values. It cannot tell
a true summary from an invented one, and it never tries. One thing it does do
is stronger than shape, and it is the reason this module exists rather than a
pile of dictionaries:

    A field owned by the runtime is refused when it arrives from a model.

The design says the harness fills the trusted fields itself — the commit SHA,
the pull-request URL, the CI result, the authenticated identity — *so the model
cannot invent a successful outcome*. That sentence is only true if something
enforces it. `validate(..., source=MODEL)` is that something, and `seal()` is
the one door those fields come through.

Two smaller rules carry the same weight:

*Trust is not a default.* A context item with no `trust` field is untrusted,
never governed. Only a governed item may be treated as instructions, so the
absent case has to fall the safe way.

*Anything bound for the knowledge base passes the redaction gate.* Session
summaries and memory candidates are the two things written there, so both check
themselves — see `check_for_kb`.

No third-party dependency: core stays installable with a Python and nothing
else, and JSON Schema is *emitted* from these declarations (`json_schema`) so
the published files in `schemas/` cannot drift away from what core enforces.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# ── who may write a field ────────────────────────────────────────────────
MODEL = "model"        # a hand may write it; it is that hand's assertion
RUNTIME = "runtime"    # only core writes it, and a model-supplied value is refused

#: Timestamps are compared and sorted long after the run. Accepts a trailing Z
#: or a numeric offset; seconds optional.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?"
                        r"(Z|[+-]\d{2}:\d{2})$")


class Invalid(Exception):
    """Carries every problem, not just the first.

    A caller fixing one field at a time through a dozen round trips is how a
    contract gets abandoned for a free-form dictionary.
    """

    def __init__(self, schema_name: str, problems: list[str]):
        self.schema_name = schema_name
        self.problems = problems
        listed = "\n".join(f"    {p}" for p in problems)
        super().__init__(f"{schema_name}: {len(problems)} problem(s)\n{listed}")


@dataclass(frozen=True)
class Field:
    name: str
    kind: str                      # text int number bool texts map objects timestamp
    note: str
    required: bool = False
    owner: str = MODEL
    choices: tuple[str, ...] = ()
    of: "Schema | None" = None     # for kind="objects"


@dataclass(frozen=True)
class Schema:
    name: str
    purpose: str
    fields: tuple[Field, ...]
    #: An open schema keeps unknown fields. Only `run-event` is open: the
    #: recorder must be able to append a new kind of fact without a reader
    #: rejecting the whole file, and it deliberately never raises.
    open: bool = False

    @property
    def by_name(self) -> dict[str, Field]:
        return {f.name: f for f in self.fields}

    def runtime_fields(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.owner == RUNTIME)


# ── type checking ────────────────────────────────────────────────────────
def _type_problem(f: Field, value: Any) -> str | None:
    """One field, one answer. Returns None when the value is acceptable."""
    if f.kind == "text":
        if not isinstance(value, str) or not value.strip():
            return f"{f.name}: expected non-empty text, got {value!r}"
        if f.choices and value not in f.choices:
            return f"{f.name}: {value!r} is not one of {', '.join(f.choices)}"
    elif f.kind == "timestamp":
        if not isinstance(value, str) or not _TIMESTAMP.match(value):
            return (f"{f.name}: expected a timestamp like 2026-09-15T10:03:00Z, "
                    f"got {value!r}")
    elif f.kind == "int":
        # bool is a subclass of int in Python, so `isinstance(True, int)` is
        # True and an unguarded check accepts True as a count.
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{f.name}: expected a whole number, got {value!r}"
    elif f.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{f.name}: expected a number, got {value!r}"
    elif f.kind == "bool":
        if not isinstance(value, bool):
            return f"{f.name}: expected true or false, got {value!r}"
    elif f.kind == "texts":
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            return f"{f.name}: expected a list of text, got {value!r}"
        if f.choices:
            unknown = [v for v in value if v not in f.choices]
            if unknown:
                return (f"{f.name}: {', '.join(map(repr, unknown))} not in "
                        f"{', '.join(f.choices)}")
    elif f.kind == "map":
        if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
            return f"{f.name}: expected an object with text keys, got {value!r}"
    elif f.kind == "objects":
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            return f"{f.name}: expected a list of objects, got {value!r}"
    else:                                             # pragma: no cover
        return f"{f.name}: unknown field kind {f.kind!r} in the schema itself"
    return None


def validate(schema: Schema, document: Any, *, source: str = RUNTIME,
             _where: str = "") -> list[str]:
    """Every problem with this document. An empty list means it conforms.

    `source=MODEL` additionally refuses any field only the runtime may assert.
    That is the whole defence behind "the model cannot invent a successful
    outcome", so it is checked before anything else about those fields.
    """
    if not isinstance(document, dict):
        return [f"{_where or schema.name}: expected an object, got {type(document).__name__}"]

    problems: list[str] = []
    known = schema.by_name
    prefix = f"{_where}." if _where else ""

    if source == MODEL:
        # `null` is absent, the same as it is for every other field below. A
        # model emitting "head_commit": null is not claiming a commit.
        claimed = [n for n in schema.runtime_fields()
                   if document.get(n) is not None]
        for name in claimed:
            problems.append(
                f"{prefix}{name}: only the runtime may assert this — a value "
                f"from a model is refused")

    for f in schema.fields:
        if f.name not in document or document[f.name] is None:
            if f.required and not (source == MODEL and f.owner == RUNTIME):
                problems.append(f"{prefix}{f.name} is required ({f.note})")
            continue
        value = document[f.name]
        problem = _type_problem(f, value)
        if problem:
            problems.append(prefix + problem)
            continue
        if f.kind == "objects" and f.of is not None:
            for i, item in enumerate(value):
                problems += validate(f.of, item, source=source,
                                     _where=f"{prefix}{f.name}[{i}]")

    if not schema.open:
        for name in document:
            if name not in known:
                problems.append(f"{prefix}{name} is not part of {schema.name}")
    return problems


def check(schema: Schema, document: Any, *, source: str = RUNTIME) -> dict:
    """Validate or raise. Returns the document so it can be used inline."""
    problems = validate(schema, document, source=source)
    if problems:
        raise Invalid(schema.name, problems)
    return document


def seal(schema: Schema, document: dict, **trusted: Any) -> dict:
    """The one door the runtime-owned fields come through.

    The model's half is validated as a model document — which refuses any
    trusted field it tried to fill — and only then are the runtime's own
    values added. Passing a field the runtime does not own is a programming
    mistake and says so rather than quietly widening what a model can set.
    """
    known = schema.by_name
    misplaced = [k for k in trusted if k not in known]
    if misplaced:
        raise Invalid(schema.name, [f"{k} is not part of {schema.name}" for k in misplaced])
    not_ours = [k for k in trusted if known[k].owner != RUNTIME]
    if not_ours:
        raise Invalid(schema.name, [
            f"{k} is written by the model, not the runtime — sealing it here "
            f"would hide whose assertion it is" for k in not_ours])

    check(schema, document, source=MODEL)
    sealed = dict(document)
    sealed.update(trusted)
    return check(schema, sealed, source=RUNTIME)


# ── the trust rule ───────────────────────────────────────────────────────
GOVERNED = "governed"
UNTRUSTED = "untrusted"


def may_instruct(item: dict) -> bool:
    """Whether a context item may be treated as instructions rather than data.

    Absent means untrusted. A ticket description, a pull-request comment, a
    source file and an ordinary memory are all data no matter what they say
    about themselves — the whole prompt-injection boundary is this one
    default falling the safe way.
    """
    return item.get("trust") == GOVERNED


# ── the KB gate ──────────────────────────────────────────────────────────
def check_for_kb(schema: Schema, document: dict) -> dict:
    """Validate, then refuse to hand a secret to something long-lived.

    The two things written to a knowledge base are a session summary and a
    memory candidate, and both arrive here. Import is local so the contracts
    stay readable without the gate, and so a caller cannot end up with half of
    this rule.
    """
    from . import redaction

    check(schema, document)
    redaction.gate(json.dumps(document, default=str, ensure_ascii=False))
    return document


# ═════════════════════════════════════════════════════════════════════════
# The seven
# ═════════════════════════════════════════════════════════════════════════

ROLES = ("developer", "reviewer", "architect", "security")
HANDS = ("claude", "codex", "kimi")
TASK_KINDS = ("question", "review", "build", "learn")

# ── 1. agent-card ────────────────────────────────────────────────────────
# Identity and permission are both here and they are *different things*.
# The identity fields say which process, which log, which owner — they are what
# an audit reads. The action lists say what that agent may do. Conflating them
# is how "we can identify him" turns into "so he may not be trusted with much".
AGENT_CARD = Schema(
    name="agent-card",
    purpose="who an agent is, who owns it, and what it may do",
    fields=(
        Field("agent_id", "text", "stable internal id, never renamed",
              required=True, owner=RUNTIME),
        Field("display_name", "text", "renameable; history keeps the old names",
              required=True),
        Field("owner_jira_user_id", "text",
              "the human answerable for this agent's work",
              required=True, owner=RUNTIME),
        Field("role", "text", "one of the four roles", required=True,
              choices=ROLES),
        Field("hand", "text", "the coding agent that runs it", required=True,
              choices=HANDS),
        Field("kb", "text", "the knowledge base this agent resolves to",
              owner=RUNTIME),
        Field("repos", "texts", "repository paths in scope"),
        Field("projects", "texts", "project keys in scope"),
        Field("skills", "map", "skill name to grant state"),
        Field("allowed_actions", "texts", "what this agent may do",
              required=True, owner=RUNTIME),
        Field("denied_actions", "texts", "what it may never do, whatever else says",
              owner=RUNTIME),
        Field("created_at", "timestamp", "when the card was issued", owner=RUNTIME),
    ),
)

# ── 2. task ──────────────────────────────────────────────────────────────
TASK = Schema(
    name="task",
    purpose="one piece of work, and how far it may go without a human",
    fields=(
        Field("task_id", "text", "assigned before work starts", required=True,
              owner=RUNTIME),
        Field("kind", "text", "what sort of work — readiness is per kind",
              required=True, choices=TASK_KINDS),
        Field("title", "text", "what is being asked", required=True),
        Field("detail", "text", "the full request, as given"),
        Field("issue_key", "text", "the ticket, when there is one"),
        Field("repo", "text", "where the work happens"),
        Field("kb", "text", "resolved by core from the path — never chosen by a model",
              required=True, owner=RUNTIME),
        Field("requested_by", "text", "the human who asked", required=True,
              owner=RUNTIME),
        # The default is wait. An agent that finishes and stops is a colleague;
        # one that pushes because nobody said not to is a liability.
        Field("permission", "text",
              "wait for the owner, or proceed — absent means wait",
              choices=("wait", "proceed"), owner=RUNTIME),
        Field("acceptance", "texts", "what finished looks like"),
        Field("created_at", "timestamp", "when the task was raised", owner=RUNTIME),
    ),
)


def waits_for_owner(task: dict) -> bool:
    """Absent means wait — the same shape of default as `may_instruct`."""
    return task.get("permission") != "proceed"


# ── 3. run-event ─────────────────────────────────────────────────────────
#: Known kinds, for readers. Not a closed set: the recorder must be able to
#: append a new fact without a reader rejecting the file it appears in.
EVENT_KINDS = (
    "run.start", "run.refused", "run.finish", "run.usage",
    "git.block.checked", "hand.command", "hand.start", "hand.end",
    "intent.filed", "intent.refused",
    "agent.definition.checked", "launch_refused",
    "kb.put",
)

RUN_EVENT = Schema(
    name="run-event",
    purpose="one fact appended by the runtime while a run happens",
    open=True,
    fields=(
        Field("t", "int", "unix seconds; the recorder writes a float too",
              owner=RUNTIME),
        Field("kind", "text", "what happened", required=True, owner=RUNTIME),
    ),
)


def validate_event(event: Any) -> list[str]:
    """Events are read far more often than they are written.

    `t` is a float on the wire and an int here, so this checks the one thing
    the schema's integer rule would get wrong rather than loosening the rule
    for every other contract.
    """
    problems = validate(RUN_EVENT, event, source=RUNTIME)
    problems = [p for p in problems if not p.startswith("t: ")]
    if isinstance(event, dict):
        if not isinstance(event.get("t"), (int, float)) or isinstance(event.get("t"), bool):
            problems.append("t: expected a unix time, got "
                            f"{event.get('t')!r}")
    return problems


# ── 4. agent-result ──────────────────────────────────────────────────────
OUTCOMES = ("ready_for_review", "completed", "blocked", "failed", "cancelled")

# Declared before AGENT_RESULT, which nests it.
MEMORY_CANDIDATE = Schema(
    name="memory-candidate",
    purpose="one durable thing worth keeping, proposed by a hand and verified by core",
    fields=(
        Field("memory_type", "text", "what sort of thing this is", required=True,
              choices=("implementation_outcome", "decision", "lesson",
                       "risk", "review_outcome")),
        Field("summary", "text", "the thing itself, in one or two sentences",
              required=True),
        Field("decisions", "texts", "what was decided and why"),
        Field("risks", "texts", "what might bite later"),
        Field("project", "text", "project key"),
        Field("issue_key", "text", "the ticket, when there is one"),
        Field("agent_id", "text", "which agent", required=True, owner=RUNTIME),
        Field("agent_name_at_execution", "text", "its display name at the time",
              owner=RUNTIME),
        Field("owner_jira_user_id", "text", "the answerable human", owner=RUNTIME),
        Field("run_id", "text", "the run it came from", required=True, owner=RUNTIME),
        # Evidence is checked against the systems that hold it before anything
        # is written. A model proposing its own evidence is a model marking its
        # own work.
        Field("evidence", "map", "verified references — ticket, PR, commits, pipeline",
              owner=RUNTIME),
        Field("verification", "map", "what was actually run and what it said",
              owner=RUNTIME),
        Field("created_at", "timestamp", "when it was written", required=True,
              owner=RUNTIME),
    ),
)

AGENT_RESULT = Schema(
    name="agent-result",
    purpose="what a hand reports, separated from what the runtime knows",
    fields=(
        Field("run_id", "text", "the run", required=True, owner=RUNTIME),
        Field("agent_id", "text", "the agent", required=True, owner=RUNTIME),
        Field("agent_name_at_execution", "text", "its display name at the time",
              owner=RUNTIME),
        Field("owner_jira_user_id", "text", "the answerable human", owner=RUNTIME),
        Field("issue_key", "text", "the ticket, when there is one"),
        Field("outcome", "text", "how it ended", required=True, choices=OUTCOMES),
        Field("summary", "text", "what was done, in the hand's own words",
              required=True),
        Field("changed_files", "texts", "files the hand says it changed"),
        Field("tests_requested", "texts", "commands the hand asks to have run"),
        Field("risks", "texts", "what the hand thinks might bite"),
        Field("decisions", "texts", "choices it made along the way"),
        Field("memory_candidates", "objects", "things worth keeping",
              of=MEMORY_CANDIDATE),
        # ── the runtime's half ───────────────────────────────────────────
        # Every one of these is something a model could otherwise claim, and a
        # claimed success is indistinguishable from a real one in a log.
        Field("head_commit", "text", "the commit that actually exists", owner=RUNTIME),
        Field("pull_request", "text", "the PR that was actually opened", owner=RUNTIME),
        Field("ci_result", "text", "what CI actually said", owner=RUNTIME,
              choices=("passed", "failed", "running", "none")),
        Field("stopped_because", "text", "finished · failed · hard-cap · silent",
              owner=RUNTIME),
        Field("seconds", "int", "how long the hand ran", owner=RUNTIME),
        # ── the bill ─────────────────────────────────────────────────────
        # From the hand's own structured report (core/sky/usage.py), never
        # from anything the model wrote. Record everything; show money; judge
        # learning on tokens per task kind within one hand.
        Field("cost_usd", "number", "what the hand reported it cost", owner=RUNTIME),
        Field("input_tokens", "int", "tokens read by the model", owner=RUNTIME),
        Field("output_tokens", "int", "tokens written by the model", owner=RUNTIME),
        Field("cache_read_tokens", "int", "prompt-cache reads — recorded, not judged on",
              owner=RUNTIME),
        Field("cache_write_tokens", "int", "prompt-cache writes — recorded, not judged on",
              owner=RUNTIME),
        Field("turns", "int", "model turns the hand took", owner=RUNTIME),
        Field("duration_ms", "int", "wall time the hand reported", owner=RUNTIME),
    ),
)

# ── 5. context-manifest ──────────────────────────────────────────────────
CONTEXT_ITEM = Schema(
    name="context-item",
    purpose="one thing put in front of the model, and how far it may be trusted",
    fields=(
        Field("source", "text", "where it came from", required=True,
              choices=("kb", "jira", "git", "repo", "ci", "user", "web")),
        Field("source_id", "text", "its id in that system", required=True),
        Field("class", "text", "what sort of thing it is", required=True),
        Field("title", "text", "human label"),
        Field("version", "text", "which version was read"),
        Field("retrieved_at", "timestamp", "when it was read", required=True,
              owner=RUNTIME),
        # Absent is untrusted. See `may_instruct`.
        Field("trust", "text", "governed content may instruct; everything else is data",
              required=True, choices=(GOVERNED, UNTRUSTED), owner=RUNTIME),
        Field("content", "text", "the text itself", required=True),
    ),
)

CONTEXT_MANIFEST = Schema(
    name="context-manifest",
    purpose="everything the model was given, with its provenance attached",
    fields=(
        Field("context_id", "text", "this assembly", required=True, owner=RUNTIME),
        Field("run_id", "text", "the run it was assembled for", required=True,
              owner=RUNTIME),
        Field("task_id", "text", "the task", owner=RUNTIME),
        Field("issue_key", "text", "the ticket, when there is one"),
        Field("items", "objects", "what was supplied", required=True,
              of=CONTEXT_ITEM, owner=RUNTIME),
        Field("budget_tokens", "int", "the cap retrieval was held to", owner=RUNTIME),
        Field("assembled_at", "timestamp", "when", owner=RUNTIME),
    ),
)

# ── 6. session-summary ───────────────────────────────────────────────────
# Field names match the rest of the seven rather than the earlier draft's
# `harness_run_id` / `story_key`. Seven contracts naming one thing three ways
# is a defect in the specification, not a feature of it.
SESSION_SUMMARY = Schema(
    name="session-summary",
    purpose="the one verified record of a session that reaches the knowledge base",
    fields=(
        Field("memory_type", "text", "fixed", required=True,
              choices=("sky_session_summary",)),
        Field("run_id", "text", "the run", required=True, owner=RUNTIME),
        Field("task_id", "text", "the task", owner=RUNTIME),
        Field("agent_id", "text", "the agent", required=True, owner=RUNTIME),
        Field("agent_name_at_execution", "text", "its display name at the time",
              owner=RUNTIME),
        Field("owner_jira_user_id", "text", "the answerable human", owner=RUNTIME),
        Field("hand", "text", "which coding agent ran it", owner=RUNTIME,
              choices=HANDS),
        Field("role", "text", "which role it ran as", owner=RUNTIME, choices=ROLES),
        Field("kb", "text", "where this is being written", required=True,
              owner=RUNTIME),
        Field("package_version", "text", "the harness version in use", owner=RUNTIME),
        Field("project", "text", "project key"),
        Field("issue_key", "text", "the ticket, when there is one"),
        Field("outcome", "text", "how it ended", required=True, choices=OUTCOMES),
        Field("summary", "text", "what happened, in the hand's words", required=True),
        Field("learning", "texts", "what is worth knowing next time"),
        Field("sources", "texts", "verified references this rests on", owner=RUNTIME),
        Field("created_at", "timestamp", "when", required=True, owner=RUNTIME),
    ),
)

# ── 7. memory-candidate — declared above, next to agent-result ───────────


# ── the broker's own contract, deliberately NOT one of the seven ─────────
# The seven are what a *host package* must satisfy. An intent is internal: a
# hand writes one to ask for an outward action, and the broker validates and
# renders it. It is defined here so it gets the same field ownership rules —
# and the ownership is the whole point. A hand may say what it wants done. It
# may not say who approved it, when, or that it already happened.
INTENT = Schema(
    name="intent",
    purpose="a request for an outward action, written by a hand, carried out by a person",
    fields=(
        Field("kind", "text", "what is being asked for", required=True,
              choices=("push", "pr.open", "ticket.comment", "ticket.transition")),
        Field("summary", "text", "one line a person can read", required=True),
        Field("branch", "text", "the branch, for push and pr.open"),
        Field("remote", "text", "the remote, for push"),
        Field("base", "text", "the target branch, for pr.open"),
        Field("title", "text", "the pull request title"),
        Field("body", "text", "the pull request or comment body"),
        Field("issue_key", "text", "the ticket, for ticket.*"),
        Field("to_state", "text", "the state, for ticket.transition"),
        # ── the runtime's half ───────────────────────────────────────────
        Field("intent_id", "text", "this request's id", owner=RUNTIME),
        Field("run_id", "text", "the run that asked", required=True, owner=RUNTIME),
        Field("agent_id", "text", "which agent asked", required=True, owner=RUNTIME),
        Field("created_at", "timestamp", "when it was asked", owner=RUNTIME),
        # Approval is a runtime fact about a person's decision. A model that
        # could assert it could approve its own outward action, which is the
        # entire thing the broker exists to prevent.
        Field("approved_by", "text", "the verified person who approved it",
              owner=RUNTIME),
        Field("approved_at", "timestamp", "when they did", owner=RUNTIME),
        Field("channel", "text", "the door the approval arrived through",
              owner=RUNTIME),
        Field("executed", "bool", "whether it has been carried out", owner=RUNTIME),
    ),
)


SCHEMAS: dict[str, Schema] = {
    s.name: s for s in (
        AGENT_CARD, TASK, RUN_EVENT, AGENT_RESULT,
        CONTEXT_MANIFEST, SESSION_SUMMARY, MEMORY_CANDIDATE,
    )
}

#: What a host package must satisfy to be supported. `context-item` is nested
#: inside the manifest and is not one of the seven.
THE_SEVEN = tuple(SCHEMAS)


# ── publishing ───────────────────────────────────────────────────────────
_JSON_TYPES = {
    "text": {"type": "string", "minLength": 1},
    "timestamp": {"type": "string", "format": "date-time"},
    "int": {"type": "integer"},
    "number": {"type": "number"},
    "bool": {"type": "boolean"},
    "texts": {"type": "array", "items": {"type": "string"}},
    "map": {"type": "object"},
    "objects": {"type": "array", "items": {"type": "object"}},
}


def json_schema(schema: Schema, *, _nested: bool = False) -> dict:
    """Emit JSON Schema, so a host in another language reads the same contract.

    Generated rather than hand-written: two copies of a contract are two
    contracts, and the second one is always the stale one. `schemas/*.json`
    in this repository is the output of this function and a test says so.
    """
    properties: dict[str, Any] = {}
    for f in schema.fields:
        body = dict(_JSON_TYPES[f.kind])
        if f.choices:
            if f.kind == "texts":
                body["items"] = {"enum": list(f.choices)}
            else:
                body.pop("minLength", None)
                body["enum"] = list(f.choices)
        if f.kind == "objects" and f.of is not None:
            body["items"] = json_schema(f.of, _nested=True)
        body["description"] = f.note
        body["x-written-by"] = f.owner
        properties[f.name] = body
    out: dict[str, Any] = {}
    if not _nested:
        # `$schema` and `$id` belong to a schema *resource*. Repeating them on
        # an inline subschema declares a second resource inside the first,
        # which a strict validator resolves as its own document.
        out["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        # A `$id` is an identifier, not an address — nothing fetches it. It
        # used to carry one company's domain, which then travelled into every
        # published schema and, once the runtime was vendored, into the
        # plugin. `urn:` says "a name, not a location" and belongs to nobody.
        out["$id"] = f"urn:sky:schema:{schema.name}"
    out.update({
        "title": schema.name,
        "description": schema.purpose,
        "type": "object",
        "properties": properties,
        "required": [f.name for f in schema.fields if f.required],
        "additionalProperties": schema.open,
    })
    if not out["required"]:
        del out["required"]
    if schema.name == "run-event":
        # Document emitted kinds without closing the extensible event contract.
        out["x-known-kinds"] = list(EVENT_KINDS)
    return out


def publish(directory) -> list:
    """Write the seven JSON Schema files. Run as `python -m sky.schemas`."""
    from pathlib import Path as _Path
    directory = _Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in SCHEMAS.items():
        path = directory / f"{name}.schema.json"
        path.write_text(json.dumps(json_schema(schema), indent=2) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":                                 # pragma: no cover
    import sys
    from pathlib import Path as _Path
    target = _Path(sys.argv[1]) if len(sys.argv) > 1 else \
        _Path(__file__).resolve().parents[2] / "schemas"
    for p in publish(target):
        print(p)
