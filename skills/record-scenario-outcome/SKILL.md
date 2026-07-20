---
name: record_scenario_outcome
description: Record one expert-validated successful manual or corrected-plan outcome as eligible evidence for CasePilot scenario learning.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
dependencies: [jsonschema]
timeout_sec: 60
---

# Record Scenario Outcome

Use only after a synthetic validation case is successfully resolved and
`EMP-DEMO-001` verifies the result. A `manual_review` status alone is never
eligible evidence. Record actual allow-listed actions and catalog expertises.

This Skill creates a learning event; it does not create or publish a scenario.
