---
name: review_resolution_plan
description: Record an employee decision for the current CasePilot plan version.
version: 0.1.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool]
timeout_sec: 30
---

# Review Resolution Plan

Use for `approve_plan`, one `request_change` on version 1, or `manual_review`.
The employee ID for the MVP is `EMP-DEMO-001`. A second change request on
version 2 routes the case to `manual_review` and never creates version 3.

In CasePilot Chat, map short commands using the latest plan returned by
`take_case`: `Подтверждаю` → `approve_plan`,
`Изменить: <комментарий>` → `request_change`, and
`Беру вручную` → `manual_review`.
