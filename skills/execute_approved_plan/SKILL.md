---
name: execute_approved_plan
description: Sequentially execute an approved CasePilot plan using only four deterministic mock Skills.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 60
---

# Execute Approved Plan

Requires the current plan version in `approved` state. Execution is sequential,
audited, read-only, and stops on HITL conditions. It never closes an account or
sends a client message.

In Chat, show compact progress (`Шаг N из M — выполнен/остановлен`) and finish
with: what was checked, resolved blockers, remaining blockers, closure
eligibility, and the employee's next action. Do not show stack traces or
internal service JSON unless explicitly requested.
