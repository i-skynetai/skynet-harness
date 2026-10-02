"""SH-036: the guard reads past git's global options.

`git push` was denied but `git -C . push` was allowed, because the guard matched
substrings. git's global options are now skipped before matching.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.policy import Policy  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
POLICY = Policy.load(REPO / "plugin" / "policy.yaml")


class GitGlobalOptionsDoNotHideAPush(unittest.TestCase):

    def test_each_global_option_is_skipped(self):
        for command in ("git -C . push origin feat/x",
                        "git -C/tmp push",
                        "git -c user.name=x push",
                        "git --git-dir=.git push",
                        "git --git-dir .git push",
                        "git --work-tree=. push",
                        "git --work-tree . push origin x",
                        "git --no-pager -C . push",
                        "/usr/bin/git -C . push"):
            with self.subTest(command=command):
                found = POLICY.denied_command(command)
                self.assertIsNotNone(found, f"{command!r} was not denied")
                self.assertEqual(found.action, "push")

    def test_other_denied_subcommands_are_caught_the_same_way(self):
        self.assertEqual(POLICY.denied_command("git -C . config --global x y").action,
                         POLICY.denied_command("git config --global x y").action)
        self.assertIsNotNone(POLICY.denied_command("git -C . remote add o url"))

    def test_an_allowed_command_stays_allowed(self):
        for command in ("git -C . status", "git -C . commit -m 'push it'",
                        "git --no-pager log"):
            with self.subTest(command=command):
                self.assertIsNone(POLICY.denied_command(command))


if __name__ == "__main__":
    unittest.main(verbosity=2)
