"""Tests for the redaction gate.

Two corpora, and the second matters as much as the first. A gate that refuses
good writes teaches people to route around it, and a gate people route around
is not a gate.

Every value below is invented. They are the right *shape* and nothing more.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import redaction  # noqa: E402

# ── must be caught ───────────────────────────────────────────────────────
LEAKS = {
    "knowledge-base-pat": "token: kb_pat_AbCdEf0123456789XyZw",
    "openai-key": "OPENAI=sk-proj-AbCdEf0123456789AbCdEf0123",
    "anthropic-key": "key sk-ant-AbCdEf0123456789AbCdEf01234",
    "google-key": "AIzaSyAbCdEf0123456789AbCdEf0123456789",
    "gitlab-pat": "glpat-AbCdEf0123456789xy",
    "github-pat": "ghp_AbCdEf0123456789AbCdEf0123456789ab",
    "atlassian-token": "ATATT3xFfGF0AbCdEf0123456789xyz=",
    "slack-token": "xoxb-1234567890-AbCdEfGhIjKl",
    "aws-access-key": "AKIAIOSFODNN7EXAMPLE",
    "npm-token": "npm_" + "a" * 36,
    "telegram-bot-token": "8804660836:AAF-AbCdEf0123456789AbCdEf0123456",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijkl",
    "bearer-header": "Authorization: Bearer AbCdEf0123456789AbCdEf",
    "named-secret": 'password = "hunter2-not-a-real-one"',
}

PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
    "-----END OPENSSH PRIVATE KEY-----"
)

# ── must NOT be caught ───────────────────────────────────────────────────
# Documentation, placeholders and ordinary prose. Each of these appears in
# real design documents in this very repository.
SAFE = [
    "Set SKY_KB_PAT in your environment before running the doctor.",
    "The map holds the variable's NAME, never its value.",
    'password = "<your-password-here>"',
    "api_key: ${SKY_KB_PAT}",
    "auth_token = YOUR_TOKEN_HERE",
    "client_secret: changeme",
    "secret: xxxxxxxxxxxxxx",
    "password=[REDACTED-named-secret]",
    "A token identifies the whole person: every tenant, no scope, no expiry.",
    "Authorization: Bearer ${SKY_KB_PAT}",
    "See docs/gates.md for the probe contracts, including the ingest one.",
    "git config credential.helper is deliberately empty",
    "The commit trailer is SKY-Agent: arup-developer-1 run-20260914-001",
    "private_key: none",
]


class ItCatchesRealShapes(unittest.TestCase):
    def test_each_known_shape_is_found(self):
        for label, sample in LEAKS.items():
            with self.subTest(label=label):
                found = redaction.find(sample)
                self.assertTrue(found, f"{label} was not caught")
                self.assertIn(label, [f.label for f in found])

    def test_a_private_key_block_is_found(self):
        found = redaction.find(PRIVATE_KEY)
        self.assertIn("private-key", [f.label for f in found])

    def test_a_secret_buried_in_a_long_document_is_still_found(self):
        body = "\n".join(["ordinary prose about the design"] * 200)
        text = body + "\n" + LEAKS["openai-key"] + "\n" + body
        found = redaction.find(text)
        self.assertTrue(found)
        self.assertEqual(found[0].line, 201)


class ItLeavesOrdinaryTextAlone(unittest.TestCase):
    """The half that is usually forgotten.

    A gate with a high false-positive rate gets worked around, and then it is
    not protecting anything.
    """

    def test_nothing_in_the_safe_corpus_is_flagged(self):
        for sample in SAFE:
            with self.subTest(sample=sample[:48]):
                self.assertEqual(redaction.find(sample), [],
                                 f"false positive on: {sample}")

    def test_this_projects_own_documents_pass(self):
        """The strongest false-positive test available: real files.

        These documents discuss tokens, credentials and headers at length. If
        the gate cannot tolerate writing *about* secrets, it cannot be used on
        anything this team produces.
        """
        docs = Path(__file__).resolve().parents[2] / "docs"
        checked = 0
        for path in sorted(docs.glob("*.md")):
            with self.subTest(doc=path.name):
                findings = redaction.find(path.read_text())
                self.assertEqual(
                    findings, [],
                    f"{path.name} would be refused: {[str(f) for f in findings]}")
            checked += 1
        self.assertGreater(checked, 3, "expected several documents to check")


class TheGate(unittest.TestCase):
    def test_it_refuses_rather_than_scrubbing(self):
        with self.assertRaises(redaction.WouldLeak) as caught:
            redaction.gate(LEAKS["openai-key"])
        self.assertIn("refusing to store", str(caught.exception))
        self.assertIn("near-miss", str(caught.exception))

    def test_it_passes_clean_text(self):
        redaction.gate("A design note with nothing sensitive in it.")   # no raise

    def test_the_refusal_says_where_without_reproducing_the_value(self):
        secret = "sk-proj-AbCdEf0123456789AbCdEf0123"
        with self.assertRaises(redaction.WouldLeak) as caught:
            redaction.gate(f"line one\nOPENAI={secret}\nline three")
        message = str(caught.exception)
        self.assertIn("line 2", message)
        self.assertNotIn(secret, message,
                         "the refusal reproduced the secret into a log")


class Scrubbing(unittest.TestCase):
    """For text on its way TO a hand — a different job from the gate."""

    def test_it_replaces_and_reports_what_it_replaced(self):
        text, labels = redaction.scrub("key=" + LEAKS["openai-key"])
        self.assertNotIn("sk-proj-", text)
        self.assertIn("openai-key", labels)

    def test_scrubbed_text_then_passes_the_gate(self):
        text, _ = redaction.scrub(LEAKS["telegram-bot-token"])
        redaction.gate(text)      # must not raise

    def test_it_leaves_placeholders_intact(self):
        text, labels = redaction.scrub('password = "<your-password-here>"')
        self.assertIn("<your-password-here>", text)
        self.assertEqual(labels, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
