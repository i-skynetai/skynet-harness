"""Can this repository's tests actually be run?

Quality control is the brain function that answers that, and gate G23a fixes
how: *run the repository's own test command with a selector that matches
nothing; healthy is that the runner starts and reports zero tests.*

Two things that mechanism buys, and both are the point:

**It is a positive observation.** The runner was found, started, read the
repository's configuration and answered. That is what distinguishes this from
"a `tests/` directory exists" — which is a configuration-level check of exactly
the kind that called a broken ingest healthy for two days.

**It costs nothing.** A selector matching nothing means the suite does not run.
A probe that takes four minutes is a probe someone turns off, and a turned-off
probe is worse than none because the table still has a row for it.

**The trap, measured rather than assumed.** `pytest` and `python -m unittest`
both exit **5** when no test matches. That is the *healthy* answer here, and a
probe reading the exit code as pass/fail would invert itself — calling a working
runner broken, and refusing every build on a repository whose tests are fine.
So the exit code is interpreted per runner, never generically.

What this deliberately does not do is run the actual suite. Whether the tests
*pass* is the developer's business and the validator's; whether they *can be
run at all* is the brain's.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: A selector no test can match. Fixed rather than random so a failure is
#: reproducible by hand from the log.
NO_MATCH = "sky_probe_no_such_test_zzq"

TIMEOUT = 60
#: Windows has no `python3`; what answers to the name there is usually the
#: Store's stand-in, which exits 9009 and would read as a broken suite. The
#: interpreter running this is the nearest honest answer.
PYTHON = sys.executable if os.name == "nt" else "python3"


@dataclass(frozen=True)
class Runner:
    name: str
    command: tuple[str, ...]
    #: Exit codes that mean "started fine, matched nothing" for this runner.
    zero_codes: frozenset[int]
    #: Text that confirms it, when the runner says so in words. Belt and
    #: braces: an exit code is a number, and numbers get reused.
    zero_says: tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"{self.name}: {' '.join(self.command)}"


@dataclass(frozen=True)
class Ambiguous:
    """Several subdirectories have test suites. Which one the task concerns is
    not something a probe can know, so it does not choose."""
    runners: tuple[str, ...]
    where: tuple[str, ...]

    def __str__(self) -> str:
        return (f"{len(self.where)} subdirectories have test suites "
                f"({', '.join(self.where)}) — run from the one this task is "
                f"about, or set one in configuration")


@dataclass(frozen=True)
class NoRunner:
    """Nothing here looks like a test suite — with what was looked for."""
    looked_for: tuple[str, ...]

    def __str__(self) -> str:
        return "no test runner found (looked for " + ", ".join(self.looked_for) + ")"


def _reads(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _npm_runner(root: Path) -> Runner | None:
    """jest and vitest take a name selector; anything else cannot be probed.

    `npm test` on its own runs the whole suite, which is exactly what must not
    happen here — so a `test` script whose runner is unrecognised is reported
    as unprobeable rather than run.
    """
    package = root / "package.json"
    if not package.is_file():
        return None
    try:
        body = json.loads(_reads(package))
    except ValueError:
        return None
    if not isinstance(body, dict) or "test" not in (body.get("scripts") or {}):
        return None
    deps = {**(body.get("devDependencies") or {}), **(body.get("dependencies") or {})}
    script = str((body.get("scripts") or {}).get("test", ""))
    for tool in ("jest", "vitest"):
        if tool in deps or tool in script:
            # `--passWithNoTests` makes "matched nothing" a clean exit 0, which
            # is what this probe wants to see.
            return Runner(
                tool,
                ("npm", "test", "--silent", "--",
                 "--testNamePattern", NO_MATCH, "--passWithNoTests"),
                frozenset({0}),
                ("no tests", "0 passed", "No test files found"))
    return None


#: Directories never worth descending into looking for a test suite.
_SKIP = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__",
                   "dist", "build", "target", ".tox", ".mypy_cache", "docs"})


def detect(root: Path, *, _descend: bool = True) -> Runner | NoRunner:
    """Which runner this repository uses. Looks at files, never guesses.

    Ordered by how specific the evidence is: an explicit pytest configuration
    beats the presence of a `tests/` directory.

    **One level down, when the root has nothing.** A repository that keeps its
    code in a subdirectory is ordinary — this one keeps its tests in `core/` —
    and a probe that only looks at the root reports "no test runner" for a
    repository with a perfectly good suite. That is a false MISSING, and a
    false MISSING refuses every build.

    If *several* children have runners it does not choose: which one a task
    concerns is not something this can know, so it says so and lets the person
    decide. Guessing would be worse than saying.
    """
    root = Path(root)
    looked_for = ("pytest.ini", "pyproject.toml", "package.json", "go.mod",
                  "Cargo.toml", "tests/", "Makefile")

    pyproject = _reads(root / "pyproject.toml")
    if (root / "pytest.ini").is_file() or (root / "setup.cfg").is_file() and \
            "[tool:pytest]" in _reads(root / "setup.cfg") or "[tool.pytest" in pyproject:
        return Runner("pytest",
                      (PYTHON, "-m", "pytest", "--collect-only", "-q", "-k", NO_MATCH),
                      frozenset({5}), ("no tests ran", "no tests collected"))

    npm = _npm_runner(root)
    if npm is not None:
        return npm

    if (root / "go.mod").is_file():
        return Runner("go", ("go", "test", "-run", "^$", "./..."),
                      frozenset({0}), ("no test files", "ok"))

    if (root / "Cargo.toml").is_file():
        return Runner("cargo", ("cargo", "test", "--", "--exact", NO_MATCH),
                      frozenset({0}), ("0 passed", "running 0 tests"))

    for directory in ("tests", "test"):
        if (root / directory).is_dir():
            # Python 3.12 exits 5 and prints "NO TESTS RAN" for an empty
            # selection; 3.11 exits 0 and prints "Ran 0 tests … OK". Both are
            # the healthy answer, so both phrases are read (SH-051).
            return Runner("unittest",
                          (PYTHON, "-m", "unittest", "discover",
                           "-s", directory, "-p", f"{NO_MATCH}*.py"),
                          frozenset({5}), ("no tests ran", "ran 0 tests"))

    if _descend:
        found = []
        try:
            children = sorted(c for c in root.iterdir()
                              if c.is_dir() and c.name not in _SKIP
                              and not c.name.startswith("."))
        except OSError:
            children = []
        for child in children:
            runner = detect(child, _descend=False)
            if isinstance(runner, Runner):
                # The command runs in `root`, so its paths must be relative to it.
                found.append(Runner(runner.name,
                                    tuple(_rebase(a, child.name) for a in runner.command),
                                    runner.zero_codes, runner.zero_says))
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return Ambiguous(tuple(sorted({r.name for r in found})),
                             tuple(c.name for c in children
                                   if isinstance(detect(c, _descend=False), Runner)))
    return NoRunner(looked_for)


def _rebase(argument: str, directory: str) -> str:
    """A discovered subdirectory command still runs from the repository root."""
    return f"{directory}/{argument}" if argument in ("tests", "test") else argument


@dataclass(frozen=True)
class Result:
    state: str          # ok · degraded · missing · down
    detail: str
    runner: str = ""


def check(root: Path) -> Result:
    """Start the runner, match nothing, and read what it says."""
    root = Path(root)
    found = detect(root)
    if isinstance(found, Ambiguous):
        return Result("degraded", str(found), ", ".join(found.runners))
    if isinstance(found, NoRunner):
        # A Makefile with a test target is a real suite that this cannot probe
        # cheaply: `make test` takes no selector, so probing it would mean
        # running it. Say so rather than reporting nothing, and rather than
        # running a four-minute suite on every doctor.
        makefile = _reads(root / "Makefile")
        if "test:" in makefile:
            return Result("degraded",
                          "a Makefile `test` target exists, but make takes no "
                          "selector — running it would run the whole suite, so "
                          "this is not probed",
                          "make")
        return Result("missing", str(found))

    try:
        out = subprocess.run(list(found.command), cwd=str(root),
                             capture_output=True, text=True, timeout=TIMEOUT,
                             encoding="utf-8", errors="replace",
                             stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return Result("missing", f"{found.command[0]} is not on PATH, so "
                                 f"{found.name} cannot be run here", found.name)
    except subprocess.TimeoutExpired:
        # A runner that hangs on an empty selection is broken, not absent.
        return Result("down", f"{found.name} did not answer within {TIMEOUT}s on a "
                              f"selection that matches nothing", found.name)
    except OSError as exc:
        return Result("down", f"{found.name} could not be started: {exc}", found.name)

    said = ((out.stdout or "") + (out.stderr or "")).lower()
    # The exit code is interpreted per runner. pytest and unittest exit 5 for
    # "nothing matched", which is the healthy answer, so a generic
    # returncode-means-failure reading would invert this probe.
    if out.returncode in found.zero_codes or \
            any(phrase.lower() in said for phrase in found.zero_says):
        return Result("ok", f"{found.name} ran and reported zero tests, as it must "
                            f"for a selector that matches nothing", found.name)
    if out.returncode == 0:
        # It started and exited cleanly, but said nothing this code recognises.
        # Probably fine; not a positive observation, so not OK.
        return Result("degraded",
                      f"{found.name} exited cleanly but did not say it collected "
                      f"zero tests — it may have run something", found.name)
    # A runner that is configured but not installed is MISSING, not DOWN: the
    # fix is "install it", not "your test setup is broken". `python -m pytest`
    # on a machine without pytest exits 1 with "No module named pytest" — it is
    # not a FileNotFoundError, because `python3` itself was found.
    if "no module named" in said or "command not found" in said:
        return Result("missing",
                      f"{found.name} is configured here but is not installed — "
                      f"install it and this passes", found.name)
    tail = " ".join((out.stderr or out.stdout or "").split())[-160:]
    return Result("down", f"{found.name} failed to start: exit {out.returncode} — {tail}",
                  found.name)
