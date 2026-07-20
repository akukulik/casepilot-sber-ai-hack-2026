"""End-to-end deterministic test for one non-closure scenario."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from casepilot.runtime import RuntimeStore, execute_plan, review_plan
from skills.find_case_scenarios.scripts.find_case_scenarios import (
    find_case_scenarios,
    load_runtime_scenarios,
)


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    validation = json.loads((ROOT / "data" / "validation_cases.json").read_text())
    history = json.loads((ROOT / "data" / "historical_cases.json").read_text())
    case = next(item for item in validation if item["case_id"] == "VAL-DC-016")
    retrieval = find_case_scenarios(
        case, load_runtime_scenarios(ROOT / "data"), history, limit=3
    )
    require(retrieval["filter_stage"] == "exact_topic_and_subtopic", "wrong filter")
    require(
        retrieval["results"][0]["scenario_id"] == "SCN-DC-RECURRING-TIMING",
        f"wrong scenario: {retrieval['results'][0]['scenario_id']}",
    )

    scenario = retrieval["results"][0]
    plan = {
        "case_id": "VAL-DC-016",
        "case_summary": "Спор по регулярному платежу после отмены подписки.",
        "identified_problem": {
            "type": "recurring_payment_wrong_rail",
            "description": "Нужно определить платёжный rail и момент отмены.",
            "evidence": ["service_issue_code=RECURRING_PAYMENT_WRONG_RAIL"],
        },
        "scenarios_used": [
            {
                "scenario_id": scenario["scenario_id"],
                "similarity_score": scenario["score"],
                "useful_pattern": scenario["scenario"]["description"],
                "source_case_ids": scenario["scenario"]["source_case_ids"],
            }
        ],
        "proposed_plan": [
            {
                "step_id": "step_1",
                "order": 1,
                "action_type": "expertise",
                "action": "request_expertise",
                "description": "Определить rail и статус регулярного соглашения.",
                "expertise_type": "recurring_payment_check",
                "required_inputs": ["merchant"],
                "expected_result": "Машинный result_code проверки регулярного платежа.",
                "success_condition": "Получен допустимый result_code.",
                "failure_action": "request_information",
                "status": "pending",
            },
            {
                "step_id": "step_2",
                "order": 2,
                "action_type": "case_action",
                "action": "prepare_resolution_decision",
                "description": "Подготовить решение для подтверждения сотрудником.",
                "expertise_type": None,
                "required_inputs": ["case_id", "previous_results"],
                "expected_result": "Синтетический черновик решения.",
                "success_condition": "Черновик сформирован без банковских изменений.",
                "failure_action": "manual_review",
                "status": "pending",
            },
        ],
        "required_expertises": [
            {
                "expertise_type": "recurring_payment_check",
                "reason": "Нужно определить rail и статус отмены.",
                "planned_step_id": "step_1",
            }
        ],
        "confidence": {
            "level": "medium",
            "score": 0.72,
            "reason": "Сценарий совпадает по тематике и типу проблемы.",
        },
        "open_questions": [],
        "requires_employee_approval": True,
        "recommended_next_action": "approve_plan",
    }
    schema = json.loads((ROOT / "schemas" / "resolution_plan.schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(plan))
    require(not errors, f"plan schema errors: {[item.message for item in errors]}")

    temp = Path(tempfile.mkdtemp(prefix="casepilot-extended-"))
    try:
        shutil.copytree(ROOT / "data", temp / "data")
        shutil.copytree(ROOT / "schemas", temp / "schemas")
        shutil.rmtree(temp / "data" / "runtime", ignore_errors=True)
        store = RuntimeStore(temp)
        run = store.start_run("VAL-DC-016")
        plan_id = "PLAN-VAL-DC-016-E2E"
        store.seed_plan(plan_id, 1, plan, run_id=run["run_id"])
        approval = review_plan(
            store,
            {
                "case_id": "VAL-DC-016",
                "plan_id": plan_id,
                "plan_version": 1,
                "decision": "approve_plan",
                "employee_id": "EMP-DEMO-001",
                "comment": "Synthetic MVP extended scenario test.",
            },
        )
        require(approval["status"] == "approved", f"approval failed: {approval}")
        execution = execute_plan(store, plan_id, 1)
        require(execution["execution_status"] == "completed", str(execution))
        require(len(execution["steps"]) == 2, "not all steps executed")
        require(
            execution["steps"][0]["result"]["result_code"] == "CANCELLATION_VALID",
            "expertise result was not accepted",
        )
        require(
            execution["steps"][1]["result"]["result_code"]
            == "resolution_decision_drafted",
            "case action did not complete",
        )
        require(
            execution["recommended_next_action"] == "employee_review_resolution",
            "non-closure flow returned closure action",
        )
    finally:
        shutil.rmtree(temp)

    print(
        "PASS: VAL-DC-016 -> recurring scenario -> expertise -> "
        "mock resolution decision"
    )


if __name__ == "__main__":
    main()
