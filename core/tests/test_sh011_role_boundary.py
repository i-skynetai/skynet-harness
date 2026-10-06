"""SH-011: a Claude role starts only with the checked agent definition.

Offline fixtures exercise refusal and the run record. They do not invoke the
authenticated live check in scripts/check-role-boundary.py.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sky import cli, launcher, probes
from sky.agent_definitions import DefinitionError, check_definition, plugin_root
from sky.policy import Policy
from sky.readiness import Brain, Part, State

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


class RoleBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copyfile(PLUGIN / "policy.yaml", self.root / "policy.yaml")
        shutil.copytree(PLUGIN / "agents", self.root / "agents")
        self.policy = Policy.load(self.root / "policy.yaml")
        self.file = self.root / "agents" / "reviewer.md"
        self.map = self.root / "kb-map.json"
        self.map.write_text(json.dumps({"fixture": {
            "purpose": "offline test", "mcp_url": "https://fixture.invalid/mcp/",
            "tenant_code": "TEST", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_TEST_PAT", "default": True,
        }}), encoding="utf-8")
        self.environment = patch.dict(os.environ, {
            "SKY_STATE_DIR": str(self.root / "state"), "SKY_TEST_PAT": "fixture-token",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def replace_tools(self, tools):
        self.file.write_text(
            "---\nname: reviewer\ndescription: Offline fixture\ntools: "
            + ", ".join(tools) + "\n---\nBody\n", encoding="utf-8")

    def build(self, dry_run=True):
        brain = Brain()
        for part in Part:
            brain.add(part, State.OK, "offline fixture")
        out, err = io.StringIO(), io.StringIO()
        def fake_hand(command, *, env, cwd, log_path):
            log_path.write_text("{}\n", encoding="utf-8")
            return cli.hand.Result(True, "finished", 0, log_path, 0, "offline hand ran")
        with patch.object(probes, "run_all", return_value=brain), \
                patch.object(launcher, "prove_git_blocked", return_value=(True, "fixture")), \
                patch.object(cli.hand, "run", side_effect=fake_hand) as hand_run, \
                patch.object(cli.broker, "collect_outbox", return_value=([], [])), \
                redirect_stdout(out), redirect_stderr(err):
            argv = [
                "--kb-map", str(self.map), "--policy", str(self.policy.path),
                "build", "--role", "reviewer", "--task", "SH-011", "--json",
            ]
            if dry_run:
                argv.append("--dry-run")
            code = cli.main(argv)
            if dry_run:
                hand_run.assert_not_called()
            elif code == 0:
                hand_run.assert_called_once()
        events = [json.loads(line) for p in (self.root / "state").glob("runs/*/events.jsonl")
                  for line in p.read_text(encoding="utf-8").splitlines()]
        return code, out.getvalue(), err.getvalue(), events

    def assert_refusal(self, fragment):
        code, out, err, events = self.build()
        self.assertEqual(code, 1)
        self.assertIn("agent definitions  MISSING", out)
        self.assertIn("reviewer", err)
        self.assertIn(str(self.file), err)
        self.assertIn(fragment, err)
        refused = next(e for e in events if e["kind"] == "launch_refused")
        self.assertIn(fragment, refused["reason"])
        self.assertEqual(events[-1]["outcome"], "refused")
        self.assertEqual(json.loads(out.splitlines()[-1])["stage"], "agent-definition")

    def test_matching_definition_proceeds_through_dry_run(self):
        code, out, err, events = self.build()
        self.assertEqual(code, 0, err)
        self.assertIn("agent definitions  ok", out)
        self.assertIn("--agent sky:reviewer", out)
        self.assertIn("--allowedTools", out)
        self.assertEqual(events[-1]["outcome"], "dry-run")

    def test_missing_file_refuses_before_launch(self):
        self.file.unlink()
        self.assert_refusal("cannot read agent definition")

    def test_matching_definition_starts_fake_hand_and_records_result(self):
        code, out, err, events = self.build(dry_run=False)
        self.assertEqual(code, 0, err)
        self.assertIn("offline hand ran", out)
        self.assertTrue(any(e["kind"] == "hand.start" for e in events))
        self.assertEqual(events[-1]["outcome"], "finished")

    def test_extra_tool_is_named_in_refusal(self):
        self.replace_tools([*self.policy.tools_for("reviewer"), "Edit"])
        self.assert_refusal("extra tool 'Edit'")

    def test_missing_tool_is_named_in_refusal(self):
        self.replace_tools([t for t in self.policy.tools_for("reviewer") if t != "Read"])
        self.assert_refusal("missing tool 'Read'")

    def test_unparsable_frontmatter_refuses(self):
        self.file.write_text("tools: Read\n", encoding="utf-8")
        self.assert_refusal("frontmatter")

    def test_tools_in_body_do_not_replace_missing_frontmatter_tools(self):
        self.file.write_text("---\nname: reviewer\n---\ntools: Read\n", encoding="utf-8")
        self.assert_refusal("missing frontmatter tools:")

    def test_duplicate_tools_field_refuses(self):
        self.file.write_text("---\nname: reviewer\ntools: Read\ntools: Edit\n---\n",
                             encoding="utf-8")
        self.assert_refusal("duplicate frontmatter field")

    def test_empty_tool_refuses(self):
        self.replace_tools([*self.policy.tools_for("reviewer"), ""])
        self.assert_refusal("empty")

    def test_wrong_agent_identity_refuses(self):
        self.file.write_text("---\nname: developer\ntools: Read\n---\n", encoding="utf-8")
        self.assert_refusal("name must be 'reviewer'")

    def test_unterminated_frontmatter_refuses(self):
        self.file.write_text("---\nname: reviewer\ntools: Read\n", encoding="utf-8")
        self.assert_refusal("missing closing")

    def test_invalid_utf8_definition_refuses(self):
        self.file.write_bytes(b"\xff")
        self.assert_refusal("cannot read agent definition")

    def test_order_does_not_matter_and_groups_are_expanded(self):
        tools = self.policy.tools_for("reviewer")
        self.assertTrue(any(t.startswith("mcp__kb__") for t in tools))
        self.replace_tools(list(reversed(tools)))
        self.assertEqual(check_definition(self.policy, "reviewer"), self.file)

    def test_command_builder_also_refuses_drift(self):
        self.replace_tools([*self.policy.tools_for("reviewer"), "Edit"])
        with self.assertRaisesRegex(launcher.Refused, "extra tool 'Edit'"):
            launcher.hand_command("claude", "reviewer", self.root / "mcp.json", "x", self.policy)

    def test_doctor_reports_all_four_matching_definitions(self):
        brain = Brain()
        probes.probe_agent_definitions(brain, self.policy)
        self.assertIs(brain.observations[-1].state, State.OK)
        self.assertIs(brain.observations[-1].part, Part.SAFETY)
        self.assertEqual(brain.observations[-1].name, "agent definitions")
        self.assertIn("agent definitions  ok", brain.table())
        self.assertIn("all four", brain.table())

    def test_doctor_reports_first_drift(self):
        self.replace_tools([*self.policy.tools_for("reviewer"), "Edit"])
        brain = Brain()
        probes.probe_agent_definitions(brain, self.policy)
        self.assertIs(brain.observations[-1].state, State.MISSING)
        self.assertIn("extra tool 'Edit'", brain.table())

    def test_doctor_checks_roles_other_than_the_launch_role(self):
        (self.root / "agents" / "developer.md").unlink()
        brain = Brain()
        probes.probe_agent_definitions(brain, self.policy)
        self.assertIn("developer", brain.table())
        self.assertIs(brain.observations[-1].state, State.MISSING)

    def test_explicit_policy_does_not_fall_back_when_agents_are_missing(self):
        shutil.rmtree(self.root / "agents")
        with patch.dict(os.environ, {"SKY_PLUGIN_ROOT": str(PLUGIN)}):
            self.assertEqual(plugin_root(self.policy), self.root)
            with self.assertRaises(DefinitionError):
                check_definition(self.policy, "reviewer")

    def test_doctor_without_policy_reports_missing(self):
        brain = Brain()
        probes.probe_safety(brain)
        probes.probe_agent_definitions(brain)
        self.assertIs(brain.observations[-1].state, State.MISSING)
        self.assertIs(brain.state_of(Part.SAFETY), State.MISSING)

    def test_non_claude_definition_probe_is_not_applicable(self):
        brain = Brain()
        probes.probe_agent_definitions(brain, self.policy, "codex")
        self.assertIs(brain.observations[-1].state, State.NA)


if __name__ == "__main__":
    unittest.main()
