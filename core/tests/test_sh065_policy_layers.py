"""SH-065: real temporary worktrees, immutable ceilings and owned renders.

No installed plugin, credentials, network or live model is required.
"""
from __future__ import annotations

import copy
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sky import cli, launcher, project
from sky.agent_definitions import DefinitionError, check_definition
from sky.policy import Policy, PolicyError
from sky.policy_layers import Layer, merge, read_agent


def base_policy():
    return {"version": 1, "actions": {
        "repo.read": {"outward": False}, "repo.edit": {"outward": False},
        "kb.read": {"outward": False},
        "push": {"outward": True, "broker": "push_branch"},
        "never": {"outward": True, "never": "human checkpoint"}},
        "tools": {"Read": "repo.read", "Grep": "repo.read", "Glob": "repo.read",
                  "Edit": "repo.edit", "Write": "repo.edit",
                  "mcp__kb__search": {"action": "kb.read", "reviewed_by": "@fixture"}},
        "tool_groups": {"kb": ["mcp__kb__search"]},
        "skills": {"read": {"tools": ["Read", "+kb"]}},
        "roles": {
            "developer": {"base_tools": ["Read", "Edit", "Write", "Grep", "Glob"],
                          "skills": ["read"], "may": ["repo.read", "repo.edit", "kb.read"],
                          "needs_human": ["push"]},
            "reviewer": {"base_tools": ["Read", "Grep", "Glob"], "skills": ["read"],
                         "may": ["repo.read", "kb.read"], "needs_human": []}},
        "guard": {"scope": "harness_runs_only", "fails": "closed-in-run"}}


def new_role(skills=None):
    return {"base_tools": ["Read"], "skills": skills or [],
            "may": ["repo.read", "kb.read"], "needs_human": []}


def write_yaml(path, value):
    def emit(mapping, indent=0):
        lines = []
        for key, val in mapping.items():
            prefix = " " * indent + json.dumps(key) + ":"
            if isinstance(val, dict):
                if val:
                    lines.append(prefix)
                    lines.extend(emit(val, indent + 2))
            elif isinstance(val, list) and any(isinstance(v, dict) for v in val):
                lines.append(prefix)
                for item in val:
                    lines.append(" " * (indent + 2) + "-")
                    lines.extend(emit(item, indent + 4))
            else:
                lines.append(prefix + " " + json.dumps(val))
        return lines
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(emit(value)) + "\n", encoding="utf-8")


class PolicyLayers(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"):
            self.skipTest("git is required for worktree discovery fixtures")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name).resolve()
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.plugin = self.tmp / "plugin"
        self.cache = self.tmp / "cache"
        self.org = self.cache / "fixture-market" / "team" / "1.0.0"
        self.org.mkdir(parents=True)
        self.body = base_policy()
        write_yaml(self.plugin / "policy.yaml", self.body)
        write_yaml(self.org / "policy.yaml", {})
        for role in self.body["roles"]:
            self.agent(self.plugin, role, Policy.from_dict(self.body).tools_for(role))
        self.config({"managed": True})
        self.env = patch.dict(os.environ, {"SKY_PLUGIN_ROOT": str(self.plugin)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.saved_override = os.environ.pop("SKY_POLICY", None)
        self.addCleanup(self.restore_override)
        self.configured = patch("sky.policy.CONFIG_POLICY", str(self.tmp / "absent-config.yaml"))
        self.configured.start()
        self.addCleanup(self.configured.stop)
        self.cache_patch = patch("sky.policy.PLUGIN_CACHE", str(self.cache))
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def restore_override(self):
        os.environ.pop("SKY_POLICY", None)
        if self.saved_override is not None:
            os.environ["SKY_POLICY"] = self.saved_override

    def git(self, *args):
        out = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=20)
        self.assertEqual(out.returncode, 0, (out.stdout or "") + (out.stderr or ""))
        return out

    def config(self, body):
        write_yaml(self.root / ".sky" / "project.yaml", body)

    def agent(self, directory, role, tools=("Read",), description="Return VERDICT: APPROVED"):
        path = directory / "agents" / f"{role}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {role}\ndescription: {description}\ntools: {', '.join(tools)}\n---\nFixture body\n", encoding="utf-8")
        return path

    def effective(self, org=None, patch_body=None):
        layers = [Layer("plugin", copy.deepcopy(self.body), self.plugin, "sky")]
        if org is not None:
            layers.append(Layer("org", org, self.org, "team"))
        layers.append(Layer("project", patch_body or {}, self.root / ".sky"))
        return merge(layers, root=self.root, config={"managed": True})

    def resolved(self, cwd=None):
        return project.resolve(cwd or self.root, shipped=self.plugin / "policy.yaml", cache=self.cache)

    def org_agents(self, effective):
        for role, history in effective.history.items():
            if any(source == "org" for source, _ in history):
                self.agent(self.org, role, effective.snapshots["org"][role])

    def refuses(self, body, message, org=False):
        with self.assertRaises(PolicyError) as caught:
            self.effective(org=body) if org else self.effective(patch_body=body)
        self.assertIn(message, str(caught.exception))
        self.assertIn("org layer" if org else "project layer", str(caught.exception))

    @contextmanager
    def here(self, root=None):
        previous = Path.cwd()
        os.chdir(root or self.root)
        try:
            yield
        finally:
            os.chdir(previous)

    def command(self, *args):
        output = io.StringIO()
        with self.here(), redirect_stdout(output), redirect_stderr(output):
            result = cli.main(list(args))
        return result, output.getvalue()

    def test_layers_merge_shipped_then_org_then_project(self):
        org = {"skills": {"org-read": {"tools": ["Grep"]}},
               "roles": {"developer": {"skills_add": ["org-read"]}}}
        later = {"skills": {"project-read": {"tools": ["Glob"]}},
                 "roles": {"developer": {"skills_add": ["project-read", "org-read"]}}}
        result = self.effective(org, later)
        self.assertEqual(result.skills_for("developer"), ("read", "org-read", "project-read"))
        self.assertEqual(result.role_sources["developer"], "plugin")
        self.assertEqual([l.name for l in result.layers], ["plugin", "org", "project"])

    def test_partial_layers_are_merged_before_structural_lint(self):
        patch_body = {"skills": {"extra": {"tools": ["Grep"]}},
                      "roles": {"reviewer": {"skills_add": ["extra"]}}}
        with self.assertRaises(PolicyError):
            Policy.from_dict(patch_body)
        self.assertEqual(self.effective(patch_body=patch_body).lint(), [])

    def test_later_layer_cannot_add_or_change_actions(self):
        for value in ({"new": {"outward": False}}, {"repo.read": {"never": "new"}},
                      {"push": {"outward": False, "broker": "new"}}, {}):
            self.refuses({"actions": value}, "actions")
        for key in ("version", "ingest", "tickets"):
            self.refuses({key: {}}, key)

    def test_later_layer_cannot_change_guard(self):
        for key in ("scope", "fails", "deny_commands"):
            self.refuses({"guard": {key: "changed"}}, "guard", org=True)

    def test_outward_may_and_never_grants_name_the_offending_layer(self):
        for action in ("push", "never"):
            role = new_role()
            role["may"].append(action)
            self.refuses({"roles": {"extra": role}}, action, org=True)
        for action in ("push", "never"):
            self.refuses({"tools": {"Out": action}, "skills": {"bad": {"tools": ["Out"]}}}, "Out")

    def test_unknown_action_binding_names_the_offending_layer(self):
        self.refuses({"tools": {"Extra": "typo"}}, "unknown action", org=True)

    def test_existing_binding_cannot_be_rebound(self):
        for value in ("repo.read", "repo.edit"):
            self.refuses({"tools": {"Read": value}}, "existing name")
        self.refuses({"tool_groups": {"kb": ["Read"]}}, "existing name")

    def test_added_mcp_binding_requires_reviewed_by(self):
        self.refuses({"tools": {"mcp__extra__read": "repo.read"}}, "reviewed_by")
        result = self.effective(patch_body={"tools": {"mcp__extra__read": {
            "action": "repo.read", "reviewed_by": "@fixture"}}})
        self.assertEqual(result.binding("mcp__extra__read"), "repo.read")

    def test_lower_layer_legacy_tools_role_is_refused(self):
        self.refuses({"roles": {"extra": {"tools": ["Read"]}}}, "legacy tools")

    def test_removals_expand_groups_and_preserve_remaining_order(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["+kb"]}}})
        self.assertEqual(result.tools_for("developer"), ("Read", "Edit", "Write", "Grep", "Glob"))
        self.assertEqual(result.revocations["developer"]["tools"], {"mcp__kb__search": "project"})
        # Removing the grant preserves the overlapping base tool.
        result = self.effective(patch_body={"roles": {"developer": {"skills_remove": ["read"]}}})
        self.assertIn("Read", result.tools_for("developer"))
        self.assertEqual(result.revocations["developer"]["skills"], {"read": "project"})

    def test_removed_tool_cannot_return_through_group_alias(self):
        org = {"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}}
        patch_body = {"tool_groups": {"alias": ["+kb"]},
                      "skills": {"alias": {"tools": ["+alias"]}},
                      "roles": {"developer": {"skills_add": ["alias"]}}}
        with self.assertRaisesRegex(PolicyError, "project layer.*revoked by org"):
            self.effective(org, patch_body)

    def test_removed_tool_cannot_return_through_new_skill(self):
        org = {"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}}
        patch_body = {"skills": {"alias": {"tools": ["mcp__kb__search"]}},
                      "roles": {"developer": {"skills_add": ["alias"]}}}
        with self.assertRaisesRegex(PolicyError, "revoked by org"):
            self.effective(org, patch_body)

    def test_removed_tool_does_not_bar_fresh_new_role(self):
        org = {"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}}
        result = self.effective(org, {"roles": {"extra": new_role(["read"])}})
        self.assertIn("mcp__kb__search", result.tools_for("extra"))
        self.assertNotIn("mcp__kb__search", result.tools_for("developer"))

    def test_removed_skill_cannot_return_by_rename_or_indirect_grant(self):
        org = {"roles": {"developer": {"skills_remove": ["read"]}}}
        for name in ("read", "alias"):
            later = {"roles": {"developer": {"skills_add": [name]}}}
            if name == "alias":
                later["skills"] = {name: {"tools": ["mcp__kb__search"]}}
            with self.assertRaisesRegex(PolicyError, "revoked by org"):
                self.effective(org, later)
        with self.assertRaisesRegex(PolicyError, "revoked by org"):
            self.effective({"roles": {"developer": {"tools_remove": ["Read"]}}},
                           {"skills": {"read": {"tools_add": ["Read"]}}})

    def test_removal_does_not_revoke_unrelated_inherited_grants(self):
        result = self.effective(patch_body={"roles": {"developer": {"skills_remove": ["read"]}}})
        self.assertEqual(result.tools_for("reviewer"), ("Read", "Grep", "Glob", "mcp__kb__search"))

    def test_overlapping_skill_removal_preserves_tools_identity_and_records_revocation(self):
        self.body["skills"]["overlap"] = {"tools": ["Read", "Edit"]}
        self.body["roles"]["developer"]["skills"].append("overlap")
        original = Policy.from_dict(self.body).tools_for("developer")
        org = {"roles": {"developer": {"skills_remove": ["overlap"]}}}
        result = self.effective(org)
        self.assertEqual(result.tools_for("developer"), original)
        self.assertEqual(result.revocations["developer"],
                         {"tools": {}, "skills": {"overlap": "org"}})
        result.render()
        self.assertFalse((self.root / ".claude/agents/sky-developer.md").exists())
        registry = json.loads((self.root / ".sky/registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["active_roles"]["developer"], "sky:developer")
        self.assertEqual(registry["revocations"], result.revocations)
        self.assertIn("removed.roles.developer.skills.overlap: org", result.layer_lines())
        with self.assertRaisesRegex(PolicyError, "skill overlap revoked by org"):
            self.effective(org, {"roles": {"developer": {"skills_add": ["overlap"]}}})

    def test_partly_unique_skill_removal_revokes_only_lost_tools_and_renders_remaining_tools(self):
        result = self.effective(patch_body={"roles": {"developer": {"skills_remove": ["read"]}}})
        remaining = ("Read", "Edit", "Write", "Grep", "Glob")
        self.assertEqual(result.tools_for("developer"), remaining)
        self.assertEqual(result.revocations["developer"]["tools"], {"mcp__kb__search": "project"})
        result.render()
        self.assertEqual(read_agent(self.root / ".claude/agents/sky-developer.md").tools, remaining)

    def test_tools_remove_revokes_overlapping_base_and_skill_grants(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["Read"]}}})
        self.assertNotIn("Read", result.tools_for("developer"))
        self.assertEqual(result.revocations["developer"]["tools"], {"Read": "project"})

    def test_reordered_same_tool_set_keeps_plugin_identity_and_writes_no_agent(self):
        self.body["skills"] = {
            "early": {"tools": ["Grep", "Glob"]},
            "middle": {"tools": ["+kb"]},
            "late": {"tools": ["Glob", "Grep"]}}
        self.body["roles"]["developer"]["base_tools"] = ["Read", "Edit", "Write"]
        self.body["roles"]["developer"]["skills"] = ["early", "middle", "late"]
        self.body["roles"]["reviewer"]["skills"] = ["middle"]
        for role in self.body["roles"]:
            self.agent(self.plugin, role, Policy.from_dict(self.body).tools_for(role))
        # A pre-existing narrowed agent must also become stale on a set match.
        self.effective(patch_body={"roles": {"developer": {"tools_remove": ["Read"]}}}).render()
        result = self.effective(patch_body={"roles": {"developer": {"skills_remove": ["early"]}}})
        self.assertEqual(result.tools_for("developer"), Policy.from_dict(self.body).tools_for("developer"))
        result.render()
        self.assertFalse((self.root / ".claude/agents/sky-developer.md").exists())
        registry = result.registry()
        self.assertEqual(registry["active_roles"]["developer"], "sky:developer")
        self.assertEqual(registry["agents"]["sky:developer"]["status"], "active")
        self.assertNotIn("sky-developer", registry["agents"])

    def test_rendered_replacement_preserves_plugin_order_then_new_grant_order(self):
        self.body["roles"]["developer"]["base_tools"] = ["Read", "Edit", "Write"]
        self.body["skills"] = {"early": {"tools": ["Grep", "Glob"]},
                               "middle": {"tools": ["+kb"]},
                               "late": {"tools": ["Glob", "Grep"]}}
        self.body["roles"]["developer"]["skills"] = ["early", "middle", "late"]
        self.body["roles"]["reviewer"]["skills"] = ["middle"]
        for role in self.body["roles"]:
            self.agent(self.plugin, role, Policy.from_dict(self.body).tools_for(role))
        result = self.effective(patch_body={
            "tools": {"ExtraB": "repo.read", "ExtraA": "repo.read"},
            "skills": {"middle": {"tools_add": ["ExtraB", "ExtraA"]}},
            "roles": {"developer": {"skills_remove": ["early"], "tools_remove": ["Edit"]}}})
        expected = ("Read", "Write", "Grep", "Glob", "mcp__kb__search", "ExtraB", "ExtraA")
        self.assertEqual(result.tools_for("developer"), expected)
        result.render()
        self.assertEqual(read_agent(self.root / ".claude/agents/sky-developer.md").tools, expected)
        self.assertEqual(result.registry()["agents"]["sky-developer"]["tools"], list(expected))

    def test_owned_agent_is_deleted_when_skill_removal_becomes_redundant(self):
        self.effective(patch_body={"roles": {"developer": {"tools_remove": ["Read"]}}}).render()
        generated = self.root / ".claude/agents/sky-developer.md"
        self.assertTrue(generated.exists())
        self.body["skills"]["overlap"] = {"tools": ["Read"]}
        self.body["roles"]["developer"]["skills"].append("overlap")
        result = self.effective(patch_body={"roles": {"developer": {"skills_remove": ["overlap"]}}})
        result.render()
        self.assertFalse(generated.exists())
        self.assertEqual(result.registry()["active_roles"]["developer"], "sky:developer")

    def test_show_layers_and_lint_begin_with_effective_layers_notice(self):
        expected = f"effective policy: plugin {self.plugin / 'policy.yaml'} + project .sky/policy.yaml"
        for args in (("policy", "show", "--layers"), ("policy", "lint")):
            _, output = self.command(*args)
            self.assertEqual(output.splitlines()[0], expected)
        self.config({"managed": True, "org_plugin": "fixture-market/team"})
        _, output = self.command("policy", "show", "--layers")
        self.assertEqual(output.splitlines()[0], expected + " + org fixture-market/team")

    def test_unknown_removal_is_refused(self):
        for field, names in (("tools_remove", ["Unknown"]), ("skills_remove", ["Unknown"]),
                             ("may_remove", ["unknown"]), ("needs_human_remove", ["unknown"])):
            self.refuses({"roles": {"developer": {field: names}}}, "unknown")
        self.refuses({"skills": {"read": {"tools_remove": ["Unknown"]}}}, "unknown")
        for field in ("base_tools", "skills", "may", "needs_human"):
            self.refuses({"roles": {"developer": {field: []}}}, "forbidden patch keys")

    def test_added_role_still_obeys_read_only_tool_invariant(self):
        role = new_role()
        role["base_tools"].append("Edit")
        self.refuses({"roles": {"extra": role}}, "writer wearing its name")

    def test_missing_named_org_plugin_is_refused(self):
        self.config({"managed": True, "org_plugin": "missing"})
        with self.assertRaisesRegex(PolicyError, "org plugin missing is not installed"):
            self.resolved()

    def test_org_plugin_resolution_is_deterministic_and_disambiguates_marketplaces(self):
        newest = self.org.parent / "10.0.0"
        newest.mkdir()
        write_yaml(newest / "policy.yaml", {})
        self.assertEqual(project.org_root("team", self.cache), newest)
        second = self.cache / "other-market" / "team" / "1.0.0"
        second.mkdir(parents=True)
        write_yaml(second / "policy.yaml", {})
        with self.assertRaises(PolicyError) as caught:
            project.org_root("team", self.cache)
        self.assertIn("fixture-market/team, other-market/team", str(caught.exception))
        self.assertEqual(project.org_root("fixture-market/team", self.cache), newest)

    def test_outside_managed_project_preserves_single_policy_discovery(self):
        self.config({"managed": False})
        self.assertIsNone(self.resolved())
        with self.here():
            self.assertEqual(Policy.find(), self.plugin / "policy.yaml")
            policy = Policy.load()
            self.assertNotIn("layers", policy.__dict__)
        (self.root / ".sky" / "project.yaml").unlink()
        self.assertIsNone(self.resolved())

    def test_explicit_policy_and_environment_override_follow_decided_precedence(self):
        for kind in ("argument", "environment", "configured"):
            with self.subTest(kind=kind):
                context = patch.dict(os.environ, {"SKY_POLICY": str(self.plugin / "policy.yaml")}) if kind == "environment" else \
                    patch("sky.policy.CONFIG_POLICY", str(self.plugin / "policy.yaml")) if kind == "configured" else patch.dict(os.environ, {})
                with context:
                    argv = ["--policy", str(self.plugin / "policy.yaml")] if kind == "argument" else []
                    code, output = self.command(*argv, "policy", "show", "--layers")
                    self.assertEqual(code, 0, output)
                    self.assertEqual(output.count("explicit policy: layers ignored"), 1)
                    self.assertIn("single explicit or discovered policy", output)

    def test_malformed_managed_config_fails_closed(self):
        self.config({"managed": "true"})
        with self.assertRaisesRegex(PolicyError, "managed must be a boolean"):
            self.resolved()
        with self.here(), self.assertRaises(PolicyError):
            Policy.load()
        self.assertNotEqual(self.command("policy", "lint")[0], 0)

    def test_git_subdirectory_uses_its_worktree_root(self):
        sub = self.root / "src" / "nested"
        sub.mkdir(parents=True)
        self.assertEqual(project.git_root(sub), self.root)
        self.assertEqual(self.resolved(sub).root, self.root)

    def test_git_worktree_uses_its_own_root_and_project_config(self):
        self.git("add", ".sky/project.yaml")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        worktree = self.tmp / "worktree"
        self.git("worktree", "add", "--detach", "-q", str(worktree))
        try:
            self.assertEqual(project.git_root(worktree), worktree)
            self.assertEqual(self.resolved(worktree).root, worktree)
            (worktree / ".sky" / "project.yaml").unlink()
            self.assertIsNone(self.resolved(worktree))
            self.assertIsNotNone(self.resolved(self.root))
        finally:
            self.git("worktree", "remove", "--force", str(worktree))

    def test_project_config_schema_rejects_wrong_types_unknown_keys_and_escaping_paths(self):
        for spec in ({"managed": True, "extra": 1}, {"managed": True, "context": {"max_chars": True}},
                     {"managed": True, "context": {"max_chars": 0}}, {"managed": True, "org_plugin": "a/b/c"},
                     {"managed": True, "org_plugin": "market/.."},
                     {"managed": True, "sessions_dir": "../outside"}, {"managed": True, "sessions_dir": str(self.tmp)},
                     {"managed": True, "sessions_dir": "C:/outside"}):
            with self.subTest(spec=spec), self.assertRaises(PolicyError):
                project.validate_config(spec, self.root)
        self.assertEqual(project.validate_config({"managed": True}, self.root)["context"]["max_chars"], 40000)
        link = self.root / "escape"
        try:
            link.symlink_to(self.tmp, target_is_directory=True)
        except OSError:
            return  # Windows without symlink privilege: lexical escapes still tested.
        with self.assertRaises(PolicyError):
            project.validate_config({"managed": True, "sessions_dir": "escape/sessions"}, self.root)

    def test_project_config_schema_matches_published_schema(self):
        path = Path(__file__).resolve().parents[2] / "schemas" / "project.schema.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), project.schema())

    def test_routing_workflows_and_sessions_dir_are_validated_without_execution(self):
        # SH-075 now validates these declarations; merging must still not run them.
        routing = {"code": {"contains": ["implement"], "agent": "sky:developer"}}
        workflow = {"example": [{"id": "developer", "agent": "developer"}]}
        result = self.effective(patch_body={"routing": routing,
                                          "workflows": workflow, "sessions_dir": "cards"})
        self.assertEqual(result.body["routing"], routing)
        self.assertEqual(result.body["workflows"], workflow)
        self.assertEqual(result.body["sessions_dir"], "cards")
        self.assertFalse((self.root / "cards").exists())

    def test_show_layers_attributes_inherited_added_and_removed_grants(self):
        write_yaml(self.root / ".sky" / "policy.yaml", {
            "skills": {"extra": {"tools": ["Glob"]}},
            "roles": {"developer": {"skills_add": ["extra"], "tools_remove": ["mcp__kb__search"]}}})
        code, output = self.command("policy", "show", "--layers")
        self.assertEqual(code, 0, output)
        self.assertIn("roles.developer.skills.extra: project", output)
        self.assertIn("roles.reviewer.tools.Read: plugin", output)
        self.assertIn("removed.roles.developer.tools.mcp__kb__search: project", output)

    def test_effective_digest_covers_removal_ceiling_and_preserves_list_order(self):
        result = self.effective()
        digest = result.digest()
        reordered = dict(reversed(list(result.body.items())))
        result.body = reordered
        self.assertEqual(result.digest(), digest)
        result.revocations["developer"] = {"tools": {"Grep": "org"}, "skills": {}}
        self.assertNotEqual(result.digest(), digest)
        result.revocations.clear()
        result.body["roles"]["developer"]["base_tools"].reverse()
        self.assertNotEqual(result.digest(), digest)

    def test_render_narrowed_role_creates_project_identity_and_supersedes_plugin_identity(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        result.render()
        document = read_agent(self.root / ".claude" / "agents" / "sky-developer.md")
        self.assertEqual(document.name, "sky-developer")
        self.assertIn("VERDICT: APPROVED", document.text)
        registry = json.loads((self.root / ".sky" / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["agents"]["sky:developer"]["status"], "superseded")
        self.assertEqual(registry["active_roles"]["developer"], "sky-developer")
        self.assertIn(".claude/agents/sky-developer.md", registry["owned_files"])

    def test_render_added_project_role_creates_active_project_identity(self):
        self.agent(self.root / ".sky", "extra")
        result = self.effective(patch_body={"roles": {"extra": new_role()}})
        result.render()
        self.assertEqual(result.definition_for("extra")[1], "sky-extra")
        self.assertNotIn("sky:extra", result.registry()["agents"])

    def test_org_narrowing_uses_org_checked_replacement_identity(self):
        result = self.effective(org={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        with self.assertRaises(PolicyError):
            result.render()
        self.org_agents(result)
        result.render()
        self.assertEqual(result.registry()["active_roles"]["developer"], "team:developer")
        self.assertEqual(result.definition_for("developer")[0], self.org / "agents" / "developer.md")
        self.assertFalse((self.root / ".claude" / "agents").exists())

    def test_render_project_skill_copies_declared_source_body(self):
        source = self.root / ".sky" / "skills" / "extra" / "SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"---\nname: extra\n---\nFixture instructions\n")
        result = self.effective(patch_body={"skills": {"extra": {"tools": ["Read"]}}})
        result.render()
        destination = self.root / ".claude" / "skills" / "extra" / "SKILL.md"
        self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_collision_with_plugin_or_existing_project_agent_is_refused(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        helper = self.agent(self.plugin, "sky-developer")
        with self.assertRaisesRegex(PolicyError, "collision"):
            result.render()
        helper.unlink()
        self.agent(self.root / ".claude", "other")
        other = self.root / ".claude" / "agents" / "other.md"
        other.write_text(other.read_text(encoding="utf-8").replace("name: other", "name: sky-developer"), encoding="utf-8")
        with self.assertRaisesRegex(PolicyError, "collision"):
            result.render()
        self.assertFalse((self.root / ".sky" / "registry.json").exists())

    def test_render_missing_skill_source_or_template_refuses_before_any_write(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}},
                                          "skills": {"extra": {"tools": ["Read"]}}})
        with self.assertRaises(PolicyError):
            result.render()
        self.assertFalse((self.root / ".claude").exists())
        result = self.effective(patch_body={"roles": {"extra": new_role()}})
        with self.assertRaises(PolicyError):
            result.render()
        self.assertFalse((self.root / ".sky" / "registry.json").exists())

    def test_managed_lint_detects_effective_registry_and_rendered_file_drift(self):
        write_yaml(self.root / ".sky" / "policy.yaml", {"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        self.assertNotEqual(self.command("policy", "lint")[0], 0)
        self.assertEqual(self.command("policy", "render")[0], 0)
        self.assertEqual(self.command("policy", "lint")[0], 0)
        path = self.root / ".claude" / "agents" / "sky-developer.md"
        path.write_bytes(path.read_bytes() + b"edited\n")
        code, output = self.command("policy", "lint")
        self.assertNotEqual(code, 0)
        self.assertIn("owned file changed", output)

    def test_no_project_changes_writes_no_project_agents(self):
        self.effective().render()
        self.assertFalse((self.root / ".claude" / "agents").exists())
        self.assertTrue((self.root / ".sky" / "registry.json").exists())

    def test_managed_render_never_mutates_plugin_or_org_files(self):
        result = self.effective(org={"roles": {"reviewer": {"tools_remove": ["mcp__kb__search"]}}},
                                patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        self.org_agents(result)
        before = {p: p.read_bytes() for d in (self.plugin, self.org) for p in d.rglob("*") if p.is_file()}
        result.render()
        self.assertTrue(all(p.read_bytes() == contents for p, contents in before.items()))

    def test_render_is_idempotent_and_preserves_unowned_project_files(self):
        self.agent(self.root / ".claude", "local-extra")
        unrelated = self.root / ".claude" / "agents" / "local-extra.md"
        before = unrelated.read_bytes()
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        result.render()
        self.assertEqual(result.render(), [])
        self.assertEqual(unrelated.read_bytes(), before)
        generated = self.root / ".claude" / "agents" / "sky-developer.md"
        generated.write_bytes(generated.read_bytes() + b"manual edit")
        with self.assertRaisesRegex(PolicyError, "owned file changed"):
            result.render()

    def test_removing_a_project_override_deletes_only_unchanged_owned_files(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        result.render()
        path = self.root / ".claude" / "agents" / "sky-developer.md"
        narrowed = path.read_bytes()
        path.write_bytes(narrowed + b"manual edit")
        with self.assertRaisesRegex(PolicyError, "owned file changed"):
            self.effective().render()
        path.write_bytes(narrowed)
        self.effective().render()
        self.assertFalse(path.exists())
        self.assertEqual(self.effective().definition_for("developer")[0], self.plugin / "agents" / "developer.md")

    def test_effective_definition_lookup_never_falls_back_to_superseded_identity(self):
        result = self.effective(patch_body={"roles": {"developer": {"tools_remove": ["mcp__kb__search"]}}})
        result.render()
        path = self.root / ".claude" / "agents" / "sky-developer.md"
        self.assertEqual(check_definition(result, "developer"), path)
        path.unlink()
        with self.assertRaises(DefinitionError):
            check_definition(result, "developer")
        with self.assertRaisesRegex(launcher.Refused, "effective identity selection lands with SH-062"):
            launcher.hand_command("claude", "developer", self.root / "mcp.json", "fixture", result)


if __name__ == "__main__":
    unittest.main()
