"""SH-064: skill authority, legacy compatibility and reviewable rendering."""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from sky import cli, yamlish
from sky.policy import Policy, PolicyError

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def fixture():
    return {"version": 1, "actions": {
        "repo.read": {"outward": False}, "repo.edit": {"outward": False},
        "push": {"outward": True, "broker": "push_branch"},
        "shell.free": {"never": "unrestricted shell"}},
        "tools": {"Read": "repo.read", "Grep": "repo.read", "Edit": "repo.edit",
                  "Bash(test:*)": "repo.edit"},
        "skills": {"read": {"tools": ["Read", "Grep"]}},
        "roles": {"reviewer": {"base_tools": ["Read"], "skills": ["read"],
                               "may": ["repo.read"]}}}


class SkillsOwnTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.agents = self.root / "agents"
        self.agents.mkdir()
        self.file = self.agents / "reviewer.md"
        self.original = "---\nname: reviewer\ndescription: fixture\ntools: Read\n---\nBody\ntools: body untouched\n"
        self.file.write_text(self.original, encoding="utf-8")

    def policy(self, body=None):
        return Policy.from_dict(fixture() if body is None else body,
                                path=self.root / "policy.yaml")

    def refuses(self, body, *messages):
        with self.assertRaises(PolicyError) as caught:
            self.policy(body)
        for message in messages:
            self.assertIn(message, str(caught.exception))

    def command(self, policy, action):
        # Real loader and parser: JSON is emitted as this reader's YAML subset.
        def yaml_mapping(data, indent=0):
            lines = []
            for key, value in data.items():
                prefix = " " * indent + json.dumps(key) + ":"
                if isinstance(value, dict):
                    lines.append(prefix)
                    lines.extend(yaml_mapping(value, indent + 2))
                elif isinstance(value, list) and any(isinstance(v, dict) for v in value):
                    lines.append(prefix)
                    for item in value:
                        lines.append(" " * (indent + 2) + "-")
                        lines.extend(yaml_mapping(item, indent + 4))
                else:
                    lines.append(prefix + " " + json.dumps(value))
            return lines
        path = self.root / "policy.yaml"
        path.write_text("\n".join(yaml_mapping(policy.body)) + "\n", encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            result = cli.main(["--policy", str(path), "policy", action])
        return result, out.getvalue()

    def test_legacy_tools_policy_keeps_loading_without_bindings(self):
        body = fixture()
        body.pop("tools")
        body.pop("skills")
        body["roles"]["reviewer"] = {"tools": ["Read"], "may": ["repo.read"]}
        policy = self.policy(body)
        self.assertEqual(policy.tools_for("reviewer"), ("Read",))
        self.assertEqual(policy.artifact_problems(self.agents), [])
        self.assertEqual(self.command(policy, "lint")[0], 0)

    def test_base_and_skill_union_preserves_order_and_deduplicates(self):
        body = fixture()
        body["roles"]["reviewer"]["base_tools"] = ["Grep", "Read"]
        self.assertEqual(self.policy(body).tools_for("reviewer"), ("Grep", "Read"))

    def test_groups_expand_before_binding_lookup(self):
        body = fixture()
        body["tool_groups"] = {"reads": ["Read", "Grep", "Read"]}
        body["skills"]["read"]["tools"] = ["+reads"]
        self.assertEqual(self.policy(body).tools_for("reviewer"), ("Read", "Grep"))

    def test_binding_and_skills_for_return_declared_values(self):
        policy = self.policy()
        policy.bindings["Grep"] = {"action": "repo.read"}
        self.assertEqual(policy.binding("Grep"), "repo.read")
        self.assertIsNone(policy.binding("Unknown"))
        self.assertEqual(policy.skills_for("reviewer"), ("read",))

    def test_unknown_role_is_refused(self):
        for operation in (self.policy().tools_for, self.policy().skills_for):
            with self.assertRaisesRegex(PolicyError, "not a role"):
                operation("unknown")

    def test_unknown_skill_is_refused(self):
        body = fixture()
        body["roles"]["reviewer"]["skills"] = ["unknown"]
        self.refuses(body, "reviewer", "unknown", "not defined")

    def test_skill_roles_key_is_refused(self):
        body = fixture()
        body["skills"]["read"]["roles"] = []
        self.refuses(body, "roles key is not allowed")

    def test_legacy_tools_mixed_with_new_keys_is_refused(self):
        for field in ("base_tools", "skills"):
            body = fixture()
            body["roles"]["reviewer"] = {"tools": ["Read"], field: [], "may": ["repo.read"]}
            self.refuses(body, "legacy tools cannot be mixed")

    def test_malformed_binding_skill_and_role_lists_are_refused(self):
        for location, value in (("binding", []), ("binding", {"action": 3}),
                                ("skill", []), ("skill_tools", "Read"),
                                ("base_tools", "Read"), ("skills", "read")):
            body = fixture()
            if location == "binding":
                body["tools"]["Read"] = value
            elif location == "skill":
                body["skills"]["read"] = value
            elif location == "skill_tools":
                body["skills"]["read"]["tools"] = value
            else:
                body["roles"]["reviewer"][location] = value
            with self.subTest(location=location, value=value):
                self.refuses(body)

    def test_every_new_style_tool_requires_binding(self):
        for source in ("base_tools", "skill"):
            body = fixture()
            if source == "skill":
                body["skills"]["read"]["tools"].append("Unknown")
            else:
                body["roles"]["reviewer"]["base_tools"].append("Unknown")
            self.refuses(body, "Unknown", "no binding")

    def test_binding_to_unknown_action_is_refused(self):
        body = fixture()
        body["tools"]["Read"] = "typo"
        self.refuses(body, "typo", "not a defined action")

    def test_missing_role_action_names_role_skill_tool_and_action(self):
        body = fixture()
        body["roles"]["reviewer"]["may"] = []
        self.refuses(body, "reviewer", "skill read", "Read", "repo.read", "not in may")

    def test_outward_and_never_tools_are_refused_in_skills_base_and_groups(self):
        for action in ("push", "shell.free"):
            for source in ("skill", "base", "group", "ungranted"):
                body = fixture()
                body["tools"]["Forbidden"] = action
                if source == "base":
                    body["roles"]["reviewer"]["base_tools"].append("Forbidden")
                elif source == "group":
                    body["tool_groups"] = {"bad": ["Forbidden"]}
                    body["skills"]["read"]["tools"].append("+bad")
                elif source == "ungranted":
                    body["skills"]["idle"] = {"tools": ["Forbidden"]}
                else:
                    body["skills"]["read"]["tools"].append("Forbidden")
                with self.subTest(action=action, source=source):
                    self.refuses(body, "Forbidden", action, ".sky/outbox/")
        policy = self.policy()
        policy.bindings["Read"] = "push"
        self.assertNotIn("Read", policy.tools_for("reviewer"))

    def test_read_only_role_cannot_gain_shell_or_editing_through_skill(self):
        for tool in ("Edit", "Bash(test:*)"):
            body = fixture()
            body["skills"]["read"]["tools"].append(tool)
            self.refuses(body, "writer wearing its name")

    def test_groups_used_only_by_granted_skills_are_not_unused(self):
        body = fixture()
        body["tool_groups"] = {"reads": ["Read"]}
        body["skills"]["read"]["tools"] = ["+reads"]
        self.assertEqual(self.policy(body).lint(), [])
        body["roles"]["reviewer"]["skills"] = []
        self.refuses(body, "used by no role")

    def test_shipped_conversion_preserves_each_complete_agent_tools_line(self):
        policy = Policy.load(PLUGIN / "policy.yaml")
        for role in policy.roles_named():
            lines = (PLUGIN / "agents" / f"{role}.md").read_text(encoding="utf-8").splitlines()
            self.assertEqual(policy.agent_tools_line(role), next(l for l in lines if l.startswith("tools:")))
        self.assertEqual(policy.sync_agents(PLUGIN / "agents", write=False), [])

    def test_all_twenty_three_skill_directories_have_policy_entries(self):
        policy = Policy.load(PLUGIN / "policy.yaml")
        names = {p.name for p in (PLUGIN / "skills").iterdir() if (p / "SKILL.md").is_file()}
        self.assertEqual(len(names), 23)
        self.assertEqual(set(policy.skills), names)
        _, output = self.command(self.policy(copy.deepcopy(policy.body)), "show")
        self.assertIn("declared, granted to no role", output)
        self.assertIn("SH-082", output)
        self.assertIn("adr", output)

    def test_render_preserves_agent_metadata_body_and_helpers(self):
        helper = self.agents / "validator.md"
        helper.write_text("untouched", encoding="utf-8")
        self.policy().render(self.agents)
        self.assertEqual(self.file.read_text(encoding="utf-8"),
                         self.original.replace("tools: Read\n", "tools: Read, Grep\n"))
        self.assertEqual(helper.read_text(encoding="utf-8"), "untouched")
        verdict = expected_verdict = self.file.read_text(encoding="utf-8").replace(
            "description: fixture", "description: Return VERDICT: APPROVED or VERDICT: BLOCKED")
        self.file.write_text(verdict, encoding="utf-8")
        self.assertEqual(self.policy().render(self.agents), [])
        self.assertEqual(self.file.read_text(encoding="utf-8"), expected_verdict)
        block = self.original.replace("tools: Read\n", "tools:\n  - Read\n")
        self.file.write_bytes(block.replace("\n", "\r\n").encode("utf-8"))
        self.policy().render(self.agents)
        expected = self.original.replace("tools: Read\n", "tools: Read, Grep\n")
        self.assertEqual(self.file.read_bytes(), expected.replace("\n", "\r\n").encode("utf-8"))

    def test_render_writes_deterministic_registry_and_is_idempotent(self):
        policy = self.policy()
        self.assertEqual(policy.render(self.agents), ["reviewer", "registry.json"])
        path = self.root / "registry.json"
        before = path.read_bytes()
        self.assertEqual(json.loads(before), policy.registry())
        self.assertEqual(policy.render(self.agents), [])
        self.assertEqual(path.read_bytes(), before)
        reordered = dict(reversed(list(fixture().items())))
        self.assertEqual(policy.digest(), self.policy(reordered).digest())
        text = "version: 1\nroles:\n  a: [Read, Grep]\n"
        first = yamlish.parse(text)
        second = yamlish.parse("# comment\n" + text.replace("version: 1", "version:    1"))
        policy.body = first
        digest = policy.digest()
        policy.body = second
        self.assertEqual(policy.digest(), digest)
        policy.body["roles"]["a"].reverse()
        self.assertNotEqual(policy.digest(), digest)

    def test_render_refuses_missing_or_malformed_agent_templates(self):
        for text in (None, "tools: Read\n", "---\nname: wrong\ntools: Read\n---\n", "---\nname: reviewer\n",
                     "---\nname: reviewer\ntools:\n---\n",
                     "---\nname: reviewer\ntools: []\n---\n",
                     "---\nname: reviewer\ntools: Read\ntools: Grep\n---\n"):
            if text is None:
                self.file.unlink()
            else:
                self.file.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(PolicyError, "before writing"):
                self.policy().render(self.agents)
            self.assertFalse((self.root / "registry.json").exists())

    def test_lint_detects_missing_stale_malformed_registry_and_agent_drift(self):
        policy = self.policy()
        self.assertNotEqual(self.command(policy, "lint")[0], 0)
        policy.render(self.agents)
        self.assertEqual(self.command(policy, "lint")[0], 0)
        path = self.root / "registry.json"
        for contents in (b"broken", b'{"digest": "old", "agents": {}}', b"\xff"):
            path.write_bytes(contents)
            code, output = self.command(policy, "lint")
            self.assertNotEqual(code, 0)
            self.assertIn("run sky policy render", output)
        policy.render(self.agents)
        self.file.write_text(self.original, encoding="utf-8")
        code, output = self.command(policy, "lint")
        self.assertNotEqual(code, 0)
        self.assertIn("agent drift", output)

    def test_render_can_repair_artifact_drift_without_bypassing_policy_errors(self):
        policy = self.policy()
        self.assertEqual(self.command(policy, "render")[0], 0)
        self.assertEqual(self.command(policy, "lint")[0], 0)
        policy.body["roles"]["reviewer"]["skills"] = ["typo"]
        before = (self.root / "registry.json").read_bytes()
        self.assertNotEqual(self.command(policy, "render")[0], 0)
        self.assertEqual((self.root / "registry.json").read_bytes(), before)

    def test_sync_agents_cli_alias_and_check_agents_remain_compatible(self):
        policy = self.policy()
        code, output = self.command(policy, "check-agents")
        self.assertNotEqual(code, 0)
        self.assertIn("DRIFTED reviewer", output)
        self.assertEqual(policy.sync_agents(self.agents, write=False), ["reviewer"])
        self.assertEqual(self.command(policy, "sync-agents")[0], 0)
        self.assertEqual(self.command(policy, "check-agents")[0], 0)
        code, output = self.command(policy, "sync-agents")
        self.assertEqual(code, 0)
        self.assertIn("all 1 role agents match", output)

    def test_bad_policy_leaves_rendered_artifacts_unchanged(self):
        policy = self.policy()
        body = copy.deepcopy(policy.body)
        body["roles"]["second"] = copy.deepcopy(body["roles"]["reviewer"])
        policy = self.policy(body)
        before = self.file.read_bytes()
        with self.assertRaises(PolicyError):
            policy.render(self.agents)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse((self.root / "registry.json").exists())
        policy = self.policy()
        policy.bindings["Read"] = "unknown"
        with self.assertRaises(PolicyError):
            policy.render(self.agents)
        self.assertEqual(self.file.read_bytes(), before)

    def test_mcp_bindings_require_reviewed_by(self):
        for binding in ("repo.read", {"action": "repo.read"},
                        {"action": "repo.read", "reviewed_by": " "}):
            body = fixture()
            body["tools"]["mcp__kb__read"] = binding
            self.refuses(body, "mcp__kb__read", "reviewed_by")
        body["tools"]["mcp__kb__read"]["reviewed_by"] = "@reviewer"
        self.assertEqual(self.policy(body).lint(), [])

    def test_annotation_hook_returns_no_problems_without_inventory(self):
        self.assertEqual(self.policy().annotation_problems(), [])


if __name__ == "__main__":
    unittest.main()
