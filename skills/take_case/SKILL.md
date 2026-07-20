---
name: take_case
description: Take a CasePilot validation case into a new independent run from only its case_id, retrieve up to three approved resolution scenarios with historical evidence, build a validated strategy, and return an employee-facing review card. Use automatically when a user provides a CasePilot case ID such as VAL-DC-002 or asks to take/open a case.
version: 0.3.0
type: extension
runtime: python3
entry: plugin.py
permissions: [tool, net, read_settings]
env_from_settings: [OPENROUTER_API_KEY]
dependencies: [jsonschema]
when_to_use: Use as the primary operator entry point instead of asking the user to call load_case, find_case_scenarios, or build_resolution_plan separately.
timeout_sec: 180
---

# Take Case

Call `take_case(case_id="...")` when the employee supplies a CasePilot ID.
The Skill creates a new `run_id`, loads the case, ranks approved scenarios,
builds a plan, stores its runtime wrapper, and returns an operator view. It
never approves or executes the plan. Repeated use of the same case ID creates
another independent run without overwriting earlier results.

Use the separate `open_latest_case_run` tool only when the employee explicitly
asks to reopen the latest run without a new LLM call. Never use it for a bare
case ID.

In Chat, show only `operator_message`, not service JSON, prompts, traces, or
stack errors. Then wait for exactly one employee command:

- `Подтверждаю` → `approve_plan`;
- `Изменить: <комментарий>` → `request_change`;
- `Беру вручную` → `manual_review`.

Use `EMP-DEMO-001` for the MVP. Resolve `plan_id` and `plan_version` from the
latest `take_case` result; do not ask the employee to repeat them.
