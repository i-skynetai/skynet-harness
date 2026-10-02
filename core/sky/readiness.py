"""What a brain is made of, whether each part is alive, and what it may do.

A brain is assembled for one task from four suppliers, so it can be *partly*
assembled. This module says which parts are live and what that permits.

Two rules run through all of it, and both were learned the hard way:

**A pass needs a positive observation.** Never "no error", never "configured",
never "connected" — something came back and it was the right shape. Ingest
reported COMPLETED with zero entities for two days; every configuration-level
check called it healthy throughout.

**Readiness is per kind of task.** One green light forces a false choice
between blocking someone who only wants an answer and letting someone build
with no guard. The rule that falls out: *a brain with no Safety may answer and
review, but may not build.*

The probe contracts are the docstrings of `probes.py` and the tests that break
each probe on purpose (`core/tests/test_g23b_probes_detect_breaks.py`). This
module implements them; it does not get to reinterpret them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    OK = "ok"                 # a live call answered, with the right shape
    DEGRADED = "degraded"     # works, but weaker than it looks
    MISSING = "missing"       # never configured
    DOWN = "down"             # configured, and the probe failed
    NA = "n/a"                # not applicable on this host

    @property
    def usable(self) -> bool:
        return self in (State.OK, State.DEGRADED)


class Part(str, Enum):
    """The ten things a brain does, in the names the product uses.

    The brain terms survive only as a second label in the documents. Nothing a
    user reads should require knowing which lobe does what.
    """
    INPUTS = "inputs"                  # 1 sensory
    FOCUS = "focus"                    # 2 attention
    SHORT_TERM = "short-term memory"   # 3 working memory
    REMEMBERING = "remembering"        # 4 hippocampus
    KNOWLEDGE = "knowledge"            # 5 cortex — the KB
    THINKING = "thinking"              # 6 prefrontal
    SAFETY = "safety"                  # 7 amygdala
    HABITS = "habits"                  # 8 basal ganglia
    QUALITY = "quality control"        # 9 cerebellum
    ACTIONS = "actions"                # 10 motor


class Kind(str, Enum):
    QUESTION = "question"
    REVIEW = "review"
    BUILD = "build"
    LEARN = "learn"


#: What each kind of work needs alive. Straight from the design's §3.1 table.
#: SAFETY under BUILD and LEARN is the whole reason this module exists.
REQUIRES: dict[Kind, tuple[Part, ...]] = {
    Kind.QUESTION: (Part.KNOWLEDGE, Part.FOCUS, Part.THINKING, Part.SHORT_TERM),
    Kind.REVIEW: (Part.KNOWLEDGE, Part.FOCUS, Part.THINKING, Part.SHORT_TERM,
                  Part.QUALITY),
    Kind.BUILD: (Part.KNOWLEDGE, Part.FOCUS, Part.THINKING, Part.SHORT_TERM,
                 Part.QUALITY, Part.SAFETY, Part.HABITS, Part.ACTIONS),
    Kind.LEARN: (Part.KNOWLEDGE, Part.FOCUS, Part.THINKING, Part.SHORT_TERM,
                 Part.REMEMBERING, Part.SAFETY),
}


@dataclass
class Observation:
    """One probe's result. `detail` is what was actually seen, not a verdict.

    `detail` carries the positive observation — "5 hits, 380 ms", "0 entities" —
    because a reader deciding whether to trust a green needs the evidence, and
    because a `down` is only actionable if it says what happened.
    """
    part: Part
    state: State
    detail: str = ""
    blocks: tuple[Kind, ...] = ()

    def __str__(self) -> str:
        mark = {State.OK: "ok", State.DEGRADED: "degraded", State.MISSING: "MISSING",
                State.DOWN: "DOWN", State.NA: "n/a"}[self.state]
        return f"{self.part.value:<18} {mark:<9} {self.detail}"


@dataclass
class Brain:
    """A set of observations, and what they permit."""
    observations: list[Observation] = field(default_factory=list)

    def add(self, part: Part, state: State, detail: str = "") -> None:
        self.observations.append(Observation(part, state, detail))

    def state_of(self, part: Part) -> State:
        for o in self.observations:
            if o.part is part:
                return o.state
        return State.MISSING

    def blockers(self, kind: Kind) -> list[Observation]:
        """The parts stopping this kind of work — named, so the answer is a fix."""
        out = []
        for part in REQUIRES[kind]:
            state = self.state_of(part)
            if not state.usable:
                out.append(next(
                    (o for o in self.observations if o.part is part),
                    Observation(part, State.MISSING, "not probed"),
                ))
        return out

    def ready_for(self, kind: Kind) -> bool:
        return not self.blockers(kind)

    def ready_kinds(self) -> list[Kind]:
        return [k for k in Kind if self.ready_for(k)]

    def table(self, enforced: bool = True) -> str:
        """The doctor's output. The header is the part people act on."""
        ready = self.ready_kinds()
        can = ", ".join(k.value for k in ready) or "nothing"
        cannot = [k.value for k in Kind if k not in ready]
        head = f"ready for: {can}"
        if cannot:
            head += f"      NOT: {', '.join(cannot)}"
        lines = [head, ""]
        for o in sorted(self.observations, key=lambda o: list(Part).index(o.part)):
            lines.append("  " + str(o))
        for kind in cannot:
            blocking = self.blockers(Kind(kind))
            names = ", ".join(b.part.value for b in blocking)
            lines.append(f"\n  {kind} is blocked by: {names}")
        if not enforced:
            lines.append(
                "\n  ADVISORY — this session was not started by `sky build`, so the "
                "environment is not\n  scrubbed and the policy tiers below A are not "
                "enforced here."
            )
        return "\n".join(lines)
