"""One test per finding from the v1.0.0 review, each reproducing the defect.

The review was right on every count, and each of these was written by first
reproducing the reported behaviour and then fixing it — so a test here failing
means that exact defect has come back, not that something near it changed.

The finding numbers are the reviewer's.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import broker, guard, hosts, probes, setup  # noqa: E402
from sky.kbmap import KBMap, KBMapError, _as_kb  # noqa: E402
from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")

#: Host packages now REQUIRE a knowledge base — a config whose URL is the
#: literal `${SKY_KB_URL}` reaches nothing on Codex and Kimi, which do not
#: expand it, so `build` refuses rather than emit one that looks finished.
A_PROFILE = setup.Profile.from_dict({
    "name": "t", "mcp_url": "https://stub.invalid/mcp/", "tenant_code": "ABCD2345",
    "ontology": "o", "instance": "example-kb"})


HELPER = REPO / "plugin" / "bin" / "sky-headers"


class F1_ThePluginCarriesItsRuntime(unittest.TestCase):
    """A plugin-only install had skills and no `sky`, so nothing worked."""

    def test_the_runtime_is_in_the_plugin(self):
        self.assertTrue((REPO / "plugin" / "runtime" / "sky" / "cli.py").is_file())
        self.assertTrue(os.access(REPO / "plugin" / "bin" / "sky", os.X_OK))

    @unittest.skipIf(sys.platform == "win32", "executes plugin/bin/sky through its shebang and isolates "
                     "the home with HOME, which Windows ignores")
    def test_it_runs_with_an_empty_environment_and_no_home(self):
        """The reviewer's own acceptance: empty home, minimal PATH."""
        root = Path(tempfile.mkdtemp())
        out = subprocess.run([str(REPO / "plugin" / "bin" / "sky"), "setup", "doctor"],
                             capture_output=True, text=True, timeout=60,
                             env={"PATH": "/usr/bin:/bin", "HOME": str(root)})
        # It reports an unconfigured machine — which means it RAN.
        self.assertIn("run `sky setup init`", out.stdout)

    def test_the_copy_has_not_drifted_from_core(self):
        from sky import selftest
        self.assertTrue(selftest.check_vendored_runtime(REPO).passed)


class F2_TheGuardOnlyActsInsideARun(unittest.TestCase):
    """It denied `git push` in a person's own interactive session."""

    def tearDown(self):
        os.environ.pop("SKY_LAUNCHED", None)

    def test_an_ordinary_session_is_untouched(self):
        os.environ.pop("SKY_LAUNCHED", None)
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
        self.assertEqual(guard.decide(payload, POLICY).decision, "allow")

    def test_a_managed_run_still_refuses(self):
        os.environ["SKY_LAUNCHED"] = "1"
        payload = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
        self.assertEqual(guard.decide(payload, POLICY).decision, "deny")


class F3_TheBrokerIsConnected(unittest.TestCase):
    """It existed as functions nothing called, and `ship` asked the model."""

    def test_intent_and_ship_are_commands(self):
        from sky import cli
        parser = cli.build_parser()
        for argv in (["ship"], ["intent", "--kind", "push", "--summary", "s"]):
            with self.subTest(argv=argv[0]):
                self.assertTrue(parser.parse_args(argv).func)

    def test_a_hand_records_an_intent_and_ship_renders_it(self):
        root = Path(tempfile.mkdtemp())
        env = {**os.environ, "SKY_RUN_ID": "r1", "SKY_AGENT_ID": "nova"}
        made = subprocess.run(
            [sys.executable, "-m", "sky", "intent", "--kind", "push",
             "--summary", "push it", "--branch", "fix/abc",
             "--directory", str(root)],
            cwd=str(REPO / "core"), capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(made.returncode, 0, made.stderr)
        shown = subprocess.run(
            [sys.executable, "-m", "sky", "ship", "--directory", str(root)],
            cwd=str(REPO / "core"), capture_output=True, text=True, timeout=30)
        self.assertIn("git push origin fix/abc", shown.stdout)
        self.assertIn("has been run", shown.stdout)

    def test_the_ship_skill_calls_the_runtime_rather_than_composing(self):
        body = (REPO / "plugin" / "skills" / "ship" / "SKILL.md").read_text()
        self.assertIn("sky ship", body)
        self.assertIn(".sky/outbox/", body)       # SH-004: the hand never runs `sky`
        self.assertIn("You do not compose these commands", body)


class F4_AnArgumentThatBecomesAnOption(unittest.TestCase):
    """`--mirror` was a valid branch name and rendered `git push origin --mirror`."""

    def one(self, branch):
        return broker.accept({"kind": "push", "summary": "s", "branch": branch},
                             run_id="r", agent_id="a")

    def test_every_option_shaped_name_is_refused(self):
        for branch in ("--mirror", "--force", "-f", "--delete", "-", "--all"):
            with self.subTest(branch=branch):
                with self.assertRaises(broker.Refused) as caught:
                    broker.render(self.one(branch))
                self.assertIn("OPTION", str(caught.exception))

    def test_the_remote_is_checked_the_same_way(self):
        with self.assertRaises(broker.Refused):
            broker.render(broker.accept(
                {"kind": "push", "summary": "s", "branch": "ok", "remote": "--exec=sh"},
                run_id="r", agent_id="a"))

    def test_an_ordinary_branch_still_works(self):
        self.assertEqual(broker.render(self.one("fix/abc-1.2")).command,
                         "git push origin fix/abc-1.2")


class F5_TheIdentityNamesMatch(unittest.TestCase):
    """The launcher set SKY_AGENT; the stamp and ledger read SKY_AGENT_ID."""

    def test_the_launcher_sets_what_the_stamp_reads(self):
        from sky import launcher
        from sky.kbmap import KB
        os.environ["SKY_T"] = "t"
        kb = KB(name="k", purpose="", url="https://x/", tenant="T", ontology="o",
                privacy="work", pat_env="SKY_T")
        env = launcher.build_env(kb, run_id="r1", agent_id="a1", role="developer",
                                 task="t", directory=Path("/tmp/run1"))
        variables = dict(env.variables) if hasattr(env, "variables") else dict(env)
        self.assertEqual(variables["SKY_AGENT_ID"], "a1")
        self.assertEqual(variables["SKY_RUN_DIR"], str(Path("/tmp/run1")))

    def test_the_ledger_then_has_somewhere_to_write(self):
        root = Path(tempfile.mkdtemp())
        os.environ["SKY_RUN_DIR"] = str(root)
        os.environ["SKY_AGENT_ID"] = "nova"
        try:
            guard.record({"tool_name": "Bash", "tool_input": {"command": "ls"}},
                         guard.Verdict("allow"))
            line = json.loads((root / "tools.jsonl").read_text().strip())
        finally:
            os.environ.pop("SKY_RUN_DIR", None)
            os.environ.pop("SKY_AGENT_ID", None)
        self.assertEqual(line["agent_id"], "nova")


class F6_SetupDoesNotDamageWhatItFinds(unittest.TestCase):
    """It replaced an existing `kb`, dropped 600 to 644, and wrote before checking."""

    def world(self):
        root = Path(tempfile.mkdtemp())
        claude = root / "claude.json"
        claude.write_text(json.dumps(
            {"mcpServers": {"kb": {"type": "http", "url": "https://theirs/mcp"}}}))
        os.chmod(claude, 0o600)
        return root, claude

    def profile(self, **over):
        return setup.Profile.from_dict({
            "name": "team_kb", "mcp_url": "https://ours/mcp/",
            "tenant_code": "ABCD2345", "ontology": "o", "instance": "x", **over})

    def test_a_collision_is_refused_and_nothing_is_written(self):
        root, claude = self.world()
        with self.assertRaises(setup.SetupError) as caught:
            setup.init(self.profile(), "tok", config_dir=root / "cfg",
                       claude_json=claude, helper_source=HELPER)
        self.assertIn("not created by this tool", str(caught.exception))
        self.assertEqual(json.loads(claude.read_text())["mcpServers"]["kb"]["url"],
                         "https://theirs/mcp")
        self.assertFalse((root / "cfg" / "env").exists(), "a token was written")

    @unittest.skipIf(sys.platform == "win32", "Windows has no POSIX file modes; chmod 0600 cannot make a file private there")
    def test_the_file_mode_is_preserved(self):
        root, claude = self.world()
        setup.init(self.profile(), "tok", config_dir=root / "cfg",
                   claude_json=claude, helper_source=HELPER, replace_servers=True)
        self.assertEqual(oct(claude.stat().st_mode & 0o777), oct(0o600))

    def test_uninstall_restores_what_was_replaced(self):
        root, claude = self.world()
        setup.init(self.profile(), "tok", config_dir=root / "cfg",
                   claude_json=claude, helper_source=HELPER, replace_servers=True)
        setup.uninstall(config_dir=root / "cfg", claude_json=claude)
        self.assertEqual(json.loads(claude.read_text())["mcpServers"]["kb"]["url"],
                         "https://theirs/mcp")

    def test_an_invalid_profile_writes_nothing_at_all(self):
        root, claude = self.world()
        with self.assertRaises(setup.SetupError):
            setup.init(self.profile(privacy="personal"), "tok",
                       config_dir=root / "cfg", claude_json=claude,
                       helper_source=HELPER, replace_servers=True)
        self.assertFalse((root / "cfg" / "env").exists())
        self.assertFalse((root / "cfg" / "kb-map.json").exists())


class F7_SeveralKnowledgeBases(unittest.TestCase):
    """A task KB, the shared catalogue on the same host, and a second host."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.claude = self.root / "claude.json"
        for name in ("alpha", "beta"):
            (self.root / name).mkdir()

        def add(**body):
            setup.init(setup.Profile.from_dict(body), "tok",
                       config_dir=self.root / "cfg", claude_json=self.claude,
                       helper_source=HELPER)
        add(name="demo_kb", mcp_url="https://h/mcp/", tenant_code="DEMO0001",
            ontology="kb_sdlc", instance="qa", repos=[str(self.root / "alpha")])
        add(name="sky_kb", mcp_url="https://h/mcp/", tenant_code="DEMO0002",
            ontology="sky_skill", instance="qa", kind="catalogue", default=False)
        add(name="other_kb", mcp_url="https://other/mcp/", tenant_code="DEMO0003",
            ontology="o", instance="demo", default=False,
            repos=[str(self.root / "beta")])
        self.map = KBMap.load(self.root / "cfg" / "kb-map.json")

    def test_a_catalogue_may_not_own_a_directory(self):
        with self.assertRaises(KBMapError) as caught:
            _as_kb("cat", {"mcp_url": "https://x/", "tenant_code": "T",
                           "ontology": "o", "privacy": "work",
                           "kind": "catalogue", "repos": ["/tmp"]})
        self.assertIn("owns no repository", str(caught.exception))

    def test_a_profile_carries_the_repositories_it_owns(self):
        self.assertEqual(self.map.resolve(cwd=self.root / "alpha").name, "demo_kb")
        self.assertEqual(self.map.resolve(cwd=self.root / "beta").name, "other_kb")

    def test_a_second_task_kb_does_not_take_the_sessions_server(self):
        servers = setup.read_servers(self.claude)
        self.assertEqual(sorted(servers), ["catalogue", "kb"])
        self.assertEqual(servers["kb"]["url"], "https://h/mcp/")

    def test_the_catalogue_registers_under_its_own_name(self):
        self.assertEqual(setup.read_servers(self.claude)["catalogue"]["url"],
                         "https://h/mcp/")
        self.assertEqual(self.map.catalogue().name, "sky_kb")

    @unittest.skipIf(sys.platform == "win32", "executes the sky-headers helper through its shebang, "
                     "which Windows cannot")
    def test_two_tenants_on_one_address_are_not_ambiguous(self):
        """They share an instance token, so there is one right answer."""
        out = subprocess.run([str(self.root / "cfg" / "sky-headers")],
                             capture_output=True, text=True, timeout=20,
                             env={**os.environ,
                                  "SKY_CONFIG_DIR": str(self.root / "cfg"),
                                  "CLAUDE_CODE_MCP_SERVER_URL": "https://h/mcp/",
                                  "SKY_KB_PAT": ""})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Authorization", out.stdout)


class F8_HostPackagesCarryTheSkills(unittest.TestCase):
    def test_each_package_ships_every_skill(self):
        os.environ["SKY_PLUGIN_ROOT"] = str(REPO / "plugin")
        try:
            shipped = len(list((REPO / "plugin" / "skills").glob("*/SKILL.md")))
            for host in sorted(hosts.BUILDERS):
                with self.subTest(host=host):
                    files = hosts.build(host, POLICY, profile=A_PROFILE).files
                    count = len([f for f in files if f.endswith("SKILL.md")])
                    self.assertEqual(count, shipped)
        finally:
            os.environ.pop("SKY_PLUGIN_ROOT", None)

    def test_a_profile_fills_in_the_address_and_token_variable(self):
        profile = setup.Profile.from_dict({
            "name": "t", "mcp_url": "https://real/mcp/", "tenant_code": "T",
            "ontology": "o", "instance": "example-kb"})
        toml = [b for n, b in hosts.build("codex", POLICY, profile=profile).files.items()
                if n.endswith(".toml")][0]
        self.assertIn("https://real/mcp/", toml)
        self.assertIn("SKY_PAT_EXAMPLE_KB", toml)


class F9_ReadinessCountsWhatIsInstalled(unittest.TestCase):
    def test_the_counts_come_from_the_plugin_not_a_constant(self):
        os.environ["SKY_PLUGIN_ROOT"] = str(REPO / "plugin")
        try:
            skills, agents = probes._shipped_counts()
        finally:
            os.environ.pop("SKY_PLUGIN_ROOT", None)
        self.assertEqual(skills, len(list((REPO / "plugin" / "skills").glob("*/SKILL.md"))))
        self.assertEqual(agents, len(list((REPO / "plugin" / "agents").glob("*.md"))))

    def test_it_counts_the_sky_plugin_and_not_whatever_else_is_installed(self):
        """The first fix globbed `cache/*/*/*` and counted another product."""
        source = (REPO / "core" / "sky" / "probes.py").read_text()
        self.assertIn("plugins/cache/sky/sky", source)


class F10_PublishedSkillsCarryProvenance(unittest.TestCase):
    def test_the_publisher_records_owner_commit_and_checksum(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ps", REPO / "scripts" / "publish-skills.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        path = REPO / "plugin" / "skills" / "impact" / "SKILL.md"
        record = module.provenance(path, path.read_text(encoding="utf-8"))
        for key in ("skill_name", "owner", "version", "source_commit",
                    "checksum", "reproducible"):
            self.assertIn(key, record)
        self.assertTrue(record["checksum"].startswith("sha256:"))

    def test_the_ingest_call_passes_it(self):
        body = (REPO / "scripts" / "publish-skills.py").read_text()
        self.assertIn('"metadata": provenance(', body)


class F11_TheDocumentationMatchesTheProduct(unittest.TestCase):
    def test_the_readme_does_not_claim_ten_skills_or_pre_release(self):
        body = (REPO / "README.md").read_text()
        self.assertNotIn("not release-ready", body)
        self.assertNotIn("ten packaged skills", body)
        self.assertIn("twenty", body)

