"""Tests for the Habits and Remembering probes.

Both exist to catch a specific silent failure, and the tests are shaped around
those failures rather than around the happy path:

*Habits* — "the plugin did not load, which no config check reveals". So the
probe asks the **host**, not a settings file, and these tests check it reacts
to what the host says rather than to what is on disk.

*Remembering* — "job status COMPLETED with entities == 0, the failure that hid
for two days". Nothing but the entity count catches it, so that is the
assertion. And because this probe **writes to a shared knowledge base**, the
first test is that it does not run unless asked.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import probes  # noqa: E402
from sky.kbmap import KB  # noqa: E402
from sky.readiness import Brain, Part, State  # noqa: E402


def detail(brain: Brain, part: Part) -> str:
    return next(o.detail for o in brain.observations if o.part is part)


def a_kb(**over) -> KB:
    fields = dict(name="team_kb", purpose="x", url="https://kb.example/mcp/",
                  tenant="TEAM1234", ontology="sky_sdlc", privacy="work",
                  write=True, pat_env="SKY_TEST_PAT")
    fields.update(over)
    return KB(**fields)


class Habits(unittest.TestCase):
    def test_it_asks_the_host_and_reports_what_it_found(self):
        brain = Brain()
        probes.probe_habits(brain, "claude")
        state = brain.state_of(Part.HABITS)
        self.assertIn(state, (State.OK, State.DEGRADED, State.MISSING, State.DOWN))
        if state is State.OK:
            self.assertIn("skills", detail(brain, Part.HABITS))
            self.assertIn("agents", detail(brain, Part.HABITS))

    def test_a_hand_with_no_host_package_is_not_applicable_not_broken(self):
        """Codex and Kimi load no skills yet. That is H6, not a fault."""
        for hand in ("codex", "kimi"):
            with self.subTest(hand=hand):
                brain = Brain()
                probes.probe_habits(brain, hand)
                self.assertEqual(brain.state_of(Part.HABITS), State.NA)
                self.assertIn("H6", detail(brain, Part.HABITS))

    def test_a_plugin_the_host_does_not_list_is_missing(self):
        saved, saved_which = probes.subprocess.run, probes.shutil.which
        probes.shutil.which = lambda name: f"/usr/bin/{name}"
        probes.subprocess.run = lambda *a, **k: type(
            "R", (), {"stdout": "Installed plugins:\n\n  demo@demo-sdd\n    Status: enabled\n",
                      "stderr": "", "returncode": 0})()
        try:
            brain = Brain()
            probes.probe_habits(brain, "claude")
        finally:
            probes.subprocess.run, probes.shutil.which = saved, saved_which
        self.assertEqual(brain.state_of(Part.HABITS), State.MISSING)
        self.assertIn("marketplace", detail(brain, Part.HABITS))

    def test_installed_but_disabled_is_down_because_nothing_loads(self):
        saved, saved_which = probes.subprocess.run, probes.shutil.which
        probes.shutil.which = lambda name: f"/usr/bin/{name}"
        probes.subprocess.run = lambda *a, **k: type(
            "R", (), {"stdout": "Installed plugins:\n\n  sky@sky\n    Version: 0.4.0\n"
                                "    Status: disabled\n", "stderr": "", "returncode": 0})()
        try:
            brain = Brain()
            probes.probe_habits(brain, "claude")
        finally:
            probes.subprocess.run, probes.shutil.which = saved, saved_which
        self.assertEqual(brain.state_of(Part.HABITS), State.DOWN)
        self.assertIn("not enabled", detail(brain, Part.HABITS))


class RememberingWritesSoItIsOptIn(unittest.TestCase):
    def test_by_default_it_does_not_run_and_says_so(self):
        """A probe document on every doctor would outlive its question."""
        brain = Brain()
        probes.probe_remembering(brain, a_kb())
        self.assertEqual(brain.state_of(Part.REMEMBERING), State.DEGRADED)
        self.assertIn("not probed", detail(brain, Part.REMEMBERING))
        self.assertIn("--deep", detail(brain, Part.REMEMBERING))

    def test_a_read_only_kb_is_not_applicable(self):
        brain = Brain()
        probes.probe_remembering(brain, a_kb(write=False), deep=True)
        self.assertEqual(brain.state_of(Part.REMEMBERING), State.NA)
        self.assertIn("read-only", detail(brain, Part.REMEMBERING))


class TheEntityCountIsTheWholePoint(unittest.TestCase):
    """COMPLETED with zero entities is the failure that hid for two days."""

    def test_completed_with_zero_entities_is_down_not_ok(self):
        self.assertEqual(probes._entity_count({"status": "COMPLETED", "entities": 0}), 0)

    def test_the_count_is_found_wherever_it_is_reported(self):
        for body in ({"entities": 7},
                     {"entity_count": 7},
                     {"entities_extracted": 7},
                     {"stats": {"entities": 7}},
                     {"result": {"entity_count": 7}}):
            with self.subTest(shape=sorted(body)):
                self.assertEqual(probes._entity_count(body), 7)

    def test_a_missing_count_is_none_not_zero(self):
        """None means "not reported"; zero means "reported as none extracted".
        Collapsing them would turn an unknown into a definite failure."""
        self.assertIsNone(probes._entity_count({"status": "COMPLETED"}))

    def test_a_job_id_is_found_wherever_it_is_reported(self):
        import json as _json
        for key in ("job_id", "id", "jobId"):
            with self.subTest(key=key):
                result = {"content": [{"type": "text",
                                       "text": _json.dumps({key: "j-1"})}]}
                self.assertEqual(probes._job_id(result), "j-1")

    def test_no_job_id_is_empty_not_a_crash(self):
        self.assertEqual(probes._job_id({"content": [{"type": "text", "text": "hi"}]}), "")


class TheCountIsInTheOutputNotTheStatus(unittest.TestCase):
    """Two calls, not one — measured on a live run.

    `jobs.status` reports progress and stages and carries no entity count; the
    count is in `jobs.output` (`output.entities`). A probe polling only the
    status sees COMPLETED and can say nothing about whether anything was
    learned — blind to exactly the failure it exists for.
    """

    def test_the_count_is_read_from_the_real_output_shape(self):
        """The shape a live job actually returned."""
        body = {"job_id": "j-1", "status": "COMPLETED", "ready": True,
                "output": {"empty": False, "layer": "project", "chunks": 1,
                           "status": "ingested", "entities": 3, "relations": 1,
                           "ontology": "kb_sdlc", "document_id": "f54805d6e414",
                           "tenant_code": "DEMO0001", "was_duplicate": False},
                "errors": []}
        self.assertEqual(probes._entity_count(body), 3)

    def test_the_status_shape_alone_yields_no_count(self):
        """What `jobs.status` returns — no entities anywhere in it."""
        body = {"job_id": "j-1", "job_type": "document_ingest", "status": "COMPLETED",
                "progress_pct": 100,
                "stages": [{"name": "resolve_tenant", "status": "completed"},
                           {"name": "fetch_staged", "status": "completed"}]}
        self.assertIsNone(probes._entity_count(body),
                          "reading the status as if it carried the count is the bug")

    def test_zero_entities_in_a_completed_output_is_the_failure_to_catch(self):
        body = {"status": "COMPLETED", "output": {"status": "ingested", "chunks": 1,
                                                  "entities": 0, "relations": 0}}
        self.assertEqual(probes._entity_count(body), 0)


class TheProbeDocumentIsWrittenForTheOntology(unittest.TestCase):
    """A fixed probe document gives a FALSE DOWN on a healthy knowledge base.

    The first version said "the ProbeModule component depends on the ProbeStore
    datastore" — SDLC vocabulary. Ingested under `sky_skill`, whose types are
    Skill, Trigger, Step, Tool…, it correctly extracted nothing, and the probe
    reported the exact failure it exists to detect. A false DOWN is worse than
    no probe, because Remembering blocks a build.
    """

    def test_entity_names_are_read_from_a_structured_ontology(self):
        body = {"name": "sky_skill",
                "entity_types": [{"name": "Skill"}, {"name": "Step"}, {"name": "Tool"}]}
        saved = probes._rpc
        probes._rpc = lambda *a, **k: {"content": [{"type": "text",
                                                    "text": __import__("json").dumps(body)}]}
        try:
            self.assertEqual(probes._entity_types(a_kb(), "t"), ["Skill", "Step", "Tool"])
        finally:
            probes._rpc = saved

    def test_entity_names_are_read_from_a_yaml_body_too(self):
        """Without taking a YAML dependency — core has none."""
        yaml = ("name: sky_skill\n"
                "description: x\n"
                "entity_types:\n"
                "  - name: Skill\n"
                "    description: a procedure\n"
                "  - name: Step\n"
                "    description: one step\n"
                "relation_types:\n"
                "  - name: SKILL_HAS_STEP\n")
        self.assertEqual(probes._names_under(yaml, "entity_types"), ["Skill", "Step"])
        self.assertEqual(probes._names_under(yaml, "relation_types"), ["SKILL_HAS_STEP"])

    def test_an_ontology_with_no_entity_types_is_reported_not_ingested_into(self):
        saved = probes._entity_types
        probes._entity_types = lambda kb, token: []
        try:
            brain = Brain()
            probes.probe_remembering(brain, a_kb(), deep=True)
        finally:
            probes._entity_types = saved
        self.assertEqual(brain.state_of(Part.REMEMBERING), State.DOWN)
        self.assertIn("no entity types", detail(brain, Part.REMEMBERING))


class NothingIsPendingExceptInputs(unittest.TestCase):
    def test_only_inputs_remains_unbuilt(self):
        """Habits and Remembering were in this list; a stale entry would mask a
        real probe result."""
        self.assertEqual({p.value for p in probes._PENDING}, {"inputs"})
