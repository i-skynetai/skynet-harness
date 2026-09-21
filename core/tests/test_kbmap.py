"""Tests for KB resolution.

The interesting cases are all refusals. Resolving a KB when everything lines up
is easy; the value is in what this declines to do, because those are the
failures that would otherwise be silent — a client repository quietly answered
from the team's knowledge base looks exactly like success.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.kbmap import KB, KBMap, KBMapError, NoKBForPath  # noqa: E402


def a_map(tmp: Path, **overrides) -> KBMap:
    """A two-KB map: a work default, and a client KB owning one directory."""
    body = {
        "team_kb": {
            "purpose": "the team's own delivery knowledge",
            "mcp_url": "https://kb.example/mcp/",
            "code_url": "https://kb.example/mcp-internal/",
            "tenant_code": "TEAM1234",
            "ontology": "sky_sdlc",
            "privacy": "work",
            "write": True,
            "pat_env": "SKY_PAT_TEAM",
            "hints": ["team", "eng-"],
            "default": True,
            "repos": [str(tmp / "work" / "product")],
        },
        "client_kb": {
            "purpose": "one client's delivery knowledge",
            "mcp_url": "https://client.example/mcp/",
            "tenant_code": "CLNT5678",
            "ontology": "sky_sdlc",
            "privacy": "client",
            "write": True,
            "pat_env": "SKY_PAT_CLIENT",
            "hints": ["acme"],
            "repos": [str(tmp / "client" / "app")],
        },
    }
    for name, patch in overrides.items():
        body.setdefault(name, {}).update(patch) if name in body else body.update({name: patch})
    path = tmp / "kb-map.json"
    path.write_text(json.dumps(body))
    return KBMap.load(path)


class Resolution(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        for p in ("work/product/src", "client/app/src", "elsewhere"):
            (self.tmp / p).mkdir(parents=True, exist_ok=True)
        self.m = a_map(self.tmp)

    def test_a_repository_resolves_to_its_own_kb(self):
        self.assertEqual(self.m.resolve(self.tmp / "work" / "product").name, "team_kb")
        self.assertEqual(self.m.resolve(self.tmp / "client" / "app").name, "client_kb")

    def test_a_subdirectory_resolves_like_its_repository(self):
        self.assertEqual(self.m.resolve(self.tmp / "client" / "app" / "src").name, "client_kb")

    def test_an_unowned_directory_falls_back_to_a_work_default(self):
        self.assertEqual(self.m.resolve(self.tmp / "elsewhere").name, "team_kb")

    def test_the_nested_repository_wins(self):
        """A POC inside a checkout belongs to the POC's KB, not the parent's."""
        nested = self.tmp / "work" / "product" / "poc"
        nested.mkdir(parents=True, exist_ok=True)
        m = a_map(self.tmp, poc_kb={
            "purpose": "a proof of concept", "mcp_url": "https://kb.example/mcp/",
            "tenant_code": "POC00001", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_PAT_TEAM", "repos": [str(nested)],
        })
        self.assertEqual(m.resolve(nested).name, "poc_kb")


class Refusals(unittest.TestCase):
    """What it will not do. These are the point of the module."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        for p in ("work/product", "client/app", "elsewhere"):
            (self.tmp / p).mkdir(parents=True, exist_ok=True)
        self.m = a_map(self.tmp)

    def test_an_override_cannot_cross_a_privacy_class(self):
        """Inside a client repository, --kb team_kb is refused.

        This is the silent failure the module exists to prevent: the answer
        would have looked completely normal.
        """
        with self.assertRaises(NoKBForPath) as caught:
            self.m.resolve(self.tmp / "client" / "app", override="team_kb")
        message = str(caught.exception)
        self.assertIn("client_kb", message)
        self.assertIn("team_kb", message)
        self.assertIn("privacy", message)

    def test_an_override_within_the_same_class_is_allowed(self):
        m = a_map(self.tmp, other_work={
            "purpose": "another work KB", "mcp_url": "https://kb2.example/mcp/",
            "tenant_code": "WORK9999", "ontology": "sky_sdlc", "privacy": "work",
            "pat_env": "SKY_PAT_TEAM",
        })
        self.assertEqual(
            m.resolve(self.tmp / "work" / "product", override="other_work").name,
            "other_work",
        )

    def test_an_unowned_directory_does_not_fall_into_a_client_default(self):
        """A non-work default is never reached by accident."""
        body = json.loads((self.tmp / "kb-map.json").read_text())
        body["team_kb"]["default"] = False
        body["client_kb"]["default"] = True
        path = self.tmp / "client-default.json"
        path.write_text(json.dumps(body))
        m = KBMap.load(path)
        with self.assertRaises(NoKBForPath) as caught:
            m.resolve(self.tmp / "elsewhere")
        self.assertIn("--kb", str(caught.exception))

    def test_a_personal_kb_must_be_local(self):
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp, leaky={
                "purpose": "private notes", "mcp_url": "https://somewhere.example/mcp/",
                "tenant_code": "PRIV0001", "ontology": "personal", "privacy": "personal",
                "pat_env": "SKY_PAT_LOCAL",
            })
        self.assertIn("stays on this machine", str(caught.exception))

    def test_two_defaults_is_an_error_not_a_coin_toss(self):
        body = json.loads((self.tmp / "kb-map.json").read_text())
        body["client_kb"]["default"] = True
        path = self.tmp / "two-defaults.json"
        path.write_text(json.dumps(body))
        with self.assertRaises(KBMapError) as caught:
            KBMap.load(path)
        self.assertIn("more than one", str(caught.exception))

    def test_a_name_that_would_not_join_in_the_graph_is_rejected(self):
        """Names are matched exactly when linking a skill to its usage."""
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp, **{"Team-KB": {
                "purpose": "x", "mcp_url": "https://kb.example/mcp/",
                "tenant_code": "TEAM1234", "ontology": "sky_sdlc", "privacy": "work",
            }})
        self.assertIn("matched exactly", str(caught.exception))

    def test_an_unknown_name_lists_what_does_exist(self):
        with self.assertRaises(KBMapError) as caught:
            self.m.get("typo_kb")
        self.assertIn("client_kb", str(caught.exception))
        self.assertIn("team_kb", str(caught.exception))


class Tokens(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.m = a_map(self.tmp)

    def test_the_map_holds_a_variable_name_not_a_secret(self):
        raw = json.loads((self.tmp / "kb-map.json").read_text())
        flat = json.dumps(raw)
        self.assertIn("SKY_PAT_TEAM", flat)          # the name is there
        self.assertNotIn("Bearer", flat)             # a value is not

    def test_a_missing_token_says_where_it_belongs(self):
        import os
        os.environ.pop("SKY_PAT_TEAM", None)
        with self.assertRaises(KBMapError) as caught:
            self.m.get("team_kb").token()
        self.assertIn("SKY_PAT_TEAM", str(caught.exception))
        self.assertIn("env", str(caught.exception))


class Hints(unittest.TestCase):
    def test_a_keyword_pins_the_kb_with_no_model_call(self):
        tmp = Path(tempfile.mkdtemp())
        m = a_map(tmp)
        self.assertEqual(m.by_hint("look at ENG-123 please").name, "team_kb")
        self.assertEqual(m.by_hint("the acme migration").name, "client_kb")
        self.assertIsNone(m.by_hint("something unrelated"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class LocalityIsAHostNotAPrefix(unittest.TestCase):
    """`https://localhost.evil.example/` starts with "https://localhost"."""

    def test_a_lookalike_host_is_not_local(self):
        tmp = Path(tempfile.mkdtemp())
        for url in ("https://localhost.evil.example/mcp/",
                    "https://127.0.0.1.attacker.net/mcp/",
                    "https://mylocalhost.example/mcp/"):
            with self.subTest(url=url):
                with self.assertRaises(KBMapError) as caught:
                    a_map(tmp, private_kb={
                        "purpose": "notes", "mcp_url": url, "tenant_code": "PRIV0001",
                        "ontology": "personal", "privacy": "personal",
                        "pat_env": "SKY_PAT_LOCAL"})
                self.assertIn("stays on this machine", str(caught.exception))

    def test_the_real_local_hosts_are_accepted(self):
        tmp = Path(tempfile.mkdtemp())
        for url in ("http://localhost:8000/mcp/", "http://127.0.0.1:8000/mcp/"):
            with self.subTest(url=url):
                m = a_map(tmp, private_kb={
                    "purpose": "notes", "mcp_url": url, "tenant_code": "PRIV0001",
                    "ontology": "personal", "privacy": "personal",
                    "pat_env": "SKY_PAT_LOCAL"})
                self.assertEqual(m.get("private_kb").privacy, "personal")


class TheSharedCatalogueIsNotATaskKB(unittest.TestCase):
    """`sky_kb` holds skills and no project knowledge (D-20).

    A run pointed at it would have a library and nothing to work on — and
    would then be one write away from putting this project's material into
    everybody's library. So it is reached ALONGSIDE the task KB, never
    instead of it, and `resolve` will not return it under any argument.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "work" / "product").mkdir(parents=True, exist_ok=True)
        self.m = a_map(self.tmp, sky_kb={
            "purpose": "the shared skill catalogue",
            "mcp_url": "https://kb.example/mcp/", "tenant_code": "DEMO0002",
            "ontology": "sky_skill", "privacy": "work", "pat_env": "SKY_PAT_TEAM",
            "kind": "catalogue"})

    def test_the_catalogue_is_reachable_by_its_own_accessor(self):
        self.assertEqual(self.m.catalogue().name, "sky_kb")
        self.assertTrue(self.m.catalogue().is_catalogue)

    def test_a_task_still_resolves_to_a_task_kb(self):
        self.assertEqual(self.m.resolve(self.tmp / "work" / "product").name, "team_kb")

    def test_resolve_never_returns_the_catalogue_even_with_an_override(self):
        with self.assertRaises(NoKBForPath) as caught:
            self.m.resolve(self.tmp / "work" / "product", override="sky_kb")
        self.assertIn("not a task knowledge base", str(caught.exception))

    def test_a_writable_catalogue_is_refused(self):
        """A writable shared library is how one project's work reaches everyone."""
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp, bad={
                "purpose": "x", "mcp_url": "https://kb.example/mcp/",
                "tenant_code": "DEMO0002", "ontology": "sky_skill",
                "privacy": "work", "kind": "catalogue", "write": True})
        self.assertIn("write", str(caught.exception))

    def test_a_default_catalogue_is_refused(self):
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp, bad={
                "purpose": "x", "mcp_url": "https://kb.example/mcp/",
                "tenant_code": "DEMO0002", "ontology": "sky_skill",
                "privacy": "work", "kind": "catalogue", "default": True})
        self.assertIn("never the KB a task resolves to", str(caught.exception))

    def test_two_catalogues_is_an_error(self):
        """There is one shared skill library, not several."""
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp,
                  sky_kb={"purpose": "x", "mcp_url": "https://kb.example/mcp/",
                          "tenant_code": "DEMO0002", "ontology": "sky_skill",
                          "privacy": "work", "kind": "catalogue"},
                  other={"purpose": "x", "mcp_url": "https://kb.example/mcp/",
                         "tenant_code": "AAAA1111", "ontology": "sky_skill",
                         "privacy": "work", "kind": "catalogue"})
        self.assertIn("one shared skill library", str(caught.exception))

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(KBMapError) as caught:
            a_map(self.tmp, bad={
                "purpose": "x", "mcp_url": "https://kb.example/mcp/",
                "tenant_code": "AAAA1111", "ontology": "x", "privacy": "work",
                "kind": "library"})
        self.assertIn("'task' or 'catalogue'", str(caught.exception))

    def test_a_map_with_no_catalogue_is_ordinary(self):
        """Skill discovery is optional; everything else must still work."""
        self.assertIsNone(a_map(Path(tempfile.mkdtemp())).catalogue())
