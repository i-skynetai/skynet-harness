"""Tests for the config contract — `sky setup` (H2).

The half that matters most here is not "does it write the files". It is:

* the token never appears in anything this prints,
* it never writes over a part of the user's file it was not asked to,
* and the helper it installs obeys the host's contract exactly, driven the way
  the host drives it — through a shell, reading only environment variables.

The token used throughout is `TOKEN`, and several tests assert that string is
absent from rendered output. That is the point of using one value everywhere.
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

from sky import setup  # noqa: E402
from sky.kbmap import KBMap  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SHIPPED_HELPER = REPO / "plugin" / "bin" / "sky-headers"

TOKEN = "this-exact-string-is-the-secret"

PROFILE = {
    "name": "team_kb",
    "mcp_url": "https://example.invalid/mcp/",
    "tenant_code": "ABCD2345",
    "ontology": "kb_sdlc",
    "instance": "example-kb",
    "privacy": "work",
    "code_url": "https://example.invalid/code/mcp/",
}


def a_home():
    root = Path(tempfile.mkdtemp())
    (root / "cfg").mkdir()
    return root


def run_init(root: Path, profile: dict | None = None, **kw):
    p = setup.Profile.from_dict(profile or PROFILE)
    return p, setup.init(p, TOKEN, config_dir=root / "cfg",
                         claude_json=root / "claude.json",
                         helper_source=SHIPPED_HELPER, **kw)


class TheTokenIsNeverShown(unittest.TestCase):
    """Every path that renders text, checked against the one secret string."""

    def test_the_plan_describes_the_token_without_holding_it(self):
        root = a_home()
        rendered = "\n".join(str(c) for c in setup.plan(
            setup.Profile.from_dict(PROFILE), config_dir=root / "cfg",
            claude_json=root / "claude.json"))
        self.assertNotIn(TOKEN, rendered)
        self.assertIn("SKY_PAT_EXAMPLE_KB", rendered)

    def test_doctor_names_the_variable_and_not_the_value(self):
        root = a_home()
        run_init(root)
        rendered = "\n".join(str(f) for f in setup.doctor(
            config_dir=root / "cfg", claude_json=root / "claude.json"))
        self.assertNotIn(TOKEN, rendered)
        self.assertIn("SKY_PAT_EXAMPLE_KB", rendered)

    def test_the_map_written_holds_the_variable_name_only(self):
        root = a_home()
        run_init(root)
        body = (root / "cfg" / "kb-map.json").read_text()
        self.assertNotIn(TOKEN, body)
        self.assertIn("SKY_PAT_EXAMPLE_KB", body)

    def test_the_host_server_file_holds_no_token_either(self):
        root = a_home()
        run_init(root)
        self.assertNotIn(TOKEN, (root / "claude.json").read_text())


class TheTokenFile(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "Windows has no POSIX file modes; chmod 0600 cannot make a file private there")
    def test_it_is_written_at_600(self):
        root = a_home()
        run_init(root)
        mode = (root / "cfg" / "env").stat().st_mode & 0o777
        self.assertEqual(oct(mode), oct(0o600))

    def test_doctor_reports_a_loose_mode_rather_than_fixing_it_quietly(self):
        root = a_home()
        run_init(root)
        os.chmod(root / "cfg" / "env", 0o644)
        findings = setup.doctor(config_dir=root / "cfg",
                                claude_json=root / "claude.json")
        bad = [f for f in findings if not f.ok and "permission" in f.name]
        self.assertTrue(bad, [str(f) for f in findings])
        self.assertIn("should be 600", bad[0].detail)

    def test_a_line_that_is_not_key_value_is_refused_with_its_number(self):
        path = a_home() / "env"
        path.write_text("GOOD=1\nnonsense\n")
        with self.assertRaises(setup.SetupError) as caught:
            setup.read_env(path)
        self.assertIn(":2", str(caught.exception))

    def test_a_lower_case_name_is_refused(self):
        path = a_home() / "env"
        path.write_text("token=x\n")
        with self.assertRaises(setup.SetupError):
            setup.read_env(path)

    def test_a_token_is_not_interpreted(self):
        """Values are opaque. A shell parser would eat `$` and quotes."""
        path = a_home() / "env"
        setup.write_env({"SKY_PAT_X": "a$b\"c'd e"}, path)
        self.assertEqual(setup.read_env(path)["SKY_PAT_X"], "a$b\"c'd e")

    def test_a_missing_file_is_empty_not_an_error(self):
        self.assertEqual(setup.read_env(a_home() / "nothing"), {})


class Rotation(unittest.TestCase):
    def test_it_replaces_one_variable_and_keeps_the_rest(self):
        root = a_home()
        run_init(root)
        values = setup.read_env(root / "cfg" / "env")
        values["SKY_PAT_OTHER"] = "another"
        setup.write_env(values, root / "cfg" / "env")
        setup.rotate("example-kb", "fresh", config_dir=root / "cfg")
        after = setup.read_env(root / "cfg" / "env")
        self.assertEqual(after["SKY_PAT_EXAMPLE_KB"], "fresh")
        self.assertEqual(after["SKY_PAT_OTHER"], "another")

    def test_an_unknown_instance_lists_the_ones_it_has(self):
        root = a_home()
        run_init(root)
        with self.assertRaises(setup.SetupError) as caught:
            setup.rotate("nowhere", "x", config_dir=root / "cfg")
        self.assertIn("SKY_PAT_EXAMPLE_KB", str(caught.exception))

    def test_rotating_to_the_same_value_is_refused(self):
        """Almost always a paste of the old token, and it would report success."""
        root = a_home()
        run_init(root)
        with self.assertRaises(setup.SetupError) as caught:
            setup.rotate("example-kb", TOKEN, config_dir=root / "cfg")
        self.assertIn("already stored", str(caught.exception))

    def test_an_empty_token_changes_nothing(self):
        root = a_home()
        run_init(root)
        with self.assertRaises(setup.SetupError):
            setup.rotate("example-kb", "   ", config_dir=root / "cfg")
        self.assertEqual(setup.read_env(root / "cfg" / "env")["SKY_PAT_EXAMPLE_KB"],
                         TOKEN)


class TheUsersOwnFile(unittest.TestCase):
    """`~/.claude.json` holds every other MCP server the person has."""

    def test_other_servers_survive_init(self):
        root = a_home()
        (root / "claude.json").write_text(json.dumps(
            {"mcpServers": {"their_own": {"type": "http", "url": "https://x/"}},
             "somethingElse": 42}))
        run_init(root)
        body = json.loads((root / "claude.json").read_text())
        self.assertIn("their_own", body["mcpServers"])
        self.assertEqual(body["somethingElse"], 42)
        self.assertEqual(sorted(body["mcpServers"]), ["code", "kb", "their_own"])

    def test_uninstall_removes_only_what_the_manifest_names(self):
        root = a_home()
        (root / "claude.json").write_text(json.dumps(
            {"mcpServers": {"their_own": {"type": "http", "url": "https://x/"}}}))
        run_init(root)
        setup.uninstall(config_dir=root / "cfg", claude_json=root / "claude.json")
        body = json.loads((root / "claude.json").read_text())
        self.assertEqual(sorted(body["mcpServers"]), ["their_own"])

    def test_uninstall_keeps_the_token_unless_asked(self):
        root = a_home()
        run_init(root)
        setup.uninstall(config_dir=root / "cfg", claude_json=root / "claude.json")
        self.assertTrue((root / "cfg" / "env").exists())
        self.assertFalse((root / "cfg" / "kb-map.json").exists())

    def test_uninstall_without_a_manifest_refuses_rather_than_guessing(self):
        root = a_home()
        with self.assertRaises(setup.SetupError) as caught:
            setup.uninstall(config_dir=root / "cfg",
                            claude_json=root / "claude.json")
        self.assertIn("no record", str(caught.exception))

    def test_a_broken_host_file_is_reported_not_rewritten(self):
        root = a_home()
        (root / "claude.json").write_text("{not json")
        with self.assertRaises(setup.SetupError) as caught:
            run_init(root)
        self.assertIn("your own file", str(caught.exception))
        self.assertEqual((root / "claude.json").read_text(), "{not json")


class TheServerNames(unittest.TestCase):
    def test_they_are_kb_and_code_because_the_allowlists_say_so(self):
        """`mcp__kb__kb_search` is what every agent file names.

        A server called anything else produces tool ids no allowlist mentions,
        and the agent then has no knowledge base — silently. This project has
        paid for that failure twice.
        """
        names = setup.server_names(setup.Profile.from_dict(PROFILE))
        self.assertEqual(sorted(names), ["code", "kb"])

    def test_a_profile_with_no_code_endpoint_registers_only_the_kb(self):
        thin = {k: v for k, v in PROFILE.items() if k != "code_url"}
        self.assertEqual(sorted(setup.server_names(
            setup.Profile.from_dict(thin))), ["kb"])

    def test_the_registered_server_points_at_the_installed_helper(self):
        root = a_home()
        run_init(root)
        server = json.loads((root / "claude.json").read_text())["mcpServers"]["kb"]
        self.assertEqual(server["headersHelper"],
                         str(root / "cfg" / "sky-headers"))
        self.assertEqual(server["type"], "http")

    def test_the_helper_is_copied_out_of_the_versioned_cache(self):
        """A path with a version number in it dangles at the next update."""
        root = a_home()
        run_init(root)
        installed = root / "cfg" / "sky-headers"
        self.assertTrue(installed.is_file())
        self.assertTrue(os.access(installed, os.X_OK))
        self.assertEqual(installed.read_text(), SHIPPED_HELPER.read_text())


class TheProfile(unittest.TestCase):
    def test_the_three_fields_are_required_and_named_when_missing(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.Profile.from_dict({"mcp_url": "https://x/"})
        self.assertIn("tenant_code", str(caught.exception))
        self.assertIn("ontology", str(caught.exception))

    def test_an_unknown_privacy_class_is_refused(self):
        with self.assertRaises(setup.SetupError):
            setup.Profile.from_dict({**PROFILE, "privacy": "secret"})

    def test_the_instance_falls_back_to_the_host_name(self):
        thin = {k: v for k, v in PROFILE.items() if k != "instance"}
        thin["mcp_url"] = "https://example-kb.example.invalid/mcp/"
        self.assertEqual(setup.Profile.from_dict(thin).instance, "example-kb")

    def test_the_variable_name_is_built_from_the_instance(self):
        self.assertEqual(setup.token_variable("example-kb"), "SKY_PAT_EXAMPLE_KB")
        self.assertEqual(setup.token_variable("demo.11"), "SKY_PAT_DEMO_11")
        with self.assertRaises(setup.SetupError):
            setup.token_variable("---")


class WhatInitWrites(unittest.TestCase):
    def test_the_map_it_writes_is_one_the_runtime_can_load(self):
        root = a_home()
        run_init(root)
        kbs = KBMap.load(root / "cfg" / "kb-map.json")
        self.assertEqual(kbs.names(), ["team_kb"])
        self.assertEqual(kbs.get("team_kb").tenant, "ABCD2345")

    def test_a_profile_the_runtime_would_reject_fails_init_loudly(self):
        """`personal` off this machine is refused by the map's own rules."""
        root = a_home()
        with self.assertRaises(setup.SetupError) as caught:
            run_init(root, {**PROFILE, "privacy": "personal"})
        self.assertIn("will load", str(caught.exception))

    def test_a_second_default_replaces_the_first(self):
        root = a_home()
        run_init(root)
        run_init(root, {**PROFILE, "name": "other_kb", "tenant_code": "WXYZ2345"})
        body = json.loads((root / "cfg" / "kb-map.json").read_text())
        defaults = [n for n, e in body.items() if e.get("default")]
        self.assertEqual(defaults, ["other_kb"])

    def test_no_register_writes_the_config_and_touches_no_host_file(self):
        root = a_home()
        run_init(root, register=False)
        self.assertTrue((root / "cfg" / "kb-map.json").exists())
        self.assertFalse((root / "claude.json").exists())

    def test_an_empty_token_writes_nothing_at_all(self):
        root = a_home()
        profile = setup.Profile.from_dict(PROFILE)
        with self.assertRaises(setup.SetupError):
            setup.init(profile, "  ", config_dir=root / "cfg",
                       claude_json=root / "claude.json")
        self.assertFalse((root / "cfg" / "env").exists())


@unittest.skipIf(sys.platform == "win32", "runs the #!/usr/bin/env python3 helper through the shell, "
                 "as the host does on macOS; how the host runs it on Windows is unmeasured")
class TheHelperObeysTheHostsContract(unittest.TestCase):
    """Driven the way the host drives it: a shell, and environment variables.

    Measured contract (Claude Code 2.1.152): run through a shell, 10s timeout,
    `CLAUDE_CODE_MCP_SERVER_NAME` and `CLAUDE_CODE_MCP_SERVER_URL` added, and
    it must exit 0 having printed a JSON object whose values are all strings.
    """

    def drive(self, root: Path, url: str = PROFILE["mcp_url"], **extra):
        env = {**os.environ, "SKY_CONFIG_DIR": str(root / "cfg"),
               "CLAUDE_CODE_MCP_SERVER_NAME": "kb",
               "CLAUDE_CODE_MCP_SERVER_URL": url}
        env.pop("SKY_KB_PAT", None)
        env.update(extra)
        return subprocess.run(str(root / "cfg" / "sky-headers"), shell=True,
                              capture_output=True, text=True, timeout=10, env=env,
                              stdin=subprocess.DEVNULL)

    def test_it_returns_a_json_object_of_strings(self):
        root = a_home()
        run_init(root)
        out = self.drive(root)
        self.assertEqual(out.returncode, 0, out.stderr)
        body = json.loads(out.stdout)
        self.assertIsInstance(body, dict)
        self.assertTrue(all(isinstance(v, str) for v in body.values()))
        self.assertEqual(body["Authorization"], f"Bearer {TOKEN}")

    def test_an_explicit_variable_wins_over_the_map(self):
        """Core's path: `sky build` has already chosen, and says so."""
        root = a_home()
        run_init(root)
        out = self.drive(root, SKY_KB_PAT="from-core")
        self.assertEqual(json.loads(out.stdout)["Authorization"], "Bearer from-core")

    def test_an_address_the_map_does_not_know_prints_nothing_on_stdout(self):
        """Empty stdout is how the host is told this failed — so it must be
        empty, and the reason must go to stderr."""
        root = a_home()
        run_init(root)
        out = self.drive(root, url="https://somewhere.else.invalid/mcp/")
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")
        self.assertIn("mcp_url", out.stderr)

    def test_the_failure_message_carries_no_token(self):
        root = a_home()
        run_init(root)
        out = self.drive(root, url="https://somewhere.else.invalid/mcp/")
        self.assertNotIn(TOKEN, out.stderr)

    def test_a_blank_token_is_refused_rather_than_sent(self):
        """A blank Bearer fails at the server and reads as a revoked token."""
        root = a_home()
        run_init(root)
        setup.write_env({"SKY_PAT_EXAMPLE_KB": ""}, root / "cfg" / "env")
        out = self.drive(root)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(out.stdout, "")


class ItIsWiredIntoTheCommand(unittest.TestCase):
    def test_setup_is_a_subcommand(self):
        from sky import cli
        parsed = cli.build_parser().parse_args(["setup", "doctor"])
        self.assertEqual(parsed.setup_action, "doctor")

    def test_the_shipped_helper_exists_and_is_executable(self):
        self.assertTrue(SHIPPED_HELPER.is_file())
        self.assertTrue(os.access(SHIPPED_HELPER, os.X_OK),
                        "the host runs this; a non-executable copy ships broken")


if __name__ == "__main__":
    unittest.main(verbosity=2)
