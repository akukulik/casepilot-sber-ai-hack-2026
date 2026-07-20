---
name: load_case
description: Load one synthetic CasePilot validation case by case_id and return structured JSON.
version: 0.2.0
type: script
runtime: python3
scripts:
  - name: load_case.py
    description: Load a validation case by ID.
permissions: []
when_to_use: Use as the first CasePilot step when an employee provides a validation case_id.
timeout_sec: 20
---

# Load Case

Run with:

```text
skill_exec(
  skill="load_case",
  script="load_case.py",
  args=["VAL-DC-001"]
)
```

The script returns a JSON object with `status`, `case_id`, and `case`. A missing
case is a structured `not_found` result, not an exception. It reads only
`validation_cases.json` and never exposes historical resolutions. Its local
`casepilot_data_dir.txt` locator identifies the canonical synthetic dataset;
`CASEPILOT_DATA_DIR` or `--data-dir` may override it.
