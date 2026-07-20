---
name: review_scenario_draft
description: Record the CasePilot expert decision for a validated scenario draft and publish only an explicitly approved draft.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
dependencies: [jsonschema]
timeout_sec: 60
---

# Review Scenario Draft

Use only after `validate_scenario_draft` returns
`ready_for_expert_review`. For the MVP the expert is `EMP-DEMO-001`.
`approve` publishes a runtime scenario version; `reject` closes the draft.
No autonomous or `/evolve` publication is permitted.
