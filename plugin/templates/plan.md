---
{
  "type": "plan",
  "schema_version": 1,
  "title": "Replace with the plan title",
  "analysis_id": "replace-with-stored-analysis-id",
  "steps": [
    {"id": "implement", "role": "developer", "description": "Replace with bounded work", "acceptance": ["Replace with an observable check"], "inputs": ["replace-with-stored-analysis-id"]},
    {"id": "review", "role": "reviewer", "description": "Review the change", "acceptance": ["Required findings are resolved"], "inputs": ["implement"]}
  ],
  "citations": [],
  "relates_to": []
}
---
# Plan

Replace placeholders. Return to `sky kb plan put --from - --analysis <analysis-id>`.
If any analysis question is OPEN, stop with its count and run /sky:decide first.

## Inputs
Cite knowledge as id:<record> and code as file:line. The runtime pins the analysis,
closing decisions and cited knowledge revisions plus checkout; do not supply pins,
stamps or stale. Unknown checkout currency remains explicit.

## Ordered work and review
Keep step ids unique. Roles are architect, developer, reviewer and security only.
Specify bounded descriptions, observable acceptance and inputs. Include the review
and security gates required by the workflow. A plan is not implementation admission.
Show/list compute stale and reasons from current inputs; re-plan after input changes.
