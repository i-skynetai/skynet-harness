"""The run record — what actually happened, captured outside the model.

A model writes a useful summary and is not evidence. Everything here is written
by the runtime: the identifier exists before the hand starts, so the model never
chooses it, and the events are appended by code the hand does not call.

What this is worth, stated plainly: **deterministic correlation for the actions
that pass through the runtime.** It is not proof of everything an agent did — a
hand with a shell can create an artifact outside this path — and the record sits
on the same machine as the thing it records, so it is not tamper-proof either.
Useful, and not more than that.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

def state_dir() -> Path:
    """Resolved on every call, never at import.

    Bound at import it is fixed before a caller — a test, a wrapper — can set
    SKY_STATE_DIR, so the test suite wrote into the real home directory and
    failed there. A constant that reads the environment is a constant that is
    wrong for anyone who sets it late.
    """
    return Path(os.environ.get("SKY_STATE_DIR", "~/.local/state/sky")).expanduser()


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


@dataclass
class Run:
    """One execution. Created before anything else happens."""
    run_id: str
    directory: Path
    agent_id: str
    role: str
    task: str
    kb: str

    @classmethod
    def start(cls, *, role: str, task: str, kb: str, agent_id: str,
              root: Path | None = None) -> "Run":
        root = root or (state_dir() / "runs")
        root.mkdir(parents=True, exist_ok=True)
        # Creation IS the claim. Checking whether a directory exists and then
        # creating it leaves a window two runs can both pass through — a
        # threaded reproduction raised FileExistsError — so mkdir does the
        # deciding, and losing the race just means trying the next number.
        base = f"run-{_stamp()}"
        for n in range(1, 1000):
            run_id = f"{base}-{n:03d}"
            directory = root / run_id
            try:
                directory.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError(f"1000 runs already started in this second under {root}")
        run = cls(run_id=run_id, directory=directory, agent_id=agent_id,
                  role=role, task=task, kb=kb)
        run.event("run.start", role=role, task=task, kb=kb, agent_id=agent_id)
        return run

    # ── events ───────────────────────────────────────────────────────────
    def event(self, kind: str, /, **fields) -> None:
        """Append one fact. Never raises — losing the record must not stop work.

        `kind` is positional-only: a caller recording a field of its own called
        "kind" is completely reasonable, and without the `/` that collides with
        this parameter and raises instead of recording.
        """
        # The event's own name and time cannot be overwritten by a caller's
        # field. Splatting fields last let `kind="build"` silently replace the
        # event name — the record survived, saying the wrong thing, which in an
        # audit log is worse than the crash that preceded it. A colliding field
        # is kept under a prefixed name rather than dropped.
        record = {"t": time.time(), "kind": kind}
        for key, value in fields.items():
            record["field_" + key if key in record else key] = value
        line = json.dumps(record, default=str, ensure_ascii=False)
        try:
            with open(self.directory / "events.jsonl", "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def refused(self, why: str, **fields) -> None:
        """A refusal is a result, and is recorded as carefully as a success."""
        self.event("run.refused", why=why, **fields)

    def finish(self, outcome: str, **fields) -> None:
        self.event("run.finish", outcome=outcome, **fields)

    # ── the stamp every artifact carries ─────────────────────────────────
    def trailer(self) -> str:
        """The commit trailer. Written by the runtime, never by the model.

        The broker refuses to push a commit that does not carry this exact
        line — which is what turns "the model cannot omit it" from a hope into
        a check, since the hand runs `git commit` itself.
        """
        return f"SKY-Agent: {self.agent_id} {self.run_id}"

    def stamp(self) -> dict:
        return {"sky_agent": self.agent_id, "sky_run": self.run_id,
                "sky_role": self.role, "sky_task": self.task, "sky_kb": self.kb}
