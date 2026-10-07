"""SH-067 inventory tests use fake providers; no network or credentials."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sky import inventory
from sky.policy import Policy


def policy(tool="Read", action="repo.read"):
    return Policy.from_dict({"version": 1,
        "actions": {"repo.read": {"outward": False}, "repo.edit": {"outward": False}},
        "tools": {"Edit": {"action": "repo.edit"},
                  tool: {"action": action, "reviewed_by": "@fixture"}},
        "skills": {"sample": {"tools": [tool]}},
        "roles": {"developer": {"base_tools": ["Edit"], "skills": ["sample"],
                                "may": ["repo.read", "repo.edit"], "needs_human": []}}})


def roster(annotations=None):
    meta = {} if annotations is None else {"annotations": annotations}
    return {"timestamp": "2026-10-06", "servers": {
        "fixture": {"timestamp": "2026-10-05", "tools": {"search": meta}}}}


class ToolInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".sky/tool-inventory.json"

    def save(self, body):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(body), encoding="utf-8")

    def test_unknown_tool_fails_naming_skill_binding_and_tool(self):
        notes, problems = inventory.check(policy("Unknown"), {"servers": {}})
        self.assertIn("skill sample: missing tool Unknown", "\n".join(problems))
        self.assertIn("binding Unknown: missing tool Unknown", "\n".join(problems))
        self.assertIn("role developer: missing tool Unknown", "\n".join(problems))

    def test_bash_pattern_passes_as_builtin(self):
        _, problems = inventory.check(policy("Bash(git status:*)"), {"servers": {}})
        self.assertEqual(problems, [])

    def test_unreachable_server_uses_inventory_with_dated_notice(self):
        self.save(roster())
        def unreachable(spec):
            raise OSError("secret transport detail")
        result, notes, failures = inventory.collect({"fixture": {}}, self.path, query=unreachable)
        self.assertEqual(failures, [])
        self.assertIn("unreachable (inventory from 2026-10-05)", notes[0])
        self.assertEqual(inventory.check(policy("mcp__fixture__search"), result)[1], [])
        self.assertNotIn("secret", "\n".join(notes))

    def test_unreachable_server_without_inventory_fails(self):
        def unreachable(spec):
            raise OSError()
        _, _, problems = inventory.collect({"fixture": {}}, self.path, query=unreachable)
        self.assertIn("fixture: unreachable with no recorded inventory", problems[0])

    def test_offline_uses_recorded_inventory_and_reports_it(self):
        self.save(roster())
        before = self.path.read_bytes()
        result, notes, problems = inventory.collect({"fixture": {}}, self.path, offline=True,
            query=lambda spec: self.fail("offline must not query"))
        self.assertEqual(problems, [])
        self.assertEqual(result["servers"], roster()["servers"])
        self.assertIn("offline: using recorded inventory", notes[0])
        self.assertEqual(self.path.read_bytes(), before)

    def test_read_binding_requires_true_read_only_annotation(self):
        p = inventory.install_annotation_hook(policy("mcp__fixture__search"))
        for annotations in ({}, {"readOnlyHint": False}, {"readOnlyHint": "true"}):
            self.assertIn("requires readOnlyHint: true", p.annotation_problems(roster(annotations))[0])
        self.assertEqual(p.annotation_problems(roster({"readOnlyHint": True})), [])

    def test_destructive_annotation_requires_outward_binding(self):
        p = inventory.install_annotation_hook(policy("mcp__fixture__search", "repo.edit"))
        self.assertIn("requires an outward action", p.annotation_problems(roster({"destructiveHint": True}))[0])

    def test_absent_annotations_and_absent_inventory_have_no_findings(self):
        p = inventory.install_annotation_hook(policy("mcp__fixture__search"))
        self.assertEqual(p.annotation_problems(), [])
        self.assertEqual(p.annotation_problems(roster()), [])

    def test_inventory_serialization_is_deterministic_with_sorted_keys(self):
        def query(spec):
            return {"z": {"annotations": {"readOnlyHint": True}}, "a": {}}
        inventory.collect({"z-server": {}, "a-server": {}}, self.path, query=query, now="fixed-date")
        before = self.path.read_bytes()
        inventory.collect({"a-server": {}, "z-server": {}}, self.path, query=query, now="fixed-date")
        self.assertEqual(self.path.read_bytes(), before)
        decoded = json.loads(before)
        self.assertEqual(list(decoded["servers"]), ["a-server", "z-server"])
        self.assertEqual(list(decoded["servers"]["a-server"]["tools"]), ["a", "z"])

    def test_unknown_hand_reports_empty_builtins(self):
        notes, problems = inventory.check(policy(), {"servers": {}}, hand="unknown")
        self.assertIn("unknown hand", notes[0])
        self.assertTrue(problems)

    def test_server_metadata_preserves_annotations_and_normalizes_names(self):
        tools = inventory.tool_metadata([{"name": "kb.search", "annotations": {"readOnlyHint": True}}])
        self.assertEqual(tools, {"kb_search": {"annotations": {"readOnlyHint": True}}})

    def test_extra_provider_tools_need_not_have_bindings(self):
        self.assertEqual(inventory.check(policy(), roster({"destructiveHint": True}))[1], [])

    def test_context_and_kb_map_servers_are_all_collected(self):
        root = Path(self.temp.name)
        (root / ".sky").mkdir()
        (root / ".sky/context.yaml").write_text(
            "servers:\n  fixture:\n    url: https://example.invalid/mcp\n", encoding="utf-8")
        kb_map = root / "kb-map.json"
        kb_map.write_text(json.dumps({
            "team": {"mcp_url": "https://example.invalid/kb", "tenant_code": "fixture",
                     "ontology": "fixture", "privacy": "work", "default": True,
                     "code_url": "https://example.invalid/code", "pat_env": "SH067_TEST_TOKEN"}}), encoding="utf-8")
        with patch.dict("os.environ", {"SKY_KB_URL": "", "SKY_CODE_URL": "", "SH067_TEST_TOKEN": "test-only"}):
            servers = inventory.configured_servers(root, kb_map=kb_map)
        self.assertEqual(set(servers), {"fixture", "kb", "code"})
        self.assertEqual(servers["kb"]["token"], "test-only")

    def test_effective_declared_skill_groups_are_checked_from_raw_policy(self):
        from sky.policy_layers import Layer, merge
        p = policy()
        p.body["tool_groups"] = {"fixture": ["Read"]}
        p.body["skills"]["sample"]["tools"] = ["+fixture"]
        root = Path(self.temp.name)
        effective = merge([Layer("plugin", p.body, root), Layer("project", {}, root)], root=root)
        self.assertEqual(inventory.check(effective, {"servers": {}})[1], [])

    def test_offline_script_prints_notice_and_checks_policy(self):
        script = Path(__file__).resolve().parents[2] / "scripts/check-allowlists.py"
        spec = importlib.util.spec_from_file_location("check_allowlists_sh067", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.save(roster())
        output = io.StringIO()
        with patch("sky.project.resolve", return_value=None), \
             patch("sky.project.git_root", return_value=Path(self.temp.name)), \
             patch("sky.policy.Policy.load", return_value=policy("mcp__fixture__search")), \
             patch("sky.inventory.configured_servers", return_value={"fixture": {}}), \
             patch("sky.inventory.query_server", side_effect=AssertionError("no network")), \
             redirect_stdout(output):
            result = module.main(["--offline", "--policy", "fixture.yaml"])
        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("offline: using recorded inventory", output.getvalue())
        self.assertIn("PASS", output.getvalue())

    def test_offline_script_without_inventory_reports_one_failure(self):
        script = Path(__file__).resolve().parents[2] / "scripts/check-allowlists.py"
        spec = importlib.util.spec_from_file_location("check_allowlists_missing_sh067", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with patch("sky.project.git_root", return_value=Path(self.temp.name)), \
             patch("sky.policy.Policy.load", return_value=policy("mcp__fixture__search")), \
             patch("sky.inventory.configured_servers", side_effect=AssertionError("must stop early")), \
             redirect_stdout(output):
            result = module.main(["--offline", "--policy", "fixture.yaml"])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue().splitlines(), [
            "no inventory at .sky/tool-inventory.json — run once without --offline to record it",
            "FAIL: 1 problem(s)."])
