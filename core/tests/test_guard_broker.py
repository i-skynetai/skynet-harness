"""Tests for H5 — the guard, the ledger, and the broker's render half.

Two things under test that are easy to write and easy to get wrong:

* the guard must judge **each** command in a shell line, because `npm test &&
  git push` is one string and two intentions;
* the broker must **refuse** rather than escape a field carrying a shell
  metacharacter, and must refuse a hand that tries to approve its own push.

The hook output shapes are the host's own, read out of the Claude Code
executable rather than from documentation: `permissionDecision` is one of
allow · deny · ask · defer, inside `hookSpecificOutput`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import broker, guard, schemas  # noqa: E402
from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class InAManagedRun:
    """The guard only acts inside a run the launcher started.

    Every case below that expects a denial has to be inside one — which is the
    point of the rule, not an inconvenience to work around: in an ordinary
    session it is the person's own repository and the host's own permission
    prompt, and denying `git push` there was simply wrong.
    """

    def __enter__(self):
        self.saved = os.environ.get("SKY_LAUNCHED")
        os.environ["SKY_LAUNCHED"] = "1"
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop("SKY_LAUNCHED", None)
        else:
            os.environ["SKY_LAUNCHED"] = self.saved
        return False


class TheGuardOnlyActsInsideARun(unittest.TestCase):
    """The rule the review found missing, now pinned."""

    def test_an_ordinary_session_is_left_alone(self):
        os.environ.pop("SKY_LAUNCHED", None)
        v = guard.decide(bash("git push origin dev"), POLICY)
        self.assertEqual(v.decision, "allow")
        self.assertEqual(v.reason, "", "no noise on every command either")

    def test_and_the_same_command_is_denied_inside_one(self):
        with InAManagedRun():
            self.assertEqual(guard.decide(bash("git push origin dev"),
                                          POLICY).decision, "deny")

    def test_the_shipped_shim_exits_early_outside_a_run(self):
        shim = REPO / "plugin" / "bin" / "sky-guard"
        self.assertIn('SKY_LAUNCHED" != "1"', shim.read_text())


class TheGuardJudgesEachCommand(unittest.TestCase):
    def setUp(self):
        self.run = InAManagedRun().__enter__()

    def tearDown(self):
        self.run.__exit__(None, None, None)

    def test_a_denied_command_is_denied(self):
        v = guard.decide(bash("git push origin dev"), POLICY)
        self.assertEqual(v.decision, "deny")
        self.assertEqual(v.action, "push")
        self.assertIn("sky ship", v.reason)

    def test_an_ordinary_command_is_allowed(self):
        self.assertEqual(guard.decide(bash("npm test"), POLICY).decision, "allow")

    def test_a_push_hidden_behind_a_test_run_is_still_caught(self):
        """One line, two intentions. Judging the whole string sees a test."""
        v = guard.decide(bash("npm test && git push origin dev"), POLICY)
        self.assertEqual(v.decision, "deny")
        self.assertEqual(v.action, "push")

    def test_every_separator_splits(self):
        for line in ("npm test; git push origin dev",
                     "npm test || git push origin dev",
                     "echo hi | git push origin dev"):
            with self.subTest(line=line):
                self.assertEqual(guard.decide(bash(line), POLICY).decision, "deny")

    def test_the_longest_match_gives_the_reason_not_the_first(self):
        """A force push recorded as an ordinary push is what an audit reads."""
        v = guard.decide(bash("git push --force origin main"), POLICY)
        self.assertEqual(v.decision, "deny")
        self.assertIn("force", v.reason.lower())

    def test_a_tool_that_runs_no_command_is_not_this_guards_business(self):
        v = guard.decide({"tool_name": "Read", "tool_input": {"file_path": "x"}},
                         POLICY)
        self.assertEqual(v.decision, "allow")

    def test_malformed_input_does_not_crash_it(self):
        for payload in ({}, {"tool_name": "Bash"},
                        {"tool_name": "Bash", "tool_input": "not a dict"}):
            with self.subTest(payload=payload):
                self.assertEqual(guard.decide(payload, POLICY).decision, "allow")

    def test_with_no_policy_it_stands_aside_and_says_so(self):
        """Fails open — and never silently, which is the whole bargain."""
        v = guard.decide(bash("git push origin dev"), None)
        self.assertEqual(v.decision, "allow")
        self.assertIn("no policy", v.reason)


class TheHookOutputShape(unittest.TestCase):
    def test_it_is_exactly_what_the_host_reads(self):
        body = guard.Verdict("deny", "because").as_hook_output()
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(body["hookSpecificOutput"]["permissionDecisionReason"],
                         "because")

    def test_only_the_hosts_own_four_words_are_used(self):
        self.assertEqual(guard.DECISIONS, ("allow", "deny", "ask", "defer"))

    def test_the_command_line_end_to_end(self):
        """The real entry point, driven as the host drives it."""
        import subprocess
        out = subprocess.run(
            [sys.executable, "-m", "sky", "guard"], cwd=str(REPO / "core"),
            input=json.dumps(bash("git push origin dev")),
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "SKY_LAUNCHED": "1",
                 "SKY_POLICY": str(REPO / "plugin" / "policy.yaml")})
        self.assertEqual(out.returncode, 0, out.stderr)
        body = json.loads(out.stdout)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")


class TheLedger(unittest.TestCase):
    def test_outside_a_run_it_writes_nothing(self):
        """An interactive session is not something to litter a home with."""
        saved = os.environ.pop("SKY_RUN_DIR", None)
        try:
            self.assertIsNone(guard.record(bash("npm test")))
        finally:
            if saved is not None:
                os.environ["SKY_RUN_DIR"] = saved

    def test_inside_a_run_it_appends_one_line_per_call(self):
        root = Path(tempfile.mkdtemp())
        os.environ["SKY_RUN_DIR"] = str(root)
        try:
            guard.record(bash("npm test"), guard.Verdict("allow"))
            guard.record(bash("git push"), guard.Verdict("deny", "no", "push"))
            lines = (root / "tools.jsonl").read_text().strip().splitlines()
        finally:
            os.environ.pop("SKY_RUN_DIR", None)
        self.assertEqual(len(lines), 2)
        second = json.loads(lines[1])
        self.assertEqual(second["decision"], "deny")
        self.assertEqual(second["action"], "push")

    def test_it_never_raises_even_when_it_cannot_write(self):
        """A ledger that can break a run is a ledger someone turns off."""
        os.environ["SKY_RUN_DIR"] = "/proc/nonexistent/nowhere"
        try:
            self.assertIsNone(guard.record(bash("npm test")))
        finally:
            os.environ.pop("SKY_RUN_DIR", None)


class TheBrokerRefusesRatherThanEscapes(unittest.TestCase):
    HAND = {"kind": "push", "summary": "push the fix", "branch": "fix/abc",
            "remote": "origin"}

    def sealed(self, **over):
        return broker.accept({**self.HAND, **over}, run_id="r1", agent_id="a1")

    def test_a_clean_push_renders_one_command(self):
        rendered = broker.render(self.sealed())
        self.assertEqual(rendered.command, "git push origin fix/abc")
        self.assertNotIn("&&", rendered.command)

    def test_a_shell_metacharacter_is_refused_not_quoted(self):
        for value in ("fix/a; rm -rf /", "fix/$(whoami)", "fix/a`id`",
                      "fix/a|tee", "fix/a\nrm"):
            with self.subTest(value=value):
                with self.assertRaises(broker.Refused) as caught:
                    broker.render(self.sealed(branch=value))
                self.assertIn("branch", str(caught.exception))

    def test_a_remote_is_checked_too(self):
        with self.assertRaises(broker.Refused):
            broker.render(self.sealed(remote="origin;id"))

    def test_pushing_the_shared_branch_directly_is_refused(self):
        for branch in ("main", "master"):
            with self.subTest(branch=branch):
                with self.assertRaises(broker.Refused) as caught:
                    broker.render(self.sealed(branch=branch))
                self.assertIn("pull request", str(caught.exception))

    def test_an_empty_field_is_refused_rather_than_guessed(self):
        with self.assertRaises(broker.Refused):
            broker.render(self.sealed(branch=""))


class AHandMayNotApproveItsOwnWork(unittest.TestCase):
    """The reason the broker exists at all."""

    HAND = {"kind": "push", "summary": "s", "branch": "b", "remote": "origin"}

    def test_a_hand_that_writes_approved_by_is_refused(self):
        with self.assertRaises(broker.Refused) as caught:
            broker.accept({**self.HAND, "approved_by": "me"},
                          run_id="r", agent_id="a")
        self.assertIn("only the runtime may assert this", str(caught.exception))

    def test_and_approved_at_and_channel_and_executed(self):
        for field, value in (("approved_at", "2026-09-15T00:00:00Z"),
                             ("channel", "telegram"), ("executed", True),
                             ("run_id", "forged"), ("agent_id", "forged")):
            with self.subTest(field=field):
                with self.assertRaises(broker.Refused):
                    broker.accept({**self.HAND, field: value},
                                  run_id="r", agent_id="a")

    def test_the_runtime_supplies_them_instead(self):
        sealed = broker.accept(self.HAND, run_id="r1", agent_id="a1")
        self.assertEqual(sealed["run_id"], "r1")
        self.assertEqual(sealed["agent_id"], "a1")

    def test_approval_fields_are_runtime_owned_on_the_contract(self):
        owned = schemas.INTENT.runtime_fields()
        for field in ("approved_by", "approved_at", "channel", "executed"):
            self.assertIn(field, owned)


class TheOtherKinds(unittest.TestCase):
    def seal(self, body):
        return broker.accept(body, run_id="r", agent_id="a")

    def test_a_pull_request_pipes_its_body_rather_than_inlining_it(self):
        r = broker.render(self.seal({
            "kind": "pr.open", "summary": "open it", "branch": "fix/a",
            "base": "dev", "title": "Fix the thing", "body": "why\nand how"}))
        self.assertIn("--body-file -", r.command)
        self.assertEqual(r.body, "why\nand how")

    def test_a_comment_renders_no_command_at_all(self):
        r = broker.render(self.seal({
            "kind": "ticket.comment", "summary": "say it",
            "issue_key": "ABC-12", "body": "done on branch fix/a"}))
        self.assertEqual(r.command, "")
        self.assertIn("yourself", r.note)

    def test_a_malformed_ticket_id_is_refused(self):
        with self.assertRaises(broker.Refused):
            broker.render(self.seal({
                "kind": "ticket.comment", "summary": "s",
                "issue_key": "not a ticket", "body": "x"}))

    def test_an_unknown_kind_is_refused_by_the_contract(self):
        with self.assertRaises(broker.Refused):
            self.seal({"kind": "deploy", "summary": "s"})


class ReadingWhatAHandLeftBehind(unittest.TestCase):
    def test_an_unreadable_file_is_reported_not_skipped(self):
        """A dropped intent is an outward action somebody thinks happened."""
        root = Path(tempfile.mkdtemp())
        (root / "a.json").write_text('{"kind": "push", "summary": "s"}')
        (root / "b.json").write_text("{ not json")
        found = broker.read_pending(root)
        self.assertEqual(len(found), 2)
        self.assertIn("unreadable", [f["kind"] for f in found])

    def test_one_bad_intent_does_not_hide_the_good_ones(self):
        good = broker.accept({"kind": "push", "summary": "s", "branch": "fix/a"},
                             run_id="r", agent_id="a")
        bad = dict(good, branch="fix/a;id")
        results = broker.render_all([good, bad])
        self.assertIsInstance(results[0][1], broker.Rendered)
        self.assertIsInstance(results[1][1], broker.Refused)

    def test_a_missing_directory_is_empty_not_an_error(self):
        self.assertEqual(broker.read_pending(Path("/nonexistent/x")), [])


class ItExecutesNothing(unittest.TestCase):
    def test_the_module_never_runs_a_command(self):
        """H5 renders. Execution is H8, behind gate G24."""
        source = (REPO / "core" / "sky" / "broker.py").read_text()
        for forbidden in ("subprocess", "os.system", "popen", "os.exec"):
            self.assertNotIn(forbidden, source.lower(),
                             f"broker.py mentions {forbidden}; it must not execute")


if __name__ == "__main__":
    unittest.main(verbosity=2)
