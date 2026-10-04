"""One test per finding from the v1.0.2 review.

A note on that review's headline — "none of the nine code fixes landed" — which
was a diff-range artifact rather than a defect: it compared `main...dev`, and
the merge-base of those two branches *is* the commit carrying the nine fixes,
so the range excludes them by construction. The review's own verified state
said `main` was at that commit with 473 tests passing. The individual findings
below were all real, and all are fixed here.

This file names-retired-vocabulary-on-purpose: it proves the retirement rules
fire, which means containing the words they retire.
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

from sky import broker, hosts, launcher, setup  # noqa: E402
from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")
HELPER = REPO / "plugin" / "bin" / "sky-headers"
A_PROFILE = setup.Profile.from_dict({
    "name": "t", "mcp_url": "https://stub.invalid/mcp/", "tenant_code": "ABCD2345",
    "ontology": "o", "instance": "example-kb"})


def live_lines(rendered) -> list[str]:
    """Lines a person would actually run if they pasted the block."""
    return [l for l in str(rendered).splitlines() if l and not l.startswith("#")]


class H1_NothingInTheOutputRunsButTheCommand(unittest.TestCase):
    """Fencing the body was a label. The lines inside it were still commands."""

    def test_a_comment_body_contributes_no_runnable_line(self):
        sealed = broker.accept(
            {"kind": "ticket.comment", "summary": "say it", "issue_key": "ABC-1",
             "body": "done\ngit push --force origin main\nrm -rf /"},
            run_id="r", agent_id="a")
        self.assertEqual(live_lines(broker.render(sealed)), [])

    def test_a_pull_request_body_contributes_none_either(self):
        sealed = broker.accept(
            {"kind": "pr.open", "summary": "open it", "branch": "fix/a",
             "base": "dev", "title": "T", "body": "why\nsudo shutdown now"},
            run_id="r", agent_id="a")
        self.assertEqual(
            live_lines(broker.render(sealed)),
            ['gh pr create --base dev --head fix/a --title "T" --body-file -'])


class H2_ModelTextNeverCrossesAShell(unittest.TestCase):
    """A shell expands an argument before `sky` starts, so a backtick in a
    body has already run by the time any check could see it."""

    def test_an_intent_can_be_read_from_a_file(self):
        root = Path(tempfile.mkdtemp())
        (root / "i.json").write_text(json.dumps({
            "kind": "ticket.comment", "summary": "tell it", "issue_key": "ABC-1",
            "body": "note: `id` and $(whoami) are text here"}))
        out = subprocess.run(
            [sys.executable, "-m", "sky", "intent", "--from-file",
             str(root / "i.json"), "--directory", str(root / "p")],
            cwd=str(REPO / "core"), capture_output=True, text=True, timeout=30,
            env={**os.environ, "SKY_RUN_ID": "r", "SKY_AGENT_ID": "a"})
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_the_ship_skill_tells_you_to_write_a_file(self):
        body = (REPO / "plugin" / "skills" / "ship" / "SKILL.md").read_text()
        self.assertIn("editor tool into\n`.sky/outbox/`", body)   # SH-004
        self.assertNotIn("--body", body)
        self.assertIn("never put the text on a command line", body)

    def test_it_does_not_instruct_composing_body_arguments(self):
        body = (REPO / "plugin" / "skills" / "ship" / "SKILL.md").read_text()
        for line in body.splitlines():
            if line.strip().startswith("sky intent"):
                self.assertIn("--from-file", line,
                              f"this line puts text on a command line: {line}")


class H3_ARoleAHostCannotTellApartIsNotOffered(unittest.TestCase):
    def test_codex_gets_one_read_role_not_three(self):
        """The sandbox makes architect, reviewer and security identical."""
        self.assertEqual(launcher.HAND_ROLES["codex"], frozenset({"reviewer"}))
        self.assertEqual(hosts.CAN_ENFORCE["codex"][1], ("reviewer",))

    def test_the_others_are_refused_with_a_reason(self):
        config = Path(tempfile.mkdtemp()) / "mcp.json"
        config.write_text(json.dumps(
            {"mcpServers": {"kb": {"type": "http", "url": "https://x/"}}}))
        for role in ("architect", "security", "developer"):
            with self.subTest(role=role):
                with self.assertRaises(launcher.Refused):
                    launcher.hand_command("codex", role, config, "x", POLICY)


class H4_TheLauncherIsNotWrittenOverSomebodyElses(unittest.TestCase):
    def test_a_foreign_sky_on_path_is_refused(self):
        root = Path(tempfile.mkdtemp())
        (root / "bin").mkdir()
        theirs = root / "bin" / "sky"
        theirs.write_text("#!/bin/sh\necho mine\n")
        os.chmod(theirs, 0o755)
        with self.assertRaises(setup.SetupError) as caught:
            setup.install_launcher(root / "bin")
        self.assertIn("not ours to replace", str(caught.exception))
        self.assertIn("echo mine", theirs.read_text())

    def test_one_this_tool_wrote_is_replaced_without_complaint(self):
        root = Path(tempfile.mkdtemp())
        first, _ = setup.install_launcher(root / "bin")
        again, _ = setup.install_launcher(root / "bin")
        self.assertEqual(first, again)


class H6_TheLauncherPointsSomewhereStable(unittest.TestCase):
    """A path with a version number in it breaks on the next plugin update."""

    def test_it_does_not_point_into_a_versioned_cache(self):
        root = Path(tempfile.mkdtemp())
        target, _ = setup.install_launcher(root / "bin")
        body = target.read_text()
        self.assertNotIn("plugins/cache", body)
        if sys.platform == "win32":
            self.skipTest("the setup launcher is a POSIX shebang script; on Windows the path it holds is written escaped")
        self.assertIn(str(root / "runtime"), body)

    @unittest.skipIf(sys.platform == "win32", "executes the setup launcher through its shebang, "
                     "which Windows cannot")
    def test_and_the_copy_it_points_at_really_runs(self):
        root = Path(tempfile.mkdtemp())
        target, _ = setup.install_launcher(root / "bin")
        out = subprocess.run([str(target), "selftest", "--root", str(REPO)],
                             capture_output=True, text=True, timeout=90)
        self.assertIn("PASS", out.stdout, out.stdout + out.stderr)


class H5_ARollbackCoversEverythingItWrote(unittest.TestCase):
    def test_a_failure_part_way_through_leaves_nothing(self):
        root = Path(tempfile.mkdtemp())
        saved_dir, saved_helper = setup.LAUNCHER_DIR, setup.install_helper
        setup.LAUNCHER_DIR = root / "bin"
        setup.install_helper = lambda *a, **k: (_ for _ in ()).throw(
            OSError("disk full"))
        try:
            with self.assertRaises(setup.SetupError):
                setup.init(A_PROFILE, "tok", config_dir=root / "cfg",
                           claude_json=root / "claude.json",
                           helper_source=HELPER)
        finally:
            setup.LAUNCHER_DIR, setup.install_helper = saved_dir, saved_helper
        for leftover in ("cfg/env", "cfg/kb-map.json", "claude.json"):
            with self.subTest(leftover=leftover):
                self.assertFalse((root / leftover).exists())


class H7_UninstallComparesTheWholeEntry(unittest.TestCase):
    def test_a_changed_url_keeps_the_server(self):
        """Comparing only the helper missed a person re-pointing the URL."""
        root = Path(tempfile.mkdtemp())
        claude = root / "claude.json"
        saved = setup.LAUNCHER_DIR
        setup.LAUNCHER_DIR = root / "bin"
        try:
            setup.init(A_PROFILE, "tok", config_dir=root / "cfg",
                       claude_json=claude, helper_source=HELPER)
            body = json.loads(claude.read_text())
            body["mcpServers"]["kb"]["url"] = "https://mine/mcp/"
            claude.write_text(json.dumps(body))
            setup.uninstall(config_dir=root / "cfg", claude_json=claude)
        finally:
            setup.LAUNCHER_DIR = saved
        self.assertEqual(json.loads(claude.read_text())["mcpServers"]["kb"]["url"],
                         "https://mine/mcp/")


class H8_APackageIsComplete(unittest.TestCase):
    def test_it_refuses_rather_than_emit_an_unfilled_address(self):
        saved = hosts._default_profile
        hosts._default_profile = lambda: None
        try:
            with self.assertRaises(hosts.HostError) as caught:
                hosts.build("codex", POLICY)
        finally:
            hosts._default_profile = saved
        self.assertIn("reaches nothing", str(caught.exception))

    def test_no_package_keeps_the_placeholder(self):
        for host in sorted(hosts.BUILDERS):
            for name, body in hosts.build(host, POLICY,
                                          profile=A_PROFILE).files.items():
                with self.subTest(host=host, file=name):
                    self.assertNotIn("${SKY_KB_URL}", body)
                    self.assertNotIn("${SKY_CODE_URL}", body)

    def test_the_templates_the_skills_name_are_shipped(self):
        shipped = len(list((REPO / "plugin" / "templates").glob("*.md")))
        self.assertGreater(shipped, 0)
        for host in sorted(hosts.BUILDERS):
            files = hosts.build(host, POLICY, profile=A_PROFILE).files
            with self.subTest(host=host):
                self.assertEqual(
                    len([f for f in files if f.startswith("templates/")]), shipped)


class H9_TheDocumentedLoopDoesNotStageEverything(unittest.TestCase):
    def test_it_does_not_tell_you_to_git_add_dash_a(self):
        body = (REPO / "docs" / "local-workflow.md").read_text()
        for line in body.splitlines():
            if line.strip().startswith("git add"):
                self.assertNotIn("-A", line, f"blanket add: {line}")
        self.assertIn("git diff --staged", body)
        self.assertIn("Not `git add -A`", body)


class H10_TheReadmeVersionMatchesThePlugin(unittest.TestCase):
    def test_they_agree(self):
        version = json.loads(
            (REPO / "plugin" / ".claude-plugin" / "plugin.json").read_text())["version"]
        self.assertIn(f"**v{version}.**", (REPO / "README.md").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class H11_TheRenameLeftNothingWritingIntoYourHome(unittest.TestCase):
    """Found rechecking the repo after it became `skynet-harness`.

    `install_launcher` took the launcher's directory from its argument and the
    runtime copy's from the real `~/.config/sky` — so anything that redirected
    the launcher still dropped twenty modules into the user's own home. Nothing
    failed, so nothing said so, and the evidence was a `runtime/` directory
    beside a `selftest-words` file with no setup ever having completed.
    """

    def test_both_destinations_follow_the_argument(self):
        root = Path(tempfile.mkdtemp())
        target, _ = setup.install_launcher(root / "bin")
        self.assertTrue((root / "runtime" / "sky").is_dir())
        if sys.platform == "win32":
            self.skipTest("the setup launcher is a POSIX shebang script; on Windows the path it holds is written escaped")
        self.assertIn(str(root / "runtime"), target.read_text())

    def test_an_explicit_config_dir_wins(self):
        root = Path(tempfile.mkdtemp())
        target, _ = setup.install_launcher(root / "bin", config_dir=root / "cfg")
        self.assertTrue((root / "cfg" / "runtime" / "sky").is_dir())
        self.assertFalse((root / "runtime").exists())

    def test_the_real_config_dir_is_never_written_by_a_redirected_call(self):
        real = setup.CONFIG_DIR / "runtime"
        before = sorted(p.name for p in real.glob("*")) if real.is_dir() else None
        setup.install_launcher(Path(tempfile.mkdtemp()) / "bin")
        after = sorted(p.name for p in real.glob("*")) if real.is_dir() else None
        self.assertEqual(before, after)

    def test_a_failed_setup_leaves_no_runtime_behind(self):
        root = Path(tempfile.mkdtemp())
        saved = setup.install_helper
        setup.install_helper = lambda *a, **k: (_ for _ in ()).throw(
            OSError("disk full"))
        try:
            with self.assertRaises(setup.SetupError):
                setup.init(A_PROFILE, "tok", config_dir=root / "cfg",
                           claude_json=root / "claude.json", helper_source=HELPER)
        finally:
            setup.install_helper = saved
        self.assertFalse((root / "cfg" / "runtime").exists())

    def test_every_retired_prefix_actually_fires(self):
        """Three of the first five rules were decoration: `VAI_` is always
        followed by a word character, so a both-sides word boundary never
        matched it."""
        from sky import selftest
        for probe, caught in (("VAI_KB_URL", True), ("/vai:doctor", True),
                              ("mcp__plugin_vai_kb__x", True), ("vai-headers", True),
                              ("SKY_KB_URL", False), ("/sky:doctor", False),
                              ("sky-headers", False)):
            root = Path(tempfile.mkdtemp())
            for d in ("core", "plugin", "schemas", "hosts", "docs"):
                (root / d).mkdir()
            (root / "plugin" / "skills" / "x").mkdir(parents=True)
            (root / "plugin" / "skills" / "x" / "SKILL.md").write_text(f"a {probe} b")
            with self.subTest(probe=probe):
                self.assertEqual(not selftest.check_no_retired_names(root).passed,
                                 caught)


class H12_ARedirectedSetupTouchesNothingReal(unittest.TestCase):
    """The worst of the three leaks, and the last one found.

    A test that named its own `config_dir` still installed a command onto the
    real `~/.local/bin` — pointing at the temporary runtime it had just made.
    The command kept working until the operating system cleaned that directory,
    at which point `sky` on a person's PATH would simply stop, with nothing to
    say why. Nothing failed at the time, which is what let it happen twice.
    """

    def a_redirected_init(self, root: Path):
        setup.init(A_PROFILE, "tok", config_dir=root / "cfg",
                   claude_json=root / "claude.json", helper_source=HELPER)

    def test_it_installs_its_launcher_beside_its_own_configuration(self):
        root = Path(tempfile.mkdtemp())
        self.a_redirected_init(root)
        self.assertTrue((root / "cfg" / "bin" / "sky").is_file())
        self.assertTrue((root / "cfg" / "runtime" / "sky").is_dir())

    def test_the_real_launcher_is_untouched(self):
        real = Path("~/.local/bin/sky").expanduser()
        before = real.read_bytes() if real.exists() else None
        self.a_redirected_init(Path(tempfile.mkdtemp()))
        after = real.read_bytes() if real.exists() else None
        self.assertEqual(before, after, "a redirected setup wrote to the real PATH")

    def test_the_real_config_directory_is_untouched(self):
        real = setup.CONFIG_DIR
        before = sorted(p.name for p in real.glob("*")) if real.is_dir() else None
        self.a_redirected_init(Path(tempfile.mkdtemp()))
        after = sorted(p.name for p in real.glob("*")) if real.is_dir() else None
        self.assertEqual(before, after)

    def test_a_launcher_never_points_into_a_temporary_directory(self):
        root = Path(tempfile.mkdtemp())
        self.a_redirected_init(root)
        body = (root / "cfg" / "bin" / "sky").read_text()
        if sys.platform == "win32":
            self.skipTest("the setup launcher is a POSIX shebang script; on Windows the path it holds is written escaped")
        self.assertIn(str(root / "cfg" / "runtime"), body)
        # And the shape of the bug, stated so it cannot come back quietly: the
        # path a launcher points at must be the one beside it.
        self.assertNotIn("/.config/sky/runtime", body)
