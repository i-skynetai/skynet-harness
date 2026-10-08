"""Local rules state their match; no bridge or model is invoked."""
import unittest

from sky.dispatch import route
from sky.workflows import WorkflowError


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.rules = [{"id": "feature", "contains": ["implement"], "workflow": "feature"},
                      {"id": "review", "contains": ["review"], "agent": "reviewer"}]

    def test_workflow_selection_names_rule_and_reason(self):
        choice = route("Implement a cache", self.rules, {"feature": object()})
        self.assertEqual((choice["choice"], choice["target"], choice["rule"]), ("workflow", "feature", "feature"))
        self.assertIn("implement", choice["reason"])

    def test_agent_selection_with_registry(self):
        choice = route("Review cache", self.rules, {"feature": object()}, agents={"reviewer"})
        self.assertEqual(choice["choice"], "agent")

    def test_ambiguous_route_asks_instead_of_order_tiebreak(self):
        choice = route("implement then review", self.rules, {"feature": object()})
        self.assertEqual(choice["choice"], "ask")
        self.assertIn("ambiguous", choice["reason"])

    def test_missing_route_asks(self):
        self.assertEqual(route("Explain cache", self.rules, {"feature": object()})["choice"], "ask")

    def test_unknown_workflow_or_agent_refused(self):
        with self.assertRaises(WorkflowError):
            route("implement", self.rules, {})
        with self.assertRaises(WorkflowError):
            route("review", self.rules, {"feature": object()}, agents=set())

    def test_mapped_rules_supported_and_duplicate_ids_refused(self):
        self.assertEqual(route("review", {"review": {"contains": ["review"], "agent": "reviewer"}}, {})["rule"], "review")
        with self.assertRaises(WorkflowError):
            route("review", [self.rules[1], self.rules[1]], {})

    def test_remote_session_target_not_accepted(self):
        with self.assertRaises(WorkflowError):
            route("review", [{"id": "r", "contains": ["review"], "session": "remote"}], {})
