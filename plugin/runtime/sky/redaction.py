"""The gate anything bound for a knowledge base passes through.

Found the hard way: session transcripts carry live credentials, because past
sessions were often *about* configuring credentials. A knowledge base is
long-lived and searchable, so a secret written into one is worse than a secret
in a terminal scrollback — it is indexed, retrievable, and it will be handed
back to somebody later as context.

**A match refuses the write; it does not scrub and continue.** A silent scrub
hides that it nearly happened, and the near-miss is the thing worth knowing.
`scrub` exists for a different job — cleaning text on its way *to* a hand, so
the hand never sees a secret it could copy forward.

Two failure modes, and both are real:

*Missing a secret* puts a credential in the KB permanently. That is the one the
patterns are tuned against, and why the last pattern is deliberately broad.

*Firing on ordinary text* is not harmless either. A gate that refuses good
writes teaches people to work around it, and a gate people work around is not a
gate. The test suite holds a corpus of text that must NOT match, and it is as
load-bearing as the corpus that must.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Ordered most specific first, so a labelled report names the real thing
#: rather than the catch-all.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("knowledge-base-pat", re.compile(r"\bkb_pat_[A-Za-z0-9_\-]{16,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("gitlab-pat", re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("github-pat", re.compile(r"\b(?:ghp|gho|ghs|ghr)_[A-Za-z0-9]{30,}"
                              r"|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("atlassian-token", re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
                               r"-----END [A-Z ]*PRIVATE KEY-----")),
    ("bearer-header", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{16,}")),
    # Last resort, and deliberately broad: an assignment whose NAME says it is a
    # secret. A false positive costs one refused write and a human glance; a
    # false negative costs a credential in a searchable store forever.
    ("named-secret", re.compile(
        r"(?i)\b(pass(?:word|wd)?|secret|api[_\-]?key|auth[_\-]?token|"
        r"access[_\-]?token|client[_\-]?secret|private[_\-]?key)\b\s*[:=]\s*"
        r"['\"]?([A-Za-z0-9_\-/+\.]{12,})")),
)

#: Text that looks like a secret and is not. Placeholders in documentation are
#: the common case, and refusing a document for containing the word "REDACTED"
#: would make the gate an obstacle rather than a control.
_ALLOWED = re.compile(
    r"(?i)^(?:x{3,}|\*{3,}|\.{3,}|<[^>]+>|\$\{[^}]+\}|"
    r"your[_\-]?[a-z]+|my[_\-]?[a-z]+|example[a-z_\-]*|placeholder[a-z_\-]*|"
    r"redacted[a-z_\-]*|changeme|none|null|true|false|todo|tbd|"
    r"[a-z_]*here|\.\.\.)$"
)


@dataclass(frozen=True)
class Finding:
    label: str
    line: int
    excerpt: str          # never the secret itself — enough to locate it

    def __str__(self) -> str:
        return f"line {self.line}: {self.label} ({self.excerpt})"


def _is_placeholder(value: str) -> bool:
    return bool(_ALLOWED.match(value.strip().strip("'\"")))


def find(text: str) -> list[Finding]:
    """Every secret still present. An empty list means safe to store.

    Findings carry a line number and a masked excerpt, never the value: a
    refusal message ends up in a log, and a log is not where a leaked
    credential should be reproduced.
    """
    if not text:
        return []
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(2) if label == "named-secret" and match.lastindex else match.group(0)
            if label == "named-secret" and _is_placeholder(value):
                continue
            line = text.count("\n", 0, match.start()) + 1
            if (label, line) in seen:
                continue
            seen.add((label, line))
            findings.append(Finding(label, line, _mask(match.group(0))))
    return sorted(findings, key=lambda f: (f.line, f.label))


def _mask(raw: str) -> str:
    """Enough to find it in the source, not enough to use it."""
    flat = " ".join(raw.split())
    if len(flat) <= 12:
        return flat[:4] + "…"
    return f"{flat[:8]}…{len(flat)} chars"


def scrub(text: str) -> tuple[str, list[str]]:
    """Replace every secret with a labelled placeholder.

    For text on its way TO a hand — so a hand cannot copy forward a credential
    it was never meant to see. Not for text on its way to a knowledge base:
    that path refuses instead, because a silent scrub hides the near-miss.
    """
    if not text:
        return text, []
    labels: list[str] = []
    for label, pattern in PATTERNS:
        if label == "named-secret":
            def replace_named(m: re.Match[str], _l: str = label) -> str:
                if _is_placeholder(m.group(2)):
                    return m.group(0)
                labels.append(_l)
                return f"{m.group(1)}=[REDACTED-{_l}]"
            text = pattern.sub(replace_named, text)
        else:
            def replace(m: re.Match[str], _l: str = label) -> str:
                labels.append(_l)
                return f"[REDACTED-{_l}]"
            text = pattern.sub(replace, text)
    return text, sorted(set(labels))


class WouldLeak(Exception):
    """Raised by the gate. Carries the findings so the refusal is actionable."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        listed = "\n".join(f"    {f}" for f in findings)
        super().__init__(
            f"refusing to store this: {len(findings)} possible secret(s) found.\n"
            f"{listed}\n"
            "    A knowledge base is long-lived and searchable, so this is "
            "refused rather than\n    quietly scrubbed — the near-miss is worth "
            "knowing about."
        )


def gate(text: str) -> None:
    """The hard gate before anything is written to a knowledge base."""
    findings = find(text)
    if findings:
        raise WouldLeak(findings)
