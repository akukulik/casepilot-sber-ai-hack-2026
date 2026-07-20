---
name: validate_scenario_draft
description: Independently validate one CasePilot scenario draft against evidence, allowlists, conflicts, schemas, and offline replay.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
dependencies: [jsonschema]
timeout_sec: 60
---

# Validate Scenario Draft

Validate one `draft_id`. A passing result becomes
`ready_for_expert_review`, not `approved`. Fail closed on missing evidence,
unknown actions, unknown expertises, conflicts, or replay pass rate below 0.8.
