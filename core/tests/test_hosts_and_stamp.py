"""Tests for the H5 leftovers and H6 — the stamp, the rules, the host packages.

The theme: a package or a document that overstates what its host can enforce is
worse than none, because somebody runs a build on it. Several tests below check
that the *limits* are stated, not only that the files exist.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import hosts, setup  # noqa: E402
from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")

#: Host packages now REQUIRE a knowledge base — a config whose URL is the
#: literal `${SKY_KB_URL}` reaches nothing on Codex and Kimi, which do not
#: expand it, so `build` refuses rather than emit one that looks finished.
A_PROFILE = setup.Profile.from_dict({
    "name": "t", "mcp_url": "https://stub.invalid/mcp/", "tenant_code": "ABCD2345",
    "ontology": "o", "instance": "example-kb"})


ADMIN = REPO / "admin" / "sky-admin"


def sky(*args, **env):
    return subprocess.run([sys.executable, "-m", "sky", *args],
                          cwd=str(REPO / "core"), capture_output=True, text=True,
                          timeout=30, env={**os.environ, **env})


class TheStamp(unittest.TestCase):
    """A stamp a model composed is a stamp a model can get wrong."""

    def test_inside_a_run_it_prints_five_fields(self):
        out = sky("stamp", "--json", SKY_AGENT_ID="nova", SKY_RUN_ID="run-1",
                  SKY_ROLE="developer", SKY_KB_NAME="team_kb", SKY_TASK="T-1")
        self.assertEqual(out.returncode, 0, out.stderr)
        body = json.loads(out.stdout)
        self.assertEqual(sorted(body), ["sky_agent", "sky_kb", "sky_role",
                                        "sky_run", "sky_task"])
        self.assertEqual(body["sky_agent"], "nova")

    def test_outside_a_run_it_refuses_rather_than_inventing_one(self):
        clean = {k: "" for k in ("SKY_AGENT_ID", "SKY_RUN_ID")}
        out = sky("stamp", "--json", **clean)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("not a run", out.stderr)
        # It still prints the empty shape, so a caller sees blanks rather than
        # a crash — but the exit code and stderr say not to use them.
        self.assertEqual(json.loads(out.stdout)["sky_agent"], "")

    def test_the_ingest_skill_requires_it(self):
        body = (REPO / "plugin" / "skills" / "ingest" / "SKILL.md").read_text()
        self.assertIn("sky stamp --json", body)
        self.assertIn("never compose them", body)


class TheRulesTravelWithThePlugin(unittest.TestCase):
    def test_both_documents_ship(self):
        for name in ("policy.md", "identity.md", "CONFIG.md"):
            self.assertTrue((REPO / "plugin" / name).is_file(), name)

    def test_policy_md_says_which_layer_is_actually_a_boundary(self):
        """The dangerous version of this system is one where prose reads like
        enforcement."""
        body = (REPO / "plugin" / "policy.md").read_text()
        self.assertIn("This is the boundary", body)
        self.assertIn("not a sandbox", body)

    def test_identity_md_separates_the_agent_from_the_person(self):
        body = (REPO / "plugin" / "identity.md").read_text()
        self.assertIn("declared", body)
        self.assertIn("they authenticate nothing", body)
        self.assertIn("Never write an approval", body)


class TheHostPackages(unittest.TestCase):
    def test_both_hosts_produce_parseable_toml(self):
        for host in sorted(hosts.BUILDERS):
            with self.subTest(host=host):
                package = hosts.build(host, POLICY, profile=A_PROFILE)
                toml = [b for n, b in package.files.items() if n.endswith(".toml")]
                self.assertTrue(toml, f"{host} ships no configuration")
                parsed = tomllib.loads(toml[0])
                self.assertIn("mcp_servers", parsed)
                self.assertIn("kb", parsed["mcp_servers"])

    def test_the_server_is_called_kb_so_the_tool_ids_match(self):
        """`mcp__kb__kb_search` is what the rules and skills say."""
        for host in sorted(hosts.BUILDERS):
            with self.subTest(host=host):
                package = hosts.build(host, POLICY, profile=A_PROFILE)
                toml = [b for n, b in package.files.items() if n.endswith(".toml")][0]
                self.assertIn("[mcp_servers.kb]", toml)

    def test_no_package_carries_a_token(self):
        """A variable NAME is fine — a value is not. The name is per instance
        (`SKY_PAT_EXAMPLE_KB`), so asserting one fixed spelling was testing the
        wrong thing."""
        for host in sorted(hosts.BUILDERS):
            package = hosts.build(host, POLICY, profile=A_PROFILE)
            for name, body in package.files.items():
                with self.subTest(host=host, file=name):
                    self.assertNotIn("Bearer ", body)
            toml = [b for n, b in package.files.items() if n.endswith(".toml")][0]
            self.assertIn("bearer_token_env_var", toml)
            self.assertIn("SKY_PAT_", toml)

    def test_each_package_states_what_its_host_cannot_enforce(self):
        """The half a generated file usually leaves out."""
        codex = hosts.build("codex", POLICY, profile=A_PROFILE).files["AGENTS.md"]
        self.assertIn("No named agent", hosts.__doc__)
        self.assertIn("prose", codex)
        kimi = hosts.build("kimi", POLICY, profile=A_PROFILE).files["RULES.md"]
        self.assertIn("cannot stop you editing a file", kimi)

    def test_kimi_is_offered_no_role(self):
        """SH-008: the launcher refuses every Kimi role, so the package must too."""
        _, roles = hosts.CAN_ENFORCE["kimi"]
        self.assertEqual(roles, ())
        kimi = hosts.build("kimi", POLICY, profile=A_PROFILE).files["RULES.md"]
        self.assertIn("none — no managed run on this host", kimi)

    def test_legacy_exports_and_native_roles_are_distinguished(self):
        """Read-only exported rules cannot claim the native developer boundary."""
        from sky import launcher
        readme = (REPO / "hosts" / "README.md").read_text()
        self.assertEqual(hosts.CAN_ENFORCE["codex"][1], ("reviewer",))
        self.assertEqual(launcher.HAND_ROLES["codex"], {"developer", "reviewer"})
        self.assertEqual(set(hosts.CAN_ENFORCE["kimi"][1]), launcher.HAND_ROLES["kimi"])
        self.assertIn("developer, reviewer in managed local-store projects", readme)
        self.assertIn("Legacy remote reviewer launches remain read-only", readme)
        package = hosts.build("codex", POLICY, profile=A_PROFILE).files["AGENTS.md"]
        self.assertIn("Roles you may be asked to run here: reviewer", package)
        self.assertIn("exported files do not install it", package)

    def test_codex_is_not_offered_developer_either(self):
        _, roles = hosts.CAN_ENFORCE["codex"]
        self.assertNotIn("developer", roles)

    def test_the_denied_nine_are_in_every_package(self):
        for host in sorted(hosts.BUILDERS):
            body = "".join(hosts.build(host, POLICY, profile=A_PROFILE).files.values())
            with self.subTest(host=host):
                for action in ("pr.merge", "shell.free", "permission.change"):
                    self.assertIn(action, body)

    def test_claude_is_refused_with_the_reason(self):
        with self.assertRaises(hosts.HostError) as caught:
            hosts.build("claude", POLICY, profile=A_PROFILE)
        self.assertIn("plugin", str(caught.exception))

    def test_an_unknown_host_lists_the_ones_it_has(self):
        with self.assertRaises(hosts.HostError) as caught:
            hosts.build("emacs", POLICY, profile=A_PROFILE)
        self.assertIn("codex", str(caught.exception))

    def test_writing_over_a_file_that_is_not_ours_is_refused_before_anything_lands(self):
        """`~/.codex/AGENTS.md` is the file a person already has, and the first
        version replaced it silently. Same rule as the launcher: not ours, not
        replaced — and refused BEFORE anything else is written, so the
        directory is exactly as it was."""
        root = Path(tempfile.mkdtemp())
        (root / "AGENTS.md").write_text("# my own rules\n")
        with self.assertRaises(hosts.HostError) as caught:
            hosts.build("codex", POLICY, profile=A_PROFILE).write(root)
        self.assertIn("AGENTS.md", str(caught.exception))
        self.assertIn("not ours", str(caught.exception))
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["AGENTS.md"])
        self.assertEqual((root / "AGENTS.md").read_text(), "# my own rules\n")

    def test_writing_over_its_own_earlier_output_is_allowed(self):
        root = Path(tempfile.mkdtemp())
        package = hosts.build("codex", POLICY, profile=A_PROFILE)
        first = package.write(root)
        second = package.write(root)          # a re-run, e.g. after an update
        self.assertEqual(len(first), len(second))
        self.assertTrue((root / hosts.MANIFEST).is_file())

    def test_writing_a_package_puts_the_rules_and_the_skills_down(self):
        """The rules AND the procedures. Shipping the pointer without the
        procedure was the review's finding 8."""
        root = Path(tempfile.mkdtemp())
        written = hosts.build("codex", POLICY, profile=A_PROFILE).write(root)
        names = [p.name for p in written]
        self.assertIn("AGENTS.md", names)
        self.assertIn("sky.config.toml", names)
        self.assertGreater(names.count("SKILL.md"), 10)
        self.assertTrue((root / "skills" / "CONFIG.md").is_file())


class TheAdminHandoff(unittest.TestCase):
    """What an administrator sends, and what it must never contain."""

    def make(self, out: Path, *extra):
        return subprocess.run(
            [sys.executable, str(ADMIN), "profile",
             "--url", "https://example.invalid/mcp/", "--tenant", "ABCD2345",
             "--ontology", "kb_sdlc", "--instance", "example-kb",
             "--out", str(out), *extra],
            capture_output=True, text=True, timeout=30)

    def test_the_profile_round_trips_into_setup(self):
        out = Path(tempfile.mkdtemp()) / "team.json"
        self.assertEqual(self.make(out).returncode, 0)
        profile = setup.Profile.load(out)
        self.assertEqual(profile.tenant, "ABCD2345")
        self.assertEqual(setup.token_variable(profile.instance), "SKY_PAT_EXAMPLE_KB")

    def test_it_carries_no_token_and_no_person(self):
        out = Path(tempfile.mkdtemp()) / "team.json"
        self.make(out)
        body = json.loads(out.read_text())
        for key in body:
            self.assertNotIn("pat", key.lower())
            self.assertNotIn("token", key.lower())
            self.assertNotIn("email", key.lower())

    def test_it_tells_the_person_to_mint_their_own(self):
        """The one instruction that keeps the audit trail true."""
        out = Path(tempfile.mkdtemp()) / "team.json"
        self.make(out)
        note = json.loads(out.read_text())["_note"]
        self.assertIn("YOUR OWN token", note)
        self.assertIn("Never use somebody else's", note)

    def test_the_admin_tool_refuses_a_token_on_the_command_line(self):
        source = ADMIN.read_text()
        self.assertNotIn("--token", source)
        self.assertIn("getpass", source)
        self.assertIn("argv is in the process", source)


class TheCommandIsWired(unittest.TestCase):
    def a_profile_file(self):
        path = Path(tempfile.mkdtemp()) / "p.json"
        path.write_text(json.dumps({
            "name": "t", "mcp_url": "https://stub.invalid/mcp/",
            "tenant_code": "ABCD2345", "ontology": "o", "instance": "example-kb"}))
        return str(path)

    def test_sky_host_prints_a_package(self):
        out = sky("host", "codex", "--profile", self.a_profile_file(),
                  SKY_POLICY=str(REPO / "plugin" / "policy.yaml"))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("[mcp_servers.kb]", out.stdout)

    def test_sky_host_writes_one(self):
        root = Path(tempfile.mkdtemp())
        out = sky("host", "kimi", "--into", str(root),
                  "--profile", self.a_profile_file(),
                  SKY_POLICY=str(REPO / "plugin" / "policy.yaml"))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((root / "config.toml").is_file())
        self.assertIn("enforces nothing beyond the prose", out.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
