import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sky import codexdispatch
from sky import project


class NativeDispatch(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.arguments = {"root": str(self.root), "task": "bounded task"}

    def test_unknown_tools_overrides_and_invalid_roots_never_start(self):
        cases = [("approve", self.arguments), ("implement", dict(self.arguments, role="security")),
                 ("implement", dict(self.arguments, command="publish")),
                 ("review", dict(self.arguments, root="relative")),
                 ("review", dict(self.arguments, task=""))]
        with patch("sky.codexdispatch.subprocess.Popen") as start:
            for name, arguments in cases:
                with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                    codexdispatch.dispatch(name, arguments, cwd=self.root)
            start.assert_not_called()

    def test_task_is_one_argument_and_role_is_fixed(self):
        def start(command, **kwargs):
            self.command, self.env = command, kwargs["env"]
            kwargs["stdout"].write(json.dumps({"sky": "build", "ok": True, "run_id": "runtime-run"}) + "\n")
            kwargs["stdout"].flush()
            return SimpleNamespace(poll=lambda: 0, returncode=0, wait=lambda **_: 0)
        with patch("sky.codexdispatch.context_sources.repository", return_value=self.root), \
             patch("sky.codexdispatch.subprocess.Popen", side_effect=start):
            result = codexdispatch.dispatch("implement", dict(self.arguments, task="test; publish --role reviewer"), cwd=self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(self.command[-2:], ["test; publish --role reviewer", "--json"])
        self.assertEqual(self.command[self.command.index("--role") + 1], "developer")
        self.assertEqual(self.env["SKY_LAUNCHED"], "1")

    def test_disconnect_stops_cli_tree(self):
        disconnected = threading.Event()
        disconnected.set()
        peer = SimpleNamespace(poll=lambda: None, wait=lambda **_: 0)
        with patch("sky.codexdispatch.context_sources.repository", return_value=self.root), \
             patch("sky.codexdispatch.subprocess.Popen", return_value=peer), \
             patch("sky.codexdispatch.hand._stop") as stop:
            with self.assertRaisesRegex(ValueError, "disconnected"):
                codexdispatch.dispatch("review", self.arguments, cwd=self.root, disconnected=disconnected)
            stop.assert_called_once_with(peer)

    def test_repository_probe_never_inherits_mcp_stdin(self):
        with patch("sky.project.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=str(self.root))) as git:
            self.assertEqual(project.git_root(self.root), self.root)
            self.assertEqual(git.call_args.kwargs["stdin"], codexdispatch.subprocess.DEVNULL)
