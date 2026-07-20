---
name: find_similar_cases
description: Filter synthetic historical CasePilot cases by topic and subtopic, rank them with BM25 plus explainable business signals, and return up to five resolved examples.
version: 0.4.0
type: script
runtime: python3
scripts:
  - name: find_similar_cases.py
    description: Rank historical cases for one validation-case JSON object.
permissions: []
when_to_use: Use after load_case to retrieve resolved examples before drafting a resolution plan.
timeout_sec: 20
---

# Find Similar Cases

Pass the validation-case object returned inside `load_case.case`:

```text
skill_exec(
  skill="find_similar_cases",
  script="find_similar_cases.py",
  args=[
    "--case-json",
    "{\"case_id\":\"VAL-DC-001\", ...}"
  ]
)
```

The script returns at most five historical results with `case_id`, normalized
`score`, a concise explanation, the complete source object in
`historical_case`, and the historical strategy fields needed by a later
planning step. It rejects input containing hidden solution fields.
For Chat orchestration compatibility, it also accepts the complete
`load_case` response envelope and unwraps its `case` field before ranking.

Retrieval first filters by exact topic and subtopic. If that produces no
candidates, it falls back to topic-only and finally to all history. Candidates
are ranked by BM25 text similarity (0.35), closure reason (0.45),
product-type overlap (0.15), and priority (0.05).
The local `casepilot_data_dir.txt` locator identifies the canonical synthetic
dataset; `CASEPILOT_DATA_DIR` or `--data-dir` may override it.
