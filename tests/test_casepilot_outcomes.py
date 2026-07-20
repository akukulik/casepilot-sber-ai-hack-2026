"""Deterministic outcome tests for the four CasePilot demo scenarios."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from casepilot.runtime import RuntimeStore, execute_plan, review_plan


ROOT = Path(__file__).resolve().parents[1]


def step(
    index: int,
    action: str,
    required_inputs: list[str],
    *,
    expertise_type: str | None = None,
    failure_action: str = "manual_review",
) -> dict[str, Any]:
    return {
        "step_id": f"step_{index}",
        "order": index,
        "action_type": "expertise" if expertise_type else "check",
        "action": action,
        "description": f"Детерминированный тест шага {action}.",
        "expertise_type": expertise_type,
        "required_inputs": required_inputs,
        "expected_result": "Структурированный mock-результат.",
        "success_condition": "Результат получен.",
        "failure_action": failure_action,
        "status": "pending",
    }


def plan(case_id: str, expertise_type: str, expertise_inputs: list[str], failure: str) -> dict[str, Any]:
    steps = [
        step(1, "check_account_state", ["case_id", "account_id"]),
        step(
            2,
            "request_expertise",
            expertise_inputs,
            expertise_type=expertise_type,
            failure_action=failure,
        ),
        step(
            3,
            "check_account_closure_eligibility",
            ["case_id", "account_id", "previous_results"],
        ),
    ]
    return {
        "case_id": case_id,
        "case_summary": "Синтетический тестовый кейс закрытия дебетового счёта.",
        "identified_problem": {
            "type": "test_blocker",
            "description": "Проверяемый синтетический блокер.",
            "evidence": ["synthetic test evidence"],
        },
        "similar_cases_used": [
            {
                "case_id": "HIST-DC-001" if case_id == "VAL-DC-002" else "HIST-DC-003",
                "similarity_score": 0.8,
                "useful_pattern": "Релевантная историческая стратегия.",
            }
        ],
        "proposed_plan": steps,
        "required_expertises": [
            {
                "expertise_type": expertise_type,
                "reason": "Требуется проверка причины блокировки.",
                "planned_step_id": "step_2",
            }
        ],
        "confidence": {"level": "high", "score": 0.8, "reason": "Сильное совпадение."},
        "open_questions": (
            ["restriction_reference"] if case_id == "VAL-DC-004" else []
        ),
        "requires_employee_approval": True,
        "recommended_next_action": "approve_plan",
    }


def run_case(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    store = RuntimeStore(root)
    plan_id = f"PLAN-{payload['case_id']}-001"
    store.seed_plan(plan_id, 1, payload)
    approved = review_plan(
        store,
        {
            "case_id": payload["case_id"],
            "plan_id": plan_id,
            "plan_version": 1,
            "decision": "approve_plan",
            "employee_id": "EMP-DEMO-001",
            "comment": "Детерминированный тест.",
        },
    )
    assert approved["status"] == "approved"
    return execute_plan(store, plan_id, 1)


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="casepilot-outcomes-"))
    try:
        shutil.copytree(ROOT / "data", root / "data")
        shutil.copytree(ROOT / "schemas", root / "schemas")
        shutil.rmtree(root / "data" / "runtime")

        balance_inputs = [
            "case_id",
            "account_id",
            "ledger_balance",
            "available_balance",
            "fee_events",
        ]
        restriction_inputs = [
            "case_id",
            "account_id",
            "restriction_flags",
            "restriction_reference",
            "restriction_status",
        ]
        success = run_case(
            root,
            plan("VAL-DC-002", "account_balance_analysis", balance_inputs, "manual_review"),
        )
        assert success["execution_status"] == "completed"
        assert success["closure_eligibility"]["eligible"] is True
        assert success["remaining_blockers"] == []
        assert success["recommended_next_action"] == "approve_case_closure"

        manual = run_case(
            root,
            plan("VAL-DC-003", "account_restriction_check", restriction_inputs, "manual_review"),
        )
        assert manual["execution_status"] == "manual_review"
        assert manual["closure_eligibility"]["eligible"] is False
        assert manual["recommended_next_action"] == "perform_manual_review"
        assert manual["steps"][-1]["result"]["result_code"] == "manual_legal_review_required"
        assert len(manual["steps"]) == 2

        waiting = run_case(
            root,
            plan(
                "VAL-DC-004",
                "account_restriction_check",
                restriction_inputs,
                "request_information",
            ),
        )
        assert waiting["execution_status"] == "waiting_for_information"
        assert waiting["closure_eligibility"]["eligible"] is False
        assert waiting["recommended_next_action"] == "request_missing_information"
        assert waiting["missing_fields"] == ["restriction_reference"]
        assert waiting["steps"][-1]["missing_fields"] == ["restriction_reference"]
        assert len(waiting["steps"]) == 2
        waiting_plan = RuntimeStore(root).plan("PLAN-VAL-DC-004-001", 1)
        assert waiting_plan and waiting_plan["status"] == "failed"

        print(
            json.dumps(
                {
                    "VAL-DC-002": success["execution_status"],
                    "VAL-DC-003": manual["execution_status"],
                    "VAL-DC-004": waiting["execution_status"],
                },
                ensure_ascii=False,
            )
        )
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
