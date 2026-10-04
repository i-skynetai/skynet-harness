"""Tests for the launcher.

The launcher is the only place the no-Safety-no-build rule is applied, so these
are mostly about it refusing. The environment tests matter for a different
reason: a hand inherits exactly what it is given, and the easiest way to leak a
credential is to build that environment by filtering rather than by listing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import launcher  # noqa: E402
from sky.kbmap import KB  # noqa: E402
from sky.policy import Policy  # noqa: E402

#: The policy that actually ships. Using the real file means a change to it
#: that breaks a role shows up here rather than in a user's session.
SHIPPED = Policy.load(Path(__file__).resolve().parents[2] / "plugin" / "policy.yaml")

def a_mcp_config():
    """A per-run MCP config on disk.

    Codex is now given its knowledge base through `-c` overrides read back from
    this file, and refuses to start without one — a Codex run that could not be
    told which KB to use would silently read the person's own configuration
    instead. So passing a path to nothing tests the refusal, not the command.
    """
    import json as _json
    import tempfile as _tempfile
    path = Path(_tempfile.mkdtemp()) / "mcp.json"
    path.write_text(_json.dumps(
        {"mcpServers": {"kb": {"type": "http", "url": "https://stub.invalid/mcp/"}}}))
    return path


from sky.readiness import Brain, Kind, Part, State  # noqa: E402


def a_kb(**over) -> KB:
    body = dict(name="team_kb", purpose="", url="https://kb.example/mcp/",
                tenant="TEAM1234", ontology="sky_sdlc", privacy="work",
                pat_env="SKY_TEST_PAT", code_url="https://kb.example/mcp-internal/")
    body.update(over)
    return KB(**body)


def a_brain(**states) -> Brain:
    b = Brain()
    for part in Part:
        b.add(part, states.get(part.name.lower(), State.OK), "probed")
    return b


class Refusals(unittest.TestCase):
    def test_no_safety_refuses_a_build(self):
        with self.assertRaises(launcher.Refused) as caught:
            launcher.check_readiness(a_brain(safety=State.MISSING), Kind.BUILD)
        self.assertIn("safety", str(caught.exception))

    def test_the_refusal_names_the_part_and_what_is_still_possible(self):
        with self.assertRaises(launcher.Refused) as caught:
            launcher.check_readiness(a_brain(safety=State.MISSING), Kind.BUILD)
        message = str(caught.exception)
        self.assertIn("Safety is the blocking one", message)
        self.assertIn("it IS ready for: question, review", message)

    def test_a_ready_brain_is_not_refused(self):
        launcher.check_readiness(a_brain(), Kind.BUILD)     # must not raise

    def test_an_unknown_role_is_refused_rather_than_defaulted(self):
        with self.assertRaises(launcher.Refused):
            launcher.hand_command("claude", "superuser", a_mcp_config(), "x", SHIPPED)


class TheEnvironment(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SKY_TEST_PAT"] = "test-token"
        os.environ["A_SECRET_FROM_MY_SHELL"] = "must-not-be-inherited"
        self.env = launcher.build_env(a_kb(), run_id="run-1", agent_id="a-dev-1",
                                      role="developer", task="ENG-1")

    def tearDown(self) -> None:
        self.env.close()
        os.environ.pop("A_SECRET_FROM_MY_SHELL", None)

    def test_it_is_built_by_listing_not_by_filtering(self):
        """Anything not named is absent — including things invented later.

        A filter has to be updated every time someone puts a new secret in
        their shell profile. Nobody remembers to.
        """
        self.assertNotIn("A_SECRET_FROM_MY_SHELL", self.env.variables)

    def test_it_carries_the_kb_it_was_given_and_no_other(self):
        self.assertEqual(self.env.variables["SKY_KB_NAME"], "team_kb")
        self.assertEqual(self.env.variables["SKY_KB_PAT"], "test-token")

    def test_it_marks_itself_as_launched(self):
        """So `doctor` inside the hand knows the rules are enforced here."""
        self.assertEqual(self.env.variables["SKY_LAUNCHED"], "1")

    def test_git_is_given_no_route_to_a_credential(self):
        v = self.env.variables
        self.assertEqual(v["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(v["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(v["GIT_ASKPASS"], "/usr/bin/false")
        self.assertIn("IdentitiesOnly=yes", v["GIT_SSH_COMMAND"])
        self.assertIn("helper =", Path(v["GIT_CONFIG_GLOBAL"]).read_text())

    def test_path_is_not_treated_as_a_secret(self):
        """PAT is a substring of PATH.

        A redaction heuristic that hides PATH while missing a real token is
        worse than none, because it looks like it is working.
        """
        self.assertFalse(launcher.is_secret("PATH"))
        self.assertTrue(launcher.is_secret("SKY_KB_PAT"))


class TheProof(unittest.TestCase):
    """The check that the block actually holds — and that it can fail."""

    def setUp(self) -> None:
        os.environ["SKY_TEST_PAT"] = "test-token"

    def test_the_launched_environment_yields_no_credential(self):
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            ok, why = launcher.prove_git_blocked(env)
            self.assertTrue(ok, why)
        finally:
            env.close()

    def test_the_proof_fails_when_the_block_is_removed(self):
        """Without this, the proof could be a green light that never turns red.

        Skipped where the ordinary environment has no credential to hand back —
        on such a machine there is nothing to distinguish, and a pass here would
        mean nothing.
        """
        probe = "protocol=https\nhost=dev.azure.com\n\n"
        baseline = subprocess.run(["git", "credential", "fill"], input=probe,
                                  capture_output=True, text=True, timeout=15)
        if "password=" not in baseline.stdout:
            self.skipTest("this machine has no stored credential, so the proof "
                          "cannot be shown to discriminate")
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            # Strip exactly the git controls: what is left is an ordinary shell.
            for key in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_ASKPASS",
                        "GIT_TERMINAL_PROMPT", "GIT_SSH_COMMAND"):
                env.variables.pop(key, None)
            ok, why = launcher.prove_git_blocked(env)
            self.assertFalse(ok, "the proof passed with the block removed")
            self.assertIn("refusing to start", why)
        finally:
            env.close()


class WhatTheHandNeedsToActuallyWork(unittest.TestCase):
    """A connection the hand cannot use is not a connection."""

    def test_the_tenant_and_ontology_are_in_the_environment(self):
        """Every KB tool call takes the tenant as an argument.

        It is not in the URL and not in the header, so a hand without it has a
        working connection and fails on its first call.
        """
        os.environ["SKY_TEST_PAT"] = "test-token"
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            self.assertEqual(env.variables["SKY_TENANT"], a_kb().tenant)
            self.assertEqual(env.variables["SKY_ONTOLOGY"], a_kb().ontology)
        finally:
            env.close()


class TheHandCommand(unittest.TestCase):
    def test_a_developer_may_commit_but_not_push(self):
        tools = SHIPPED.tools_for("developer")
        self.assertTrue(any("git commit" in t for t in tools))
        self.assertFalse(any("push" in t for t in tools))

    def test_read_only_roles_have_no_shell_and_no_editing(self):
        for role in ("reviewer", "architect", "security"):
            tools = SHIPPED.tools_for(role)
            self.assertFalse(any(t.startswith("Bash") for t in tools), role)
            self.assertNotIn("Edit", tools, role)
            self.assertNotIn("Write", tools, role)

    def test_claude_is_confined_to_the_chosen_kb(self):
        cmd = launcher.hand_command("claude", "developer", a_mcp_config(), "do it",
                                   SHIPPED)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertIn("--mcp-config", cmd)
        self.assertIn("sky:developer", cmd)

    def test_claude_is_asked_for_stream_json_not_json(self):
        """The watchdog needs lines. `json` is silent until the end, so a healthy
        long build would look like a stuck hand and be killed by the silence cap."""
        cmd = launcher.hand_command("claude", "developer", a_mcp_config(), "do it",
                                   SHIPPED)
        i = cmd.index("--output-format")
        self.assertEqual(cmd[i + 1], "stream-json")
        # Print mode refuses stream-json without --verbose. A real run said so:
        # "Error: When using --print, --output-format=stream-json requires --verbose".
        self.assertIn("--verbose", cmd)

    def test_the_prompt_is_never_after_a_variadic_option(self):
        """`--allowedTools <tools...>` eats every following token.

        With the prompt appended last it became one more tool name, and the run
        failed with "Input must be provided either through stdin or as a prompt
        argument". Nothing in the command's shape revealed that — a real run
        did. Any option documented as `<x...>` has the same appetite.
        """
        cmd = launcher.hand_command("claude", "reviewer", a_mcp_config(),
                                    "review the diff", SHIPPED)
        self.assertIn("review the diff", cmd)
        prompt_at = cmd.index("review the diff")
        for variadic in ("--allowedTools", "--disallowedTools", "--tools"):
            if variadic in cmd:
                self.assertLess(prompt_at, cmd.index(variadic),
                                f"the prompt follows {variadic}, which would eat it")

    def test_the_prompt_is_present_for_every_hand_that_can_run(self):
        for hand, role in (("claude", "reviewer"), ("codex", "reviewer")):
            with self.subTest(hand=hand):
                cmd = launcher.hand_command(hand, role, a_mcp_config(),
                                            "do the thing", SHIPPED)
                self.assertIn("do the thing", cmd)

    def test_the_recorded_command_hides_the_prompt_and_keeps_every_tool(self):
        """`cmd[:-1]` was both, and is now wrong on both counts.

        The prompt moved before `--allowedTools` (which would eat it), so
        dropping the last element shows the prompt and silently drops a tool
        from the run record — a record that is missing a tool is a record that
        cannot answer what the hand was allowed to do.
        """
        cmd = launcher.hand_command("claude", "reviewer", a_mcp_config(),
                                    "the secret task text", SHIPPED)
        shown = launcher.without_prompt(cmd, "the secret task text")
        self.assertNotIn("the secret task text", shown)
        self.assertIn("<prompt>", shown)
        self.assertEqual(len(shown), len(cmd), "an argument was dropped")
        self.assertEqual(shown[-1], cmd[-1], "the last tool was lost")

    def test_the_mcp_config_names_one_kb_and_is_not_world_readable(self):
        os.environ["SKY_TEST_PAT"] = "test-token"
        tmp = Path(tempfile.mkdtemp())
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            path = launcher.write_mcp_config(env, a_kb(), tmp)
            import json
            servers = json.loads(path.read_text())["mcpServers"]
            self.assertEqual(sorted(servers), ["code", "kb"])
            if sys.platform == "win32":
                self.skipTest("Windows has no POSIX file modes; chmod 0600 cannot make a file private there")
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)


class FindingsFromReview(unittest.TestCase):
    """One test per defect a review found. They existed; they must not return."""

    def setUp(self) -> None:
        os.environ["SKY_TEST_PAT"] = "test-token"

    # ── the git proof passed on any failure, not on the block ────────────
    @unittest.skipIf(sys.platform == "win32", "the fake git is a #!/bin/sh script with no .exe, "
                     "put on PATH with ':', which Windows can neither find nor run")
    def test_an_unrelated_git_failure_is_not_a_pass(self):
        fake = Path(tempfile.mkdtemp())
        (fake / "git").write_text("#!/bin/sh\necho 'fatal: arbitrary failure' >&2\nexit 128\n")
        (fake / "git").chmod(0o755)
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            env.variables["PATH"] = f"{fake}:{env.variables['PATH']}"
            ok, why = launcher.prove_git_blocked(env)
            self.assertFalse(ok, "git failing for its own reasons read as blocked")
            self.assertIn("fingerprint", why)
        finally:
            env.close()

    def test_a_missing_git_is_a_refusal_not_a_pass(self):
        env = launcher.build_env(a_kb(), run_id="r", agent_id="a",
                                 role="developer", task="t")
        try:
            env.variables["PATH"] = "/nonexistent"
            ok, why = launcher.prove_git_blocked(env)
            self.assertFalse(ok)
            self.assertIn("refusing rather than assuming", why)
        finally:
            env.close()

    # ── roles were only real on one hand ─────────────────────────────────
    def test_a_hand_that_cannot_enforce_a_role_is_refused_it(self):
        for hand, role in (("kimi", "reviewer"), ("kimi", "developer"),
                           ("codex", "developer")):
            with self.subTest(hand=hand, role=role):
                with self.assertRaises(launcher.Refused) as caught:
                    launcher.hand_command(hand, role, a_mcp_config(), "x", SHIPPED)
                self.assertIn("cannot run", str(caught.exception))

    def test_codex_may_still_review_and_does_so_read_only(self):
        cmd = launcher.hand_command("codex", "reviewer", a_mcp_config(), "x",
                                   SHIPPED)
        self.assertIn("read-only", cmd)
        self.assertNotIn("workspace-write", cmd)

    def test_every_offered_pair_is_one_the_hand_can_actually_hold(self):
        for hand, roles in launcher.HAND_ROLES.items():
            for role in roles:
                launcher.hand_command(hand, role, a_mcp_config(), "x", SHIPPED)
