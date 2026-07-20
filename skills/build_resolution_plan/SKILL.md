---
name: build_resolution_plan
description: Build and validate a read-only CasePilot resolution plan from a validation case, approved ranked scenarios with historical evidence, and the allowed expertise catalog.
version: 0.4.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool, net, read_settings]
env_from_settings: [OPENROUTER_API_KEY]
dependencies: [jsonschema]
when_to_use: Use after load_case and find_case_scenarios when all three input collections are ready and an employee needs a proposed plan.
timeout_sec: 180
---

# Build Resolution Plan

Call the registered structured tool with `case`, `scenarios`, and
`expertise_catalog` as native object/array arguments. Legacy `similar_cases`
remains accepted only for old test flows. For the single allowed
revision of version 1, also provide `revision_context`:

```text
build_resolution_plan(
  case={...},
  scenarios=[...],
  expertise_catalog=[...],
  revision_context={
    "previous_plan": {...},
    "employee_comment": "..."
  }
)
```

The Skill calls only `z-ai/glm-5.2` with medium reasoning and low temperature.
It validates the response against its JSON Schema and CasePilot invariants. If
validation fails, it makes one repair request; a second invalid result returns
a controlled error. It never loads case files, executes plan steps, changes
source case data, or calls an expertise. On success it stores the plan only in
the local runtime wrapper and returns `plan_id`, `plan_version`, and status.

Plans use only `check_account_state`, `check_pending_operations`,
`request_expertise`, and `check_account_closure_eligibility`. Version metadata
is stored by the runtime wrapper, not inside the plan payload.

On success the tool returns the technical plan JSON followed by a compact,
non-secret metadata object with the model, reasoning effort, and request count.

In Chat, do not dump the technical JSON unless explicitly asked. Present:
case ID/topic, short problem understanding, key evidence, the strongest
scenario, numbered steps, required expertise, confidence, and the three employee
choices: approve, request one change, or manual review.
