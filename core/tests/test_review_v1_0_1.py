"""One test per finding from the v1.0.1 review, each reproducing the defect.

Two of these are about my own weak tests rather than the code: finding 2 said
the regression test for "the plugin carries its runtime" exercised
`plugin/bin/sky` by its full path, which is not what any skill types. The test
below runs the **bare** command, which is the thing that was actually broken.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import broker, hosts, launcher, probes, setup  # noqa: E402
from sky.kbmap import KBMap, _as_kb  # noqa: E402
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


class G1_ASummaryCannotSmuggleInACommand(unittest.TestCase):
    """A newline in a model-written summary put an unapproved
    `git push --force` above the approved line, in text whose entire purpose is
    "these are the commands"."""

    def test_a_multi_line_summary_is_refused(self):
        for summary in ("push it\ngit push --force origin main",
                        "push it\rrm -rf /"):
            with self.subTest(summary=summary):
                sealed = broker.accept(
                    {"kind": "push", "summary": summary, "branch": "fix/a"},
                    run_id="r", agent_id="a")
                with self.assertRaises(broker.Refused) as caught:
                    broker.render(sealed)
                self.assertIn("more than one line", str(caught.exception))

    def test_the_only_uncommented_line_is_the_validated_command(self):
        sealed = broker.accept({"kind": "push", "summary": "push it",
                                "branch": "fix/a"}, run_id="r", agent_id="a")
        rendered = str(broker.render(sealed))
        live = [l for l in rendered.splitlines() if l and not l.startswith("#")]
        self.assertEqual(live, ["git push origin fix/a"])

    def test_a_body_is_commented_not_merely_fenced(self):
        """Fencing was not enough. A fence is a label; the lines inside it are
        still commands when somebody selects the block and pastes it."""
        sealed = broker.accept(
            {"kind": "ticket.comment", "summary": "say it", "issue_key": "ABC-1",
             "body": "line one\ngit push --force origin main"},
            run_id="r", agent_id="a")
        rendered = str(broker.render(sealed))
        live = [l for l in rendered.splitlines() if l and not l.startswith("#")]
        self.assertEqual(live, [], f"these lines would run: {live}")


@unittest.skipIf(sys.platform == "win32", "executes plugin/bin/sky and the installed launcher through "
                 "their shebangs, with HOME (ignored on Windows) and a POSIX PATH")
class G2_TheBareCommandWorks(unittest.TestCase):
    """`plugin/bin/sky` worked; `sky` did not, and every skill types `sky`."""

    def install(self):
        root = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "plugin", root / "plugin")
        profile = root / "team.json"
        profile.write_text(json.dumps({
            "name": "team_kb", "mcp_url": "https://h/mcp/",
            "tenant_code": "ABCD2345", "ontology": "o", "instance": "qa"}))
        out = subprocess.run(
            [str(root / "plugin" / "bin" / "sky"), "setup", "init",
             "--profile", str(profile), "--token-env", "T", "--yes"],
            capture_output=True, text=True, timeout=90,
            env={"PATH": "/usr/bin:/bin", "HOME": str(root / "home"), "T": "tok"})
        self.assertEqual(out.returncode, 0, out.stderr)
        return root

    def test_bare_sky_works_after_a_plugin_only_install(self):
        root = self.install()
        out = subprocess.run(
            ["sh", "-c", "sky setup doctor"], capture_output=True, text=True,
            timeout=90, env={"PATH": f"{root}/home/.local/bin:/usr/bin:/bin",
                             "HOME": str(root / "home")})
        self.assertIn("PASS", out.stdout, out.stdout + out.stderr)

    def test_and_it_says_so_when_that_directory_is_not_on_path(self):
        """Installed somewhere PATH does not look is the same failure again."""
        root = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "plugin", root / "plugin")
        profile = root / "team.json"
        profile.write_text(json.dumps({
            "name": "t", "mcp_url": "https://h/mcp/", "tenant_code": "ABCD2345",
            "ontology": "o", "instance": "qa"}))
        out = subprocess.run(
            [str(root / "plugin" / "bin" / "sky"), "setup", "init",
             "--profile", str(profile), "--token-env", "T", "--yes"],
            capture_output=True, text=True, timeout=90,
            env={"PATH": "/usr/bin:/bin", "HOME": str(root / "home"), "T": "tok"})
        self.assertIn("NOT on your PATH", out.stdout)
        self.assertIn("export PATH=", out.stdout)


class G4_TheOtherHostsAreConnected(unittest.TestCase):
    def a_config(self):
        path = Path(tempfile.mkdtemp()) / "mcp.json"
        path.write_text(json.dumps(
            {"mcpServers": {"kb": {"type": "http", "url": "https://real/mcp/"}}}))
        return path

    def test_a_managed_codex_run_is_given_its_knowledge_base(self):
        cmd = launcher.hand_command("codex", "reviewer", self.a_config(), "x",
                                    POLICY)
        joined = " ".join(cmd)
        self.assertIn("mcp_servers.kb.url=https://real/mcp/", joined)
        self.assertIn("bearer_token_env_var=SKY_KB_PAT", joined)

    def test_a_codex_run_that_cannot_be_given_one_is_refused(self):
        """Rather than silently reading the person's own configuration."""
        with self.assertRaises(launcher.Refused):
            launcher.hand_command("codex", "reviewer",
                                  Path("/nonexistent/mcp.json"), "x", POLICY)

    def test_kimi_is_refused_a_managed_run_and_the_reason_is_recorded(self):
        with self.assertRaises(launcher.Refused):
            launcher.hand_command("kimi", "reviewer", self.a_config(), "x", POLICY)
        self.assertEqual(launcher.HAND_ROLES["kimi"], frozenset())

    def test_each_package_ships_a_wrapper_that_loads_the_token(self):
        for host in sorted(hosts.BUILDERS):
            with self.subTest(host=host):
                package = hosts.build(host, POLICY, profile=A_PROFILE)
                wrapper = [b for n, b in package.files.items()
                           if n.startswith("bin/")][0]
                self.assertIn("config/sky}/env", wrapper)
                self.assertIn("SKY_KB_PAT=", wrapper)

    def test_the_wrapper_is_valid_shell_and_executable(self):
        root = Path(tempfile.mkdtemp())
        hosts.build("codex", POLICY, profile=A_PROFILE).write(root)
        path = root / "bin" / "sky-codex"
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(subprocess.run(["sh", "-n", str(path)],
                                        capture_output=True).returncode, 0)

    def test_no_claude_only_path_travels_into_another_hosts_skills(self):
        for host in sorted(hosts.BUILDERS):
            for name, body in hosts.build(host, POLICY, profile=A_PROFILE).files.items():
                with self.subTest(host=host, file=name):
                    self.assertNotIn("CLAUDE_PLUGIN_ROOT", body)


class G5_TheCollisionRecoveryIsReachable(unittest.TestCase):
    """The error named an option the command did not define."""

    def test_the_option_exists_on_the_real_command_line(self):
        from sky import cli
        parsed = cli.build_parser().parse_args(
            ["setup", "init", "--profile", "p.json", "--replace-servers"])
        self.assertTrue(parsed.replace_servers)

    def test_it_is_accepted_end_to_end(self):
        out = subprocess.run(
            [sys.executable, "-m", "sky", "setup", "init", "--profile",
             "/nonexistent.json", "--replace-servers", "--yes"],
            cwd=str(REPO / "core"), capture_output=True, text=True, timeout=30)
        self.assertNotIn("unrecognized arguments", out.stderr)


class G6_SetupCommitsOrRollsBack(unittest.TestCase):
    def test_uninstall_leaves_a_server_the_person_has_since_changed(self):
        root = Path(tempfile.mkdtemp())
        claude = root / "claude.json"
        setup.init(setup.Profile.from_dict({
            "name": "t", "mcp_url": "https://ours/mcp/", "tenant_code": "ABCD2345",
            "ontology": "o", "instance": "x"}), "tok",
            config_dir=root / "cfg", claude_json=claude, helper_source=HELPER)
        # The person re-points it afterwards. It is theirs now.
        body = json.loads(claude.read_text())
        body["mcpServers"]["kb"] = {"type": "http", "url": "https://mine/mcp"}
        claude.write_text(json.dumps(body))
        setup.uninstall(config_dir=root / "cfg", claude_json=claude)
        self.assertEqual(json.loads(claude.read_text())["mcpServers"]["kb"]["url"],
                         "https://mine/mcp")

    def test_the_originals_are_kept_so_a_failure_can_be_undone(self):
        source = (REPO / "core" / "sky" / "setup.py").read_text()
        self.assertIn("previous = {", source)
        self.assertIn("nothing was changed", source)


class G7_MultipleKnowledgeBases(unittest.TestCase):
    def test_a_hint_never_selects_the_catalogue(self):
        kbs = KBMap({
            "t": _as_kb("t", {"mcp_url": "https://a/", "tenant_code": "T",
                              "ontology": "o", "privacy": "work",
                              "default": True, "hints": ["x"]}),
            "c": _as_kb("c", {"mcp_url": "https://b/", "tenant_code": "C",
                              "ontology": "o", "privacy": "work",
                              "kind": "catalogue", "hints": ["skill"]})})
        self.assertIsNone(kbs.by_hint("find a skill for migrations"))

    def test_the_admin_profile_can_express_what_the_map_needs(self):
        out = subprocess.run(
            [sys.executable, str(REPO / "admin" / "sky-admin"), "profile",
             "--url", "https://h/mcp/", "--tenant", "DEMO0002",
             "--ontology", "sky_skill", "--name", "sky_kb",
             "--kind", "catalogue"],
            capture_output=True, text=True, timeout=30)
        body = json.loads(out.stdout)
        self.assertEqual(body["kind"], "catalogue")
        self.assertFalse(body["default"])

    def test_a_profile_can_name_the_repositories_it_owns(self):
        out = subprocess.run(
            [sys.executable, str(REPO / "admin" / "sky-admin"), "profile",
             "--url", "https://h/mcp/", "--tenant", "ABCD2345", "--ontology", "o",
             "--repo", "~/code/a", "--repo", "~/code/b"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(out.stdout)["repos"], ["~/code/a", "~/code/b"])

    def test_switching_the_session_to_another_host_is_implemented(self):
        root = Path(tempfile.mkdtemp())
        claude = root / "claude.json"

        def add(**body):
            setup.init(setup.Profile.from_dict(body), "tok",
                       config_dir=root / "cfg", claude_json=claude,
                       helper_source=HELPER)
        add(name="demo_kb", mcp_url="https://h/mcp/", tenant_code="DEMO0001",
            ontology="o", instance="qa")
        add(name="other_kb", mcp_url="https://other/mcp/", tenant_code="DEMO0003",
            ontology="o", instance="demo", default=False)
        setup.use("other_kb", config_dir=root / "cfg", claude_json=claude)
        self.assertEqual(setup.read_servers(claude)["kb"]["url"],
                         "https://other/mcp/")

    def test_and_refuses_to_switch_to_the_catalogue(self):
        root = Path(tempfile.mkdtemp())
        claude = root / "claude.json"
        for body in ({"name": "t", "mcp_url": "https://h/mcp/",
                      "tenant_code": "ABCD2345", "ontology": "o", "instance": "q"},
                     {"name": "cat", "mcp_url": "https://h/mcp/",
                      "tenant_code": "DEMO0002", "ontology": "sky_skill",
                      "instance": "q", "kind": "catalogue", "default": False}):
            setup.init(setup.Profile.from_dict(body), "tok",
                       config_dir=root / "cfg", claude_json=claude,
                       helper_source=HELPER)
        with self.assertRaises(setup.SetupError):
            setup.use("cat", config_dir=root / "cfg", claude_json=claude)


class G8_AnIntentNeverOverwritesAnother(unittest.TestCase):
    def test_a_gap_in_the_numbering_does_not_clobber(self):
        root = Path(tempfile.mkdtemp())
        (root / "001-push.json").write_text("{}")
        (root / "003-push.json").write_text("{}")
        out = subprocess.run(
            [sys.executable, "-m", "sky", "intent", "--kind", "push",
             "--summary", "s", "--branch", "fix/a", "--directory", str(root)],
            cwd=str(REPO / "core"), capture_output=True, text=True, timeout=30,
            env={**os.environ, "SKY_RUN_ID": "r", "SKY_AGENT_ID": "a"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(len(list(root.glob("*.json"))), 3)
        self.assertEqual((root / "003-push.json").read_text(), "{}")


class G9_TheDocumentationMatches(unittest.TestCase):
    def test_the_readme_no_longer_says_ten_skills(self):
        body = (REPO / "README.md").read_text()
        self.assertNotIn("ten SDLC skills", body)
        self.assertIn("twenty SDLC skills", body)

