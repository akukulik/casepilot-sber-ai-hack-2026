"""Create the bounded persisted CasePilot demonstration run."""

from __future__ import annotations

import json
from pathlib import Path

from casepilot.runtime import RuntimeStore, execute_plan, review_plan


ROOT = Path(__file__).resolve().parents[1]
PLAN_ID = "PLAN-VAL-DC-001-001"


def main() -> None:
    store = RuntimeStore(ROOT)
    plan = json.loads(
        (ROOT / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json").read_text(encoding="utf-8")
    )
    store.seed_plan(PLAN_ID, 1, plan)
    record = store.plan(PLAN_ID, 1)
    if record is None:
        raise RuntimeError("seeded plan is missing")
    if record["status"] == "proposed":
        reviewed = review_plan(
            store,
            {
                "case_id": "VAL-DC-001",
                "plan_id": PLAN_ID,
                "plan_version": 1,
                "decision": "approve_plan",
                "employee_id": "EMP-DEMO-001",
                "comment": "Подтверждаю план для контролируемого mock-запуска.",
            },
        )
        if reviewed["status"] != "approved":
            raise RuntimeError(f"approval failed: {reviewed}")
    result = execute_plan(store, PLAN_ID, 1)
    if result.get("execution_status") != "completed":
        raise RuntimeError(f"execution failed: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
