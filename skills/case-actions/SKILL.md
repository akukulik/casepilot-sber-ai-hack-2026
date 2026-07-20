---
name: case-actions
description: Execute one of five strictly allow-listed, deterministic CasePilot mock actions for an approved synthetic case plan.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 30
---

# CasePilot Case Actions

Use only for an employee-approved synthetic plan.

The registered tool aliases are `wait_settlement`, `draft_postclose_instr`,
`collect_compliance`, `match_cash_surplus`, and `draft_resolution`. They map
to the longer action identifiers stored in resolution plans.

The tools record mock outcomes for waiting, instructions, evidence collection,
cash-surplus matching, and resolution drafting. They never connect to banking
systems, move money, change products, or contact a client.
