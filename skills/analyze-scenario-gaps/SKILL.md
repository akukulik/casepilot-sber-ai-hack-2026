---
name: analyze_scenario_gaps
description: Analyze validated manual CasePilot resolutions, detect repeated gaps, and create non-published scenario drafts.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
dependencies: [jsonschema]
timeout_sec: 60
---

# Analyze Scenario Gaps

Use on demand to cluster successful, expert-validated manual resolutions.
Require at least three evidence events. Create only `draft` records; never
publish a scenario and never modify canonical historical or validation data.

After a draft is created, call `validate_scenario_draft` independently.
