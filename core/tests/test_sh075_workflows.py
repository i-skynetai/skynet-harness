"""Workflow validation against fixture policies; no host or session transport."""
import copy
import unittest

from sky import workflows


def policy(steps=None):
    return {"roles": {name: {} for name in ("architect", "developer", "reviewer", "security")},
            "actions": {"push": {"outward": True}, "danger": {"never": True}},
            "workflows": {"feature": copy.deepcopy(workflows.FEATURE if steps is None else steps)}}


class Validation(unittest.TestCase):
    def refuses(self, steps, message, **kwargs):
        with self.assertRaisesRegex(workflows.WorkflowError, message):
            workflows.validate(policy(steps), **kwargs)

    def test_feature_fixture_has_context_duplicates_gates_developer_and_print_ship(self):
        result = workflows.validate(policy())["feature"]
        self.assertEqual(result.steps[0]["operation"], "context")
        self.assertEqual([step["capability"] for step in result.steps if "capability" in step], ["tickets", "prs", "kb"])
        self.assertEqual([step["agent"] for step in result.steps if step.get("gate")], ["architect", "reviewer", "security"])
        self.assertEqual(result.steps[-1]["operation"], "ship")

    def test_unknown_agent_names_step(self):
        self.refuses([{"id": "build", "agent": "unknown"}], "step build.*unknown agent")

    def test_unknown_session_names_step_even_when_optional(self):
        self.refuses([{"id": "remote", "session": "unknown", "optional": True}], "step remote.*unknown session")

    def test_registered_session_and_known_hand_validate(self):
        workflows.validate(policy([{"id": "read", "session": "review"}, {"id": "hand", "hand": "claude"}]), sessions={"review"})

    def test_unknown_hand_refused(self):
        self.refuses([{"id": "read", "hand": "unknown"}], "step read.*unknown hand")

    def test_cycle_refused_with_step(self):
        self.refuses([{"id": "a", "agent": "architect", "after": ["b"]}, {"id": "b", "agent": "developer"}], "step .*cycle")

    def test_duplicate_step_id_refused(self):
        self.refuses([{"id": "a", "agent": "architect"}, {"id": "a", "agent": "developer"}], "step a.*duplicate")

    def test_outward_or_never_target_refused(self):
        for action in ("push", "danger"):
            self.refuses([{"id": "publish", "hand": action}], "step publish.*outward")

    def test_unknown_action_field_cannot_run_publication(self):
        self.refuses([{"id": "publish", "action": "push"}], "step publish.*unknown")

    def test_dependencies_must_exist_and_flags_are_boolean(self):
        self.refuses([{"id": "a", "agent": "architect", "after": ["absent"]}], "step a.*unknown dependency")
        self.refuses([{"id": "a", "agent": "architect", "gate": "true"}], "step a.*boolean")

    def test_validated_workflow_does_not_alias_input(self):
        body = policy()
        result = workflows.validate(body)["feature"]
        body["workflows"]["feature"][0]["operation"] = "push"
        self.assertEqual(result.steps[0]["operation"], "context")
