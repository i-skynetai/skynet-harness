"""G23b — break the thing each probe watches, and check the table turns red.

**Why this gate exists.** A probe that cannot fail is a green light with extra
steps. Every row in the readiness table is a claim that something was observed;
until each row has been made to go red on purpose, the table is decoration.

**And the second half, which is the one usually skipped: *only* that row.** A
probe that turns the whole table red when one thing breaks is no more useful
than one that never turns red at all — the person reading it still has to go
and find out what is actually wrong. So each case below asserts an exact set of
changed rows, and where a break legitimately cascades, the cascade is named and
justified rather than tolerated.

**What this does and does not prove.** It proves the probe *logic* detects its
break: the knowledge-base calls run against a stub, so no live tenant is
needed and no credential is used. It does not prove any particular deployment
is healthy — that is `sky doctor`, run against the real thing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import probes  # noqa: E402
from sky.kbmap import KB  # noqa: E402
from sky.policy import Policy  # noqa: E402
from sky.readiness import Brain, Part, State  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")

A_KB = KB(name="stub", purpose="", url="https://stub.invalid/mcp/",
          tenant="ABCD2345", ontology="kb_sdlc", privacy="work",
          write=True, pat_env="SKY_TEST_PAT")

#: A search result with hits in it, in the shape the live server returns:
#: every hit tagged with the tenant it came from. Only the `project` layer is
#: tenant-isolated, so a search against an EMPTY tenant still returns other
#: tenants' shared-layer documents — which is what FOREIGN_HITS reproduces.
HITS = json.dumps({"hits": [
    {"text": "…", "metadata": {"doc_id": "d1", "tenant_code": "ABCD2345"}},
    {"text": "…", "metadata": {"doc_id": "d2", "tenant_code": "ABCD2345"}},
]})
FOREIGN_HITS = json.dumps({"hits": [
    {"text": "…", "metadata": {"doc_id": "x1", "tenant_code": "OTHER001"}},
    {"text": "…", "metadata": {"doc_id": "x2", "tenant_code": "OTHER002"}},
]})


class World:
    """One controlled world. Everything the probes reach is replaced.

    Replacing rather than mocking a library: the seams are this module's own
    two functions and `subprocess.run`, and a test that patched deeper would be
    testing the patch.
    """

    def __init__(self, **broken):
        self.broken = broken
        self.saved = {}

    def _rpc(self, url, token, method, params):
        if self.broken.get("kb_down"):
            raise ConnectionError("connection refused")
        if self.broken.get("kb_publishes_nothing"):
            return {"tools": []}
        return {"tools": [{"name": f"kb_{n}"} for n in range(12)]}

    def _call_tool(self, url, token, name, args):
        if self.broken.get("search_returns_nothing"):
            return json.dumps({"hits": []})
        if self.broken.get("search_returns_only_other_tenants"):
            return FOREIGN_HITS
        return HITS

    def _run(self, argv, **kw):
        command = " ".join(str(a) for a in argv)
        out, code = "", 0
        if "--version" in command:
            out = "2.1.152 (Claude Code)"
            if self.broken.get("hand_broken"):
                code = 1
                out = ""
        elif "--help" in command:
            out = "usage: claude --model <model> ..."
        elif "plugin list" in command:
            out = ("Installed plugins:\n\n  sky@sky\n    Version: 9.9.9\n"
                   "    Status: enabled\n")
            if self.broken.get("plugin_absent"):
                out = "Installed plugins:\n\n  (none)\n"
        elif command.endswith("guard"):
            decision = "allow" if self.broken.get("guard_stood_aside") else "deny"
            out = json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": decision}})
        return type("R", (), {"stdout": out, "stderr": "", "returncode": code})()

    def __enter__(self):
        import os
        import shutil
        self.saved = {"rpc": probes._rpc, "call": probes._call_tool,
                      "run": probes.subprocess.run, "which": probes.shutil.which,
                      "cmd": probes._runtime_command,
                      "pat": os.environ.get("SKY_TEST_PAT")}
        # `_runtime_command` looks past PATH — at ~/.local/bin and the plugin —
        # which is the point of finding 3. The stub has to hide all of it.
        probes._runtime_command = (
            lambda: None if self.broken.get("guard_missing") else "/usr/bin/sky")
        probes._rpc = self._rpc
        probes._call_tool = self._call_tool
        probes.subprocess.run = self._run
        probes.shutil.which = lambda name: (
            None if self.broken.get("hand_missing") and name == "claude"
            else None if self.broken.get("guard_missing") and name == "sky"
            else f"/usr/bin/{name}")
        os.environ["SKY_TEST_PAT"] = ("" if self.broken.get("token_revoked")
                                      else "a-token")
        return self

    def __exit__(self, *exc):
        import os
        probes._rpc = self.saved["rpc"]
        probes._call_tool = self.saved["call"]
        probes.subprocess.run = self.saved["run"]
        probes.shutil.which = self.saved["which"]
        probes._runtime_command = self.saved["cmd"]
        if self.saved["pat"] is None:
            os.environ.pop("SKY_TEST_PAT", None)
        else:
            os.environ["SKY_TEST_PAT"] = self.saved["pat"]
        return False


def a_repo_with_tests() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("")
    return root


def table(policy=POLICY, cwd=None, **broken) -> dict:
    """Every row, as `{Part: State}`. One dictionary to compare against."""
    with World(**broken):
        brain = probes.run_all(A_KB, hand="claude", policy=policy,
                               cwd=cwd or a_repo_with_tests())
    return {part: brain.state_of(part) for part in Part}


HEALTHY = None            # filled in by setUpModule; the baseline to diff against


def setUpModule():
    global HEALTHY
    HEALTHY = table()


class TheBaselineIsGreenEnoughToDiffAgainst(unittest.TestCase):
    def test_the_rows_a_break_can_move_start_healthy(self):
        for part in (Part.KNOWLEDGE, Part.FOCUS, Part.SHORT_TERM,
                     Part.SAFETY, Part.QUALITY, Part.HABITS):
            with self.subTest(part=part):
                self.assertIn(HEALTHY[part], (State.OK, State.DEGRADED),
                              f"{part.value} is {HEALTHY[part].value} before "
                              f"anything is broken, so a break cannot be seen")

    def test_a_row_nothing_here_can_reach_is_reported_as_unbuilt(self):
        """Inputs has no probe yet, and the table says so rather than passing."""
        self.assertEqual(HEALTHY[Part.INPUTS], State.MISSING)


class BreakOneThing(unittest.TestCase):
    """Each case: break it, and name every row that is allowed to change."""

    def changed(self, **broken) -> dict:
        now = table(**broken)
        return {p: (HEALTHY[p], now[p]) for p in Part if now[p] is not HEALTHY[p]}

    def assert_only(self, changed: dict, *parts: Part):
        self.assertEqual(set(changed), set(parts),
                         "changed rows: " + ", ".join(
                             f"{p.value} {a.value}->{b.value}"
                             for p, (a, b) in changed.items()))

    # ── the knowledge base ───────────────────────────────────────────────
    def test_revoking_the_token_turns_knowledge_red(self):
        changed = self.changed(token_revoked=True)
        self.assertEqual(changed[Part.KNOWLEDGE][1], State.MISSING)
        # Focus, Remembering and Short-term all read the same KB, so they
        # follow. That is a cascade by design: each says "not probed, the KB
        # did not answer" rather than inventing an independent verdict.
        self.assertIn(Part.FOCUS, changed)
        self.assertNotIn(Part.QUALITY, changed)
        self.assertNotIn(Part.SAFETY, changed)
        self.assertNotIn(Part.HABITS, changed)

    def test_the_endpoint_refusing_connections_turns_knowledge_red(self):
        changed = self.changed(kb_down=True)
        self.assertEqual(changed[Part.KNOWLEDGE][1], State.DOWN)
        self.assertNotIn(Part.QUALITY, changed)
        self.assertNotIn(Part.SAFETY, changed)

    def test_an_endpoint_that_answers_but_publishes_no_tools_is_down(self):
        """The failure a ping cannot see: it answered, and it is useless."""
        changed = self.changed(kb_publishes_nothing=True)
        self.assertEqual(changed[Part.KNOWLEDGE][1], State.DOWN)

    def test_search_returning_nothing_turns_focus_red_and_leaves_knowledge_alone(self):
        """The one that matters: the KB is up, and retrieval cannot answer."""
        changed = self.changed(search_returns_nothing=True)
        self.assert_only(changed, Part.FOCUS)
        self.assertEqual(changed[Part.FOCUS][1], State.DOWN)

    def test_hits_from_other_tenants_only_degrade_focus_and_say_whose_they_are(self):
        """Measured 2026-09-17 on a real tenant with nothing of its own: five
        hits, every one from another tenant's shared layer, and Focus said OK.
        Retrieval works, so this is degraded rather than down — but the row
        has to say that this knowledge base answered with nobody's documents
        but other people's."""
        changed = self.changed(search_returns_only_other_tenants=True)
        self.assert_only(changed, Part.FOCUS)
        self.assertEqual(changed[Part.FOCUS][1], State.DEGRADED)
        with World(search_returns_only_other_tenants=True):
            brain = Brain()
            probes.probe_knowledge(brain, A_KB)
            probes.probe_focus(brain, A_KB)
        detail = brain.observations[-1].detail
        self.assertIn("NONE from tenant ABCD2345", detail)
        self.assertIn("other tenants", detail)

    def test_healthy_focus_says_how_many_hits_were_this_tenants(self):
        with World():
            brain = Brain()
            probes.probe_knowledge(brain, A_KB)
            probes.probe_focus(brain, A_KB)
        self.assertEqual(brain.observations[-1].state, State.OK)
        self.assertIn("2 from this tenant", brain.observations[-1].detail)

    # ── the hand ─────────────────────────────────────────────────────────
    def test_removing_the_hand_turns_exactly_three_rows_red(self):
        """Predicted two; it is three, and the third is right.

        Short-term memory and Thinking are the hand itself. **Habits follows
        too** — it asks the *host* which plugins are loaded, and with no host
        there is nobody to ask. That cascade is correct and worth having a test
        say out loud: an earlier version of this file predicted Safety instead,
        and the measurement corrected it rather than the other way round.
        """
        changed = self.changed(hand_missing=True)
        self.assert_only(changed, Part.SHORT_TERM, Part.THINKING, Part.HABITS)
        self.assertEqual(changed[Part.SHORT_TERM][1], State.MISSING)
        self.assertNotIn(Part.SAFETY, changed, "the policy does not need a hand")
        self.assertNotIn(Part.QUALITY, changed, "the tests do not need a hand")

    def test_a_hand_that_cannot_answer_its_own_version_is_down(self):
        changed = self.changed(hand_broken=True)
        self.assertEqual(changed[Part.SHORT_TERM][1], State.DOWN)
        self.assertNotIn(Part.QUALITY, changed)

    # ── safety ───────────────────────────────────────────────────────────
    def test_removing_the_policy_turns_safety_red_only(self):
        now = table(policy=None)
        changed = {p: (HEALTHY[p], now[p]) for p in Part if now[p] is not HEALTHY[p]}
        self.assert_only(changed, Part.SAFETY)
        self.assertEqual(changed[Part.SAFETY][1], State.MISSING)

    def test_a_guard_that_allows_a_push_is_down_not_degraded(self):
        """Installed and not enforcing is a different emergency from absent."""
        changed = self.changed(guard_stood_aside=True)
        self.assert_only(changed, Part.SAFETY)
        self.assertEqual(changed[Part.SAFETY][1], State.DOWN)

    def test_a_guard_that_is_not_installed_is_degraded_not_down(self):
        changed = self.changed(guard_missing=True)
        self.assert_only(changed, Part.SAFETY)
        self.assertEqual(changed[Part.SAFETY][1], State.DEGRADED)

    # ── quality control ──────────────────────────────────────────────────
    def test_a_repository_with_no_test_runner_turns_quality_red_only(self):
        empty = Path(tempfile.mkdtemp())
        (empty / "README.md").write_text("#")
        now = table(cwd=empty)
        changed = {p: (HEALTHY[p], now[p]) for p in Part if now[p] is not HEALTHY[p]}
        self.assert_only(changed, Part.QUALITY)
        self.assertEqual(changed[Part.QUALITY][1], State.MISSING)

    # ── habits ───────────────────────────────────────────────────────────
    def test_the_plugin_not_being_loaded_turns_habits_red_only(self):
        changed = self.changed(plugin_absent=True)
        self.assert_only(changed, Part.HABITS)


class ARedRowStopsTheRightThing(unittest.TestCase):
    """A probe that detects a break and permits the build anyway is decoration."""

    def test_no_quality_control_blocks_a_build_but_not_a_question(self):
        from sky.readiness import Kind
        empty = Path(tempfile.mkdtemp())
        (empty / "README.md").write_text("#")
        with World():
            brain = probes.run_all(A_KB, hand="claude", policy=POLICY, cwd=empty)
        blocked = [b.part for b in brain.blockers(Kind.BUILD)]
        self.assertIn(Part.QUALITY, blocked)
        self.assertNotIn(Part.QUALITY, [b.part for b in brain.blockers(Kind.QUESTION)])

    def test_no_knowledge_base_blocks_a_question_too(self):
        from sky.readiness import Kind
        with World(kb_down=True):
            brain = probes.run_all(A_KB, hand="claude", policy=POLICY,
                                   cwd=a_repo_with_tests())
        self.assertIn(Part.KNOWLEDGE, [b.part for b in brain.blockers(Kind.QUESTION)])


class TheGuardIsRunNotFound(unittest.TestCase):
    """G23a's rule applied to Safety: observe by using, never by finding."""

    def test_the_real_guard_really_refuses_a_push(self):
        out = subprocess.run(
            [sys.executable, "-m", "sky", "guard"], cwd=str(REPO / "core"),
            input=json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "git push origin main"}}),
            capture_output=True, text=True, timeout=30,
            env={"PATH": "/usr/bin:/bin", "SKY_LAUNCHED": "1",
                 "SKY_POLICY": str(REPO / "plugin" / "policy.yaml")})
        decision = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"]
        self.assertEqual(decision, "deny")

    def test_a_hooks_file_alone_is_not_the_evidence(self):
        """Stated as a test so the shortcut is not taken later."""
        source = (REPO / "core" / "sky" / "probes.py").read_text()
        self.assertIn("_guard_answers", source)
        self.assertNotIn("hooks.json", source,
                         "Safety must not conclude anything from a file existing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
