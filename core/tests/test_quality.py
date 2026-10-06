"""Tests for the Quality control probe.

The one that matters is `test_zero_tests_is_healthy_even_though_the_exit_code_is_five`.
Both Python runners exit **5** when nothing matches, and that is the *healthy*
answer for this probe. A generic "non-zero means failure" reading inverts it:
every repository whose tests are fine would be reported broken, and every build
refused. The behaviour was measured before the code was written, not assumed.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky import quality  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def a_repo(**files) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


class TheExitCodeTrap(unittest.TestCase):
    def test_the_measurement_this_rests_on_still_holds(self):
        """What `python -m unittest` does when nothing matches, pinned per
        interpreter, because the whole probe reads that answer as healthy.
        3.12 and later exit 5 and say NO TESTS RAN; 3.11 exits 0 and says
        Ran 0 tests (SH-051)."""
        out = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "zzz_matches_nothing*.py"],
            cwd=REPO, capture_output=True, text=True, timeout=60)
        said = out.stdout + out.stderr
        if sys.version_info >= (3, 12):
            self.assertEqual(out.returncode, 5)
            self.assertIn("NO TESTS RAN", said)
        else:
            self.assertEqual(out.returncode, 0)
            self.assertIn("Ran 0 tests", said)

    def test_a_3_11_style_answer_reads_as_healthy_on_any_interpreter(self):
        """Exit 0 with "Ran 0 tests … OK" is what Python 3.11 prints. The probe
        must read it as healthy whichever interpreter runs the probe (SH-051)."""
        import subprocess as sp
        root = a_repo(**{"tests/__init__.py": ""})
        fake = sp.CompletedProcess(args=[], returncode=0,
                                   stdout="\n----\nRan 0 tests in 0.000s\n\nOK\n",
                                   stderr="")
        real = quality.subprocess.run
        quality.subprocess.run = lambda *a, **k: fake
        try:
            result = quality.check(root)
        finally:
            quality.subprocess.run = real
        self.assertEqual(result.state, "ok", result.detail)
        self.assertEqual(result.runner, "unittest")

    def test_zero_tests_is_healthy_even_though_the_exit_code_is_five(self):
        """Against this repository, which really does use unittest."""
        result = quality.check(REPO)
        self.assertEqual(result.state, "ok", result.detail)
        self.assertEqual(result.runner, "unittest")
        self.assertIn("zero tests", result.detail)

    def test_exit_one_is_not_read_the_same_way_as_exit_five(self):
        """Five means "matched nothing" and is healthy; one is not.

        The realistic exit-1 case is a runner configured but not installed:
        `python -m pytest` where pytest is absent exits 1 with "No module
        named pytest" — which is MISSING, because the fix is to install it,
        not DOWN, which would read as "your test setup is broken". This was
        measured, not assumed; an earlier version of this test invented a
        scenario that never happens.
        """
        import importlib.util
        if importlib.util.find_spec("pytest") is not None:
            self.skipTest("pytest is installed here, so this path cannot be exercised")
        result = quality.check(a_repo(**{"pytest.ini": "[pytest]\n"}))
        self.assertEqual(result.state, "missing", result.detail)
        self.assertEqual(result.runner, "pytest")
        self.assertIn("not installed", result.detail)


class Detection(unittest.TestCase):
    def test_a_pytest_configuration_wins(self):
        root = a_repo(**{"pytest.ini": "[pytest]\n", "tests/x.py": ""})
        runner = quality.detect(root)
        self.assertEqual(runner.name, "pytest")
        self.assertIn("--collect-only", runner.command)
        self.assertIn(quality.NO_MATCH, runner.command)

    def test_pyproject_with_a_pytest_section_counts(self):
        root = a_repo(**{"pyproject.toml": "[tool.pytest.ini_options]\n"})
        self.assertEqual(quality.detect(root).name, "pytest")

    def test_a_tests_directory_alone_means_unittest(self):
        root = a_repo(**{"tests/test_x.py": ""})
        runner = quality.detect(root)
        self.assertEqual(runner.name, "unittest")
        self.assertIn("discover", runner.command)

    def test_jest_is_found_through_package_json(self):
        root = a_repo(**{"package.json": json.dumps(
            {"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29"}})})
        runner = quality.detect(root)
        self.assertEqual(runner.name, "jest")
        self.assertIn("--passWithNoTests", runner.command)
        self.assertIn(quality.NO_MATCH, runner.command)

    def test_vitest_too(self):
        root = a_repo(**{"package.json": json.dumps(
            {"scripts": {"test": "vitest run"}, "devDependencies": {"vitest": "^1"}})})
        self.assertEqual(quality.detect(root).name, "vitest")

    def test_an_npm_test_script_with_an_unknown_runner_is_not_used(self):
        """`npm test` alone runs everything, which is what must not happen."""
        root = a_repo(**{"package.json": json.dumps(
            {"scripts": {"test": "some-bespoke-runner"}})})
        self.assertIsInstance(quality.detect(root), quality.NoRunner)

    def test_go_and_cargo(self):
        self.assertEqual(quality.detect(a_repo(**{"go.mod": "module x\n"})).name, "go")
        self.assertEqual(quality.detect(a_repo(**{"Cargo.toml": "[package]\n"})).name,
                         "cargo")

    def test_nothing_found_says_what_it_looked_for(self):
        found = quality.detect(a_repo(**{"README.md": "# nothing here"}))
        self.assertIsInstance(found, quality.NoRunner)
        self.assertIn("pytest.ini", str(found))
        self.assertIn("package.json", str(found))


class WhenTheSuiteIsNotAtTheRoot(unittest.TestCase):
    """A repository that keeps its code in a subdirectory is ordinary.

    This one keeps its tests in `core/`. A root-only probe reported "no test
    runner" for it — a false MISSING, which refuses every build. Found by
    running the real thing, not by reading the code.
    """

    def test_a_suite_one_level_down_is_found(self):
        root = a_repo(**{"core/tests/test_x.py": "", "README.md": "#"})
        runner = quality.detect(root)
        self.assertEqual(runner.name, "unittest")
        self.assertIn("core/tests", runner.command)

    def test_the_command_still_runs_from_the_repository_root(self):
        """The path is rebased, so `cwd` stays the repository."""
        root = a_repo(**{"core/tests/test_x.py": ""})
        result = quality.check(root)
        self.assertEqual(result.state, "ok", result.detail)

    def test_the_real_repository_passes_from_its_root(self):
        """The case that found this: tests live in core/."""
        result = quality.check(REPO.parent)
        self.assertEqual(result.state, "ok", result.detail)

    def test_it_does_not_choose_between_several(self):
        """Which suite a task concerns is not something a probe can know."""
        root = a_repo(**{"api/tests/test_a.py": "", "web/package.json": json.dumps(
            {"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29"}})})
        found = quality.detect(root)
        self.assertIsInstance(found, quality.Ambiguous)
        self.assertEqual(sorted(found.where), ["api", "web"])
        result = quality.check(root)
        self.assertEqual(result.state, "degraded")
        self.assertIn("subdirectories have test suites", result.detail)

    def test_it_does_not_descend_into_dependencies(self):
        """node_modules is full of other people's test suites."""
        root = a_repo(**{"node_modules/x/package.json": json.dumps(
            {"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29"}}),
            ".venv/lib/tests/test_x.py": ""})
        self.assertIsInstance(quality.detect(root), quality.NoRunner)

    def test_it_stops_at_one_level(self):
        """Two levels down is someone else's repository, not this one."""
        root = a_repo(**{"a/b/tests/test_x.py": ""})
        self.assertIsInstance(quality.detect(root), quality.NoRunner)


class WhatItRefusesToDo(unittest.TestCase):
    def test_it_never_runs_the_real_suite(self):
        """Every command carries a selector that cannot match.

        A probe that runs the suite takes minutes, so it gets turned off — and
        a turned-off probe is worse than none, because the table still shows a
        row for it.
        """
        for files in ({"pytest.ini": "[pytest]\n"},
                      {"tests/test_x.py": ""},
                      {"package.json": json.dumps(
                          {"scripts": {"test": "jest"},
                           "devDependencies": {"jest": "^29"}})},
                      {"go.mod": "module x\n"},
                      {"Cargo.toml": "[package]\n"}):
            runner = quality.detect(a_repo(**files))
            with self.subTest(runner=runner.name):
                joined = " ".join(runner.command)
                self.assertTrue(
                    quality.NO_MATCH in joined or "-run ^$" in joined
                    or "^$" in runner.command,
                    f"{runner.name} has no selector — it would run the suite")

    def test_a_make_only_repository_is_degraded_with_the_reason(self):
        """`make test` takes no selector, so probing it means running it."""
        root = a_repo(**{"Makefile": "test:\n\tpytest\n"})
        result = quality.check(root)
        self.assertEqual(result.state, "degraded")
        self.assertIn("no selector", result.detail)
        self.assertEqual(result.runner, "make")

    def test_a_repository_with_no_suite_is_missing_not_broken(self):
        result = quality.check(a_repo(**{"README.md": "# nothing"}))
        self.assertEqual(result.state, "missing")
        self.assertIn("looked for", result.detail)

    def test_a_runner_that_is_not_installed_is_missing_not_down(self):
        root = a_repo(**{"go.mod": "module x\n"})
        import shutil
        if shutil.which("go"):
            self.skipTest("go is installed here, so this path cannot be exercised")
        result = quality.check(root)
        self.assertEqual(result.state, "missing")
        self.assertIn("not on PATH", result.detail)


class ItFeedsTheBrain(unittest.TestCase):
    def test_the_probe_sets_quality_control_from_the_check(self):
        from sky import probes
        from sky.readiness import Brain, Part, State
        brain = Brain()
        probes.probe_quality(brain, REPO)
        self.assertEqual(brain.state_of(Part.QUALITY), State.OK)

    def test_quality_is_no_longer_reported_as_not_built(self):
        """It was in the pending list; a stale entry there would mask a real
        probe result."""
        from sky import probes
        from sky.readiness import Part
        self.assertNotIn(Part.QUALITY, probes._PENDING)

    def test_a_repository_with_no_runner_blocks_a_build(self):
        """Quality control is required for BUILD, so this is the consequence."""
        from sky import probes
        from sky.readiness import Brain, Kind, Part, State
        brain = Brain()
        probes.probe_quality(brain, a_repo(**{"README.md": "#"}))
        self.assertEqual(brain.state_of(Part.QUALITY), State.MISSING)
        self.assertIn(Part.QUALITY, [b.part for b in brain.blockers(Kind.BUILD)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
