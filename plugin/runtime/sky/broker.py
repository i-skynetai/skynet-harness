"""The broker's first half: validate an intent, and render it as a command.

An **intent** is a hand saying *I would like this pushed*. It is not a push.
This module turns that request into the exact command a person then runs, and
**executes nothing** — execution is H8, behind gate G24, and standing grants
wait for the isolation boundary in H10/G25. Until then the last step of every
outward action is a human pressing return.

Three rules, and each one exists because the alternative has a name:

**Nothing the model wrote reaches a command unvalidated.** A branch name is
matched against a pattern, a remote against a pattern, and anything carrying a
shell metacharacter is refused rather than quoted. The failure being prevented
is command injection through a field a model filled in — and "we quote it
properly" is a defence that holds until one caller forgets.

**One command does one thing.** A rendered line never chains. A person shown
`git push && gh pr create && …` can only agree to all of it, which is not
consent, it is a dare.

**A model may not assert approval.** `approved_by`, `approved_at`, `channel`
and `executed` are runtime-owned on the intent contract. A hand that could
write `approved_by` could approve its own push, and the broker would be
ceremony.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import schemas

#: What a git ref may look like. Deliberately narrower than git's own rules:
#: this is what we are willing to put on a command line, not what git accepts.
#:
#: **It must start with a letter or a digit.** An earlier version allowed a
#: leading hyphen, and `--mirror` is a perfectly good match for "letters and
#: hyphens" — which rendered `git push origin --mirror`, a command that
#: overwrites every ref on the remote. No metacharacter is involved, so
#: refusing shell metacharacters does not catch it: **an argument that turns
#: into an option is its own injection**, and it needs its own rule.
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TICKET = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")
STATE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,40}$")

#: Characters that turn one command into several. A field containing any of
#: them is refused — never escaped, because an escaping bug is silent and a
#: refusal is not.
DANGEROUS = set(";|&$`\n\r\\<>(){}[]!*?\"'")


def _commented(text: str) -> list[str]:
    """Every line of `text` as a comment. Never one `#` and a hope."""
    return [f"# {line}" for line in str(text).splitlines() or [""]]


class Refused(Exception):
    """The intent will not be rendered, and why. Always actionable."""


@dataclass(frozen=True)
class Rendered:
    kind: str
    summary: str
    #: The command a person runs, or "" when this kind has no command and is
    #: carried out in a web interface instead.
    command: str
    #: Text that goes with it — a pull request body, a comment. Shown, never
    #: put on a command line.
    body: str = ""
    note: str = ""

    def __str__(self) -> str:
        """Rendered so that **every line a person can run is one this made**.

        A summary is written by a model. One with a newline in it used to break
        out of the `#` comment and put a second, unapproved line into the
        output — `git push --force origin main` sitting above the approved
        command, indistinguishable from it, in text whose whole purpose is
        "these are the commands, run them". Commenting is therefore applied per
        line, not to the first one and hopefully the rest.
        """
        out = _commented(self.summary)
        if self.note:
            out += _commented(self.note)
        if self.command:
            out.append(self.command)          # validated; the only live line
        if self.body:
            # The body is data — a pull request description, a ticket comment —
            # and it is **commented too**. Fencing it was not enough: a fence is
            # a label, and a person selecting this block and pasting it into a
            # shell still gets every body line as a command. A body containing
            # `git push --force origin main` is not hypothetical; it is what a
            # model writes when summarising what it did.
            out += ["#"] + _commented(self.body)
            out += ["# (the text above is the body, one `# ` per line — strip "
                    "the prefix to use it)"]
        return "\n".join(out)


def _clean(value, field: str, pattern: re.Pattern) -> str:
    text = str(value or "").strip()
    if not text:
        raise Refused(f"{field} is empty, and a command with a blank {field} is "
                      f"not something to guess at")
    if set(text) & DANGEROUS:
        bad = "".join(sorted(set(text) & DANGEROUS))
        raise Refused(f"{field} contains {bad!r}, which can turn one command "
                      f"into several. Refused rather than escaped.")
    if text.startswith("-"):
        # Said separately from the pattern, because the reason matters: this is
        # not a malformed name, it is an option wearing a name's clothes.
        raise Refused(
            f"{field} is {text!r}, which begins with '-' and would be read by "
            f"git as an OPTION rather than a {field}. Refused.")
    if not pattern.match(text):
        raise Refused(f"{field} is {text!r}, which is not a shape this will put "
                      f"on a command line")
    return text


def accept(written_by_hand: dict, **runtime) -> dict:
    """Take what a hand wrote, refuse what it may not say, and seal the rest.

    This is the door. `source=MODEL` is the load-bearing argument: a hand that
    puts `approved_by` in its own intent is refused here rather than quietly
    overwritten, because "the model tried to approve its own push" is a thing
    somebody should be told about, not a field that silently loses.

    `run_id` and `agent_id` then come from the runtime, which is the only
    party that knows them truthfully.
    """
    problems = schemas.validate(schemas.INTENT, written_by_hand,
                                source=schemas.MODEL)
    # Required runtime fields are the runtime's to supply; their absence from
    # what a hand wrote is correct, not a fault.
    problems = [p for p in problems
                if not any(p.startswith(f"{n}: is required")
                           for n in schemas.INTENT.runtime_fields())]
    if problems:
        raise Refused("this intent does not match its contract:\n"
                      + "\n".join(f"    {p}" for p in problems))
    return schemas.seal(schemas.INTENT, written_by_hand, **runtime)


def validate(intent: dict) -> dict:
    """Check a sealed intent — one the runtime has already stamped."""
    problems = schemas.validate(schemas.INTENT, intent, source=schemas.RUNTIME)
    if problems:
        raise Refused("this intent does not match its contract:\n"
                      + "\n".join(f"    {p}" for p in problems))
    return intent


def render(intent: dict) -> Rendered:
    """One intent, one thing a person does. Never executed here."""
    validate(intent)
    kind = intent["kind"]
    summary = str(intent["summary"]).strip()
    if "\n" in summary or "\r" in summary:
        raise Refused(
            "the summary runs to more than one line. A summary is a single "
            "line a person reads above the command; a second line in it is a "
            "second line in the output, which is how an unapproved command "
            "gets into a list of approved ones.")

    if kind == "push":
        remote = _clean(intent.get("remote") or "origin", "remote", REMOTE)
        branch = _clean(intent.get("branch"), "branch", BRANCH)
        if branch in ("main", "master"):
            raise Refused(
                f"this asks to push {branch!r} directly. That is the branch "
                "other people build on; push a branch and open a pull request.")
        return Rendered(kind, summary, f"git push {remote} {branch}",
                        note="review `git log` and `git diff` against the base first")

    if kind == "pr.open":
        branch = _clean(intent.get("branch"), "branch", BRANCH)
        base = _clean(intent.get("base"), "base", BRANCH)
        title = str(intent.get("title") or "").strip()
        if not title:
            raise Refused("a pull request with no title is one nobody will read")
        if set(title) & DANGEROUS:
            raise Refused("the title contains characters that cannot go on a "
                          "command line; put it in through the web interface")
        return Rendered(
            kind, summary,
            f'gh pr create --base {base} --head {branch} --title "{title}" --body-file -',
            body=str(intent.get("body") or ""),
            note="the body below is piped in; read it before you do — it becomes public")

    if kind == "ticket.comment":
        issue = _clean(intent.get("issue_key"), "issue_key", TICKET)
        body = str(intent.get("body") or "").strip()
        if not body:
            raise Refused("an empty comment is not worth posting")
        return Rendered(
            kind, summary, "",
            body=body,
            note=f"post this on {issue} yourself. It is rendered rather than "
                 f"run because a comment carries your name, and because text "
                 f"that came out of a knowledge base can carry more than you "
                 f"meant to make visible on a ticket")

    if kind == "ticket.transition":
        issue = _clean(intent.get("issue_key"), "issue_key", TICKET)
        state = _clean(intent.get("to_state"), "to_state", STATE)
        return Rendered(
            kind, summary, "",
            note=f"move {issue} to {state!r} yourself. A state change is a "
                 f"statement about work being done, and the person answerable "
                 f"for it makes that statement")

    raise Refused(f"{kind!r} is not a kind this renders")


def read_pending(directory: Path) -> list[dict]:
    """Intents a hand left behind, oldest first. Unreadable ones are reported.

    A file that will not parse is surfaced as a refusal rather than skipped:
    an intent silently dropped is an outward action somebody believes happened.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    out = []
    # `sky intent` leads each name with a nanosecond sequence, so name order is
    # creation order; `created_at` first keeps that true for a file renamed by hand.
    def made(path: Path):
        try:
            when = json.loads(path.read_text(encoding="utf-8")).get("created_at")
        except (ValueError, OSError, AttributeError):
            when = None
        return (when or "", path.name)

    for path in sorted(directory.glob("*.json"), key=made):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            out.append({"kind": "unreadable", "summary": f"{path.name}: {exc}"})
            continue
        if isinstance(body, dict):
            body.setdefault("intent_id", path.stem)
            out.append(body)
    return out


def render_all(intents) -> list[tuple[dict, Rendered | Refused]]:
    """Render each, keeping refusals beside the intent that caused them.

    Returned rather than raised: one bad intent must not hide the four good
    ones, and a person needs to see both lists.
    """
    results = []
    for intent in intents:
        try:
            results.append((intent, render(intent)))
        except Refused as exc:
            results.append((intent, exc))
    return results
