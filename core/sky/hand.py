"""Running a coding agent, and stopping one that has stopped working.

A hand is an opaque subprocess that may run for half an hour and may stop
producing anything at all without exiting. Two watchdogs, because those are two
different failures:

    hard cap      the longest a run may take
    silence cap   the longest it may produce nothing

**The silence cap is the one that matters**, and it is the one usually missing.
A hand that is genuinely stuck emits nothing, so it sails past every check that
only runs after a line arrives. Both caps are therefore enforced from a separate
thread that watches the clock, never from inside the loop reading output — that
mistake let one run continue for three hours under a thirty-minute limit.

Two smaller lessons, both learned by something going wrong:

*stdin is closed.* A hand that inherits a terminal will happily wait forever for
an answer nobody is there to give.

*The process group is killed, not the process.* A hand spawns children — a test
runner, a language server — and killing only the parent leaves them holding the
work directory.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

HARD_CAP_SEC = 1800
SILENCE_CAP_SEC = 420


@dataclass
class Result:
    ok: bool
    reason: str            # finished · failed · hard-cap · silent · not-installed
    exit_code: int | None
    log: Path
    seconds: float
    tail: str = ""

    def __str__(self) -> str:
        return (f"{self.reason} after {self.seconds:.0f}s"
                + (f" (exit {self.exit_code})" if self.exit_code is not None else ""))


def _stop(process: subprocess.Popen, job=None) -> None:
    """Ask the whole group, then insist. A hand has children."""
    if os.name == "nt":
        _stop_windows(process, job)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except OSError:
                return
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def _kernel32():
    """kernel32 with the calls used here typed, so handles survive on 64-bit."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel32


def _windows_job(process: subprocess.Popen):
    """Windows' answer to a process group: a job object, or None.

    Windows has no process groups and no SIGKILL. `taskkill /T` walks the
    parent links, but those break whenever a middle process has exited — a
    shell that started something in the background, say — and the orphan
    keeps the output pipe open, so the read loop waits on it for ever. A job
    holds every descendant however it was started, and ends them all at once.
    """
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
        kernel32.CloseHandle(job)
        return None
    return job


def _stop_windows(process: subprocess.Popen, job=None) -> None:
    """End the job, then the tree by its parent links, then the hand itself."""
    if process.poll() is not None and not job:
        return
    if job:
        _kernel32().TerminateJobObject(job, 1)
    if process.poll() is None:
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run(command: list[str], *, env: dict[str, str], cwd: Path, log_path: Path,
        hard_cap: int = HARD_CAP_SEC, silence_cap: int = SILENCE_CAP_SEC,
        on_line=None) -> Result:
    """Run one hand to completion, or stop it. Never raises for the hand's sake."""
    started = time.monotonic()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        log = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")
    except OSError as exc:
        return Result(False, "failed", None, log_path, 0.0, f"cannot open log: {exc}")

    job = None
    try:
        try:
            process = subprocess.Popen(
                command, cwd=str(cwd), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,      # never wait for an answer nobody will give
                text=True, bufsize=1,
                start_new_session=True,        # its own group, so children die with it
            )
        except FileNotFoundError:
            return Result(False, "not-installed", None, log_path, 0.0,
                          f"{command[0]} is not on PATH")
        except OSError as exc:
            return Result(False, "failed", None, log_path, 0.0, str(exc))
        if os.name == "nt":
            job = _windows_job(process)    # start_new_session is POSIX-only

        state = {"last": time.monotonic(), "stopped_by": ""}
        tail: list[str] = []

        def watchdog() -> None:
            """The clock is watched here, and nowhere else.

            Checking elapsed time inside the read loop cannot work: a stalled
            hand produces no lines, so the loop blocks and the check never runs.
            """
            while process.poll() is None:
                now = time.monotonic()
                if now - started > hard_cap:
                    state["stopped_by"] = "hard-cap"
                    _stop(process, job)
                    return
                if now - state["last"] > silence_cap:
                    state["stopped_by"] = "silent"
                    _stop(process, job)
                    return
                time.sleep(1)

        watcher = threading.Thread(target=watchdog, daemon=True)
        watcher.start()

        assert process.stdout is not None
        for line in process.stdout:
            state["last"] = time.monotonic()
            log.write(line)
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)
            if on_line is not None:
                on_line(line)

        # The pipe is ours to close. When the watchdog kills a hand, the read
        # loop ends without the pipe being drained, and the reader is left open.
        if process.stdout is not None:
            process.stdout.close()
        code = process.wait()
        watcher.join(timeout=3)
        seconds = time.monotonic() - started
        stopped = state["stopped_by"]
        if stopped:
            reason, ok = stopped, False
        elif code == 0:
            reason, ok = "finished", True
        else:
            reason, ok = "failed", False
        return Result(ok, reason, code, log_path, seconds, "".join(tail))
    finally:
        log.close()
        if job:
            _kernel32().CloseHandle(job)
