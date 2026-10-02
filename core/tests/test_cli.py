"""CLI behaviour that must hold without a network.

The theme is the same as everywhere else in core: an unconfigured or broken
machine is a normal state, and the command's job is to say what is wrong and
what to do — not to crash, and not to pretend.
"""
from __future__ import annotations

import io
import json
import subprocess
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.cli import main  # noqa: E402

#: The policy that ships. These tests run against the real file, so a change to
#: it that breaks a role shows up here rather than in a user's session.
SHIPPED_POLICY = str(Path(__file__).resolve().parents[2] / "plugin" / "policy.yaml")


def run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class WhenNothingIsConfigured(unittest.TestCase):
    def test_doctor_explains_instead_of_crashing(self):
        missing = Path(tempfile.mkdtemp()) / "nope.json"
        code, _, err = run("--kb-map", str(missing), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("sky setup init", err)

    def test_doctor_with_no_map_still_shows_every_row(self):
        """SH-023: the parts that need no account are probed and shown."""
        from sky import probes
        from sky.readiness import Brain, Part
        seen = {}

        def record(kb, hand="claude", policy=None, cwd=None, deep=False, no_kb=""):
            seen["kb"], seen["no_kb"] = kb, no_kb
            b = Brain()
            probes.probe_actions(b)
            return b

        saved, probes.run_all = probes.run_all, record
        try:
            missing = Path(tempfile.mkdtemp()) / "nope.json"
            code, out, err = run("--kb-map", str(missing), "doctor")
        finally:
            probes.run_all = saved
        self.assertEqual(code, 1)
        self.assertIn("sky setup init", err)
        self.assertIsNone(seen["kb"])
        self.assertIn("sky setup init", seen["no_kb"])
        self.assertIn("ready for:", out)

    def test_with_no_kb_the_kb_rows_are_missing_and_the_rest_are_probed(self):
        from sky import probes
        from sky.readiness import Part, State
        brain = probes.run_all(None, policy=None, no_kb="no KB map; run sky setup init")
        for part in (Part.KNOWLEDGE, Part.FOCUS, Part.REMEMBERING):
            self.assertIs(brain.state_of(part), State.MISSING)
        knowledge = next(o for o in brain.observations if o.part is Part.KNOWLEDGE)
        self.assertIn("sky setup init", knowledge.detail)
        probed = {o.part for o in brain.observations}
        for part in (Part.SAFETY, Part.QUALITY, Part.ACTIONS):
            self.assertIn(part, probed)

    def test_a_malformed_map_says_so_precisely(self):
        bad = Path(tempfile.mkdtemp()) / "kb-map.json"
        bad.write_text("{ not json")
        code, _, err = run("--kb-map", str(bad), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", err)


class WhenAKBExists(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.map = self.tmp / "kb-map.json"
        self.map.write_text(json.dumps({
            "team_kb": {"purpose": "the team's knowledge", "mcp_url": "https://kb.example/mcp/",
                        "tenant_code": "TEAM1234", "ontology": "sky_sdlc", "privacy": "work",
                        "write": True, "pat_env": "SKY_PAT_TEAM", "default": True},
            "notes_kb": {"purpose": "read-only reference", "mcp_url": "https://kb.example/mcp/",
                         "tenant_code": "NOTE5678", "ontology": "sky_sdlc", "privacy": "work",
                         "write": False, "pat_env": "SKY_PAT_TEAM"},
        }))

    def test_kb_list_marks_the_default_and_the_read_only_one(self):
        code, out, _ = run("--kb-map", str(self.map), "kb", "list")
        self.assertEqual(code, 0)
        self.assertIn("team_kb", out)
        self.assertIn("default", out)
        self.assertIn("read-only", out)

    def test_kb_which_says_why(self):
        code, out, _ = run("--kb-map", str(self.map), "kb", "which")
        self.assertEqual(code, 0)
        self.assertIn("team_kb", out)
        self.assertIn("default", out)

    def test_an_unknown_kb_lists_the_real_ones(self):
        code, _, err = run("--kb-map", str(self.map), "--kb", "typo", "kb", "which")
        self.assertEqual(code, 1)
        self.assertIn("team_kb", err)


class BuildRefusesBeforeItStarts(unittest.TestCase):
    """`sky build` does real work now; these are the ways it declines.

    Every one of them must say which part is the problem, because "not ready"
    on its own leaves someone with nothing to do about it.
    """

    def test_it_refuses_when_nothing_is_configured(self):
        missing = Path(tempfile.mkdtemp()) / "nope.json"
        code, _, err = run("--kb-map", str(missing), "build", "--task", "ENG-1")
        self.assertEqual(code, 1)
        self.assertIn("sky setup init", err)

    def test_a_build_is_refused_and_the_refusal_names_the_blocking_parts(self):
        """The rule, at the point it is applied.

        This asserts the *shape* of a refusal, not which part blocks. An
        earlier version hard-coded "habits" and "safety"; both now pass — the
        plugin loads and the policy is enforced — so it was asserting the
        absence of features rather than the presence of a rule, and it failed
        the moment those probes started working.
        """
        tmp = Path(tempfile.mkdtemp())
        kbmap = tmp / "kb-map.json"
        kbmap.write_text(json.dumps({"team_kb": {
            "purpose": "x", "mcp_url": "http://127.0.0.1:9/mcp/",
            "tenant_code": "TEAM1234", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_TEST_PAT", "default": True}}))
        import os
        os.environ["SKY_TEST_PAT"] = "t"
        os.environ["SKY_STATE_DIR"] = str(tmp / "state")
        os.environ["SKY_POLICY"] = SHIPPED_POLICY
        code, _, err = run("--kb-map", str(kbmap), "build", "--task", "ENG-1", "--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("not ready for build", err)
        self.assertIn("it IS ready for", err, "the refusal must say what it CAN do")
        self.assertIn("run record", err)
        # At least one part is named with a state and a reason — never just
        # "not ready", which is a refusal nobody can act on.
        named = [line for line in err.splitlines()
                 if any(f" {state} " in line
                        for state in ("missing", "down", "degraded"))]
        self.assertTrue(named, f"no part was named with a state:\n{err}")
        self.assertTrue(any(len(line.split()) > 3 for line in named),
                        "a part was named with no reason given")

    def test_a_build_with_no_policy_at_all_is_refused_before_anything_else(self):
        """No policy means no tool allowlist, which is tier A itself.

        This refusal comes earlier and for a different reason than the
        readiness one: there is nothing to hold a role to, so a role name would
        be a label rather than a boundary.
        """
        tmp = Path(tempfile.mkdtemp())
        kbmap = tmp / "kb-map.json"
        kbmap.write_text(json.dumps({"team_kb": {
            "purpose": "x", "mcp_url": "http://127.0.0.1:9/mcp/",
            "tenant_code": "TEAM1234", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_TEST_PAT", "default": True}}))
        import os
        os.environ["SKY_TEST_PAT"] = "t"
        os.environ["SKY_STATE_DIR"] = str(tmp / "state")
        os.environ["SKY_POLICY"] = str(tmp / "there-is-no-policy.yaml")
        try:
            code, _, err = run("--kb-map", str(kbmap), "build", "--task", "ENG-1",
                               "--dry-run")
        finally:
            os.environ["SKY_POLICY"] = SHIPPED_POLICY
        self.assertEqual(code, 1)
        self.assertIn("no policy", err)
        self.assertIn("boundary", err)


class TheWholePathWhenTheBrainIsReady(unittest.TestCase):
    """End to end: resolve, check, build the environment, prove it, run.

    The probes are replaced with a healthy brain and the hand with `echo`,
    because what is under test is the launcher's sequence — not whether a
    coding agent is installed on the machine running the suite.
    """

    def setUp(self) -> None:
        import os
        from sky import cli, launcher, probes
        from sky.readiness import Brain, Part, State

        self.tmp = Path(tempfile.mkdtemp())
        # Run from a repository with no remote. From the enclosing checkout, the
        # launcher's dry-run push would try that checkout's real remote, and a
        # local-path remote (a fresh clone of a clone) lets it succeed — so the
        # result would depend on the machine, not on the code.
        self._cwd = os.getcwd()
        work = self.tmp / "work"
        work.mkdir()
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        os.chdir(work)
        self.map = self.tmp / "kb-map.json"
        self.map.write_text(json.dumps({"team_kb": {
            "purpose": "x", "mcp_url": "https://kb.example/mcp/",
            "tenant_code": "TEAM1234", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_TEST_PAT", "default": True}}))
        os.environ["SKY_TEST_PAT"] = "t"
        os.environ["SKY_STATE_DIR"] = str(self.tmp / "state")
        os.environ["SKY_POLICY"] = SHIPPED_POLICY

        def healthy(kb, hand="claude", policy=None, cwd=None):
            b = Brain()
            for part in Part:
                b.add(part, State.OK, "probed")
            return b

        self._probes, probes.run_all = probes.run_all, healthy
        self._cmd = launcher.hand_command
        launcher.hand_command = lambda h, r, m, p, pol: ["sh", "-c",
                                                         "echo the hand ran"]

    def tearDown(self) -> None:
        import os
        from sky import launcher, probes
        os.chdir(self._cwd)
        probes.run_all = self._probes
        launcher.hand_command = self._cmd

    def test_a_ready_brain_runs_the_hand_and_records_it(self):
        code, out, err = run("--kb-map", str(self.map), "build",
                             "--role", "developer", "--task", "ENG-1")
        self.assertEqual(code, 0, err)
        self.assertIn("git block proven", out)
        self.assertIn("the hand ran", out)
        self.assertIn("finished", out)

        runs = list((self.tmp / "state" / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        events = (runs[0] / "events.jsonl").read_text()
        for expected in ("run.start", "git.block.checked", "hand.start",
                         "hand.end", "run.finish"):
            self.assertIn(expected, events, f"{expected} was not recorded")
        self.assertIn("the hand ran", (runs[0] / "hand.log").read_text())

    def test_a_hand_that_reports_usage_gets_a_bill_recorded_and_its_text_shown(self):
        """The bill, end to end: from the hand's own report into events.jsonl.

        The fake hand speaks stream-json — a system line, a message line whose
        text claims a wild cost, and the result object with the real numbers.
        The recorded numbers must be the result's, and what is printed must be
        the result text, not the JSON.
        """
        from sky import launcher
        result = {"type": "result", "subtype": "success", "num_turns": 3,
                  "duration_ms": 1200, "total_cost_usd": 0.0123,
                  "usage": {"input_tokens": 1000, "output_tokens": 500,
                            "cache_read_input_tokens": 9000,
                            "cache_creation_input_tokens": 0},
                  "result": "the hand did the thing"}
        lines = [json.dumps({"type": "system", "subtype": "init"}),
                 json.dumps({"type": "assistant",
                             "message": {"content": [{"type": "text",
                                                      "text": "this cost $99"}]}}),
                 json.dumps(result)]
        script = "; ".join(f"echo '{l}'" for l in lines)
        launcher.hand_command = lambda h, r, m, p, pol: ["sh", "-c", script]

        code, out, err = run("--kb-map", str(self.map), "build",
                             "--role", "developer", "--task", "ENG-2")
        self.assertEqual(code, 0, err)
        self.assertIn("the hand did the thing", out)
        self.assertNotIn('"type": "result"', out, "raw JSON was shown instead of the text")
        self.assertIn("$0.0123", out)

        runs = list((self.tmp / "state" / "runs").iterdir())
        events = [json.loads(l) for l in
                  (runs[0] / "events.jsonl").read_text().splitlines()]
        bill = [e for e in events if e["kind"] == "run.usage"]
        self.assertEqual(len(bill), 1)
        self.assertTrue(bill[0]["available"])
        self.assertEqual(bill[0]["cost_usd"], 0.0123)
        self.assertEqual(bill[0]["tokens"], 1500, "judged on input+output, not cache")
        self.assertEqual(bill[0]["cache_read_tokens"], 9000)
        self.assertEqual(bill[0]["turns"], 3)
        self.assertNotEqual(bill[0]["cost_usd"], 99, "the model's claim was believed")

    def test_with_json_a_program_gets_one_structured_line_last(self):
        """The launch contract for Ethan: never parse prose, never guess from an
        exit code."""
        from sky import launcher
        result = {"type": "result", "subtype": "success", "num_turns": 2,
                  "duration_ms": 900, "total_cost_usd": 0.0123,
                  "usage": {"input_tokens": 1000, "output_tokens": 500},
                  "result": "structured done"}
        launcher.hand_command = lambda h, r, m, p, pol: [
            "sh", "-c", f"echo '{json.dumps(result)}'"]
        code, out, err = run("--kb-map", str(self.map), "build",
                             "--role", "developer", "--task", "ENG-4", "--json")
        self.assertEqual(code, 0, err)
        last = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(last["sky"], "build")
        self.assertEqual(last["outcome"], "finished")
        self.assertTrue(last["ok"])
        self.assertTrue(last["run_id"].startswith("run-"))
        self.assertTrue(Path(last["directory"]).is_dir())
        self.assertEqual(last["usage"]["cost_usd"], 0.0123)
        self.assertEqual(last["usage"]["tokens"], 1500)
        self.assertEqual(last["result_text"], "structured done")

    def test_a_hand_that_reports_nothing_gets_an_honest_blank(self):
        """The plain `echo` hand from the other test: no JSON, so no usage —
        recorded as unavailable WITH the reason, never estimated."""
        code, out, err = run("--kb-map", str(self.map), "build",
                             "--role", "developer", "--task", "ENG-3")
        self.assertEqual(code, 0, err)
        self.assertIn("usage not available", out)
        runs = list((self.tmp / "state" / "runs").iterdir())
        events = [json.loads(l) for l in
                  (runs[0] / "events.jsonl").read_text().splitlines()]
        bill = [e for e in events if e["kind"] == "run.usage"][0]
        self.assertFalse(bill["available"])
        self.assertIn("not JSON", bill["reason"])

    def test_the_kb_token_is_in_exactly_one_run_file_and_that_file_is_private(self):
        """What is actually true about the token, asserted honestly.

        An earlier version of this test was named "the token never reaches the
        run record" and asserted that the string `SKY_TEST_PAT=t` appeared in
        no file — a string that could never appear anywhere, so the test proved
        nothing, and the claim it lent its name to was false. A review caught it.

        The real rule, from the harness design §7.1: until the boundary exists
        (H10), the hand holds the KB token by construction, and the run's
        `mcp.json` carries it so the hand can reach the KB. So the token is
        allowed in **exactly one** file, that file must be private (0600), and
        it must appear in **no other** artefact — not the event log, not the
        hand's output, nothing a person reads later.
        """
        import stat
        token = "test-token-8f3a1c-distinctive"
        os.environ["SKY_TEST_PAT"] = token
        try:
            run("--kb-map", str(self.map), "build", "--role", "developer", "--task", "V")
        finally:
            os.environ["SKY_TEST_PAT"] = "t"
        carrying = []
        for path in (self.tmp / "state").rglob("*"):
            if path.is_file() and token in path.read_text(errors="replace"):
                carrying.append(path)
        self.assertEqual([p.name for p in carrying], ["mcp.json"],
                         f"the token is in {[str(p) for p in carrying]}; only mcp.json may hold it")
        mode = stat.S_IMODE(carrying[0].stat().st_mode)
        self.assertEqual(mode, 0o600, f"mcp.json is {oct(mode)}, not private")
