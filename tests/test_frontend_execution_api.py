"""Integration checks for the thin CasePilot frontend execution adapter."""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import server  # noqa: E402
from casepilot.runtime import RuntimeStore  # noqa: E402


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
        "description": f"Шаг {index}: контролируемая проверка.",
        "expertise_type": expertise_type,
        "required_inputs": required_inputs,
        "expected_result": "Структурированный mock-результат.",
        "success_condition": "Результат получен.",
        "failure_action": failure_action,
        "status": "pending",
    }


def plan(
    case_id: str,
    expertise_type: str,
    expertise_inputs: list[str],
    failure_action: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_summary": "Синтетический план для frontend API.",
        "identified_problem": {
            "type": "frontend_test",
            "description": "Проверяемый синтетический блокер.",
            "evidence": ["synthetic evidence"],
        },
        "similar_cases_used": [
            {
                "case_id": "HIST-DC-001",
                "similarity_score": 0.8,
                "useful_pattern": "Проверенный синтетический сценарий.",
            }
        ],
        "proposed_plan": [
            step(1, "check_account_state", ["case_id", "account_id"]),
            step(
                2,
                "request_expertise",
                expertise_inputs,
                expertise_type=expertise_type,
                failure_action=failure_action,
            ),
            step(
                3,
                "check_account_closure_eligibility",
                ["case_id", "account_id", "previous_results"],
            ),
        ],
        "required_expertises": [
            {
                "expertise_type": expertise_type,
                "reason": "Нужна профильная проверка.",
                "planned_step_id": "step_2",
            }
        ],
        "confidence": {"level": "high", "score": 0.8, "reason": "Тест."},
        "open_questions": [],
        "requires_employee_approval": True,
        "recommended_next_action": "approve_plan",
    }


def wait_terminal(execution_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        execution = server.execution_by_id(execution_id)
        if execution and execution.get("execution_status") != "executing":
            dto = server.execution_dto(execution)
            if dto.get("recommendation_status") != "generating":
                return dto
        time.sleep(0.01)
    raise AssertionError("execution did not finish")


def seed(store: RuntimeStore, case_id: str, payload: dict[str, Any]) -> tuple[str, int]:
    run = store.start_run(case_id)
    plan_id = f"PLAN-{run['run_id']}"
    store.seed_plan(plan_id, 1, payload, run_id=run["run_id"])
    return plan_id, 1


def main() -> None:
    temporary = Path(tempfile.mkdtemp(prefix="casepilot-frontend-api-"))
    original_root, original_data = server.ROOT, server.DATA
    original_delays = server.PRESENTATION_DELAYS_ENABLED
    original_recommendation_llm = server.RECOMMENDATION_LLM_ENABLED
    try:
        shutil.copytree(PROJECT / "data", temporary / "data")
        shutil.copytree(PROJECT / "schemas", temporary / "schemas")
        shutil.rmtree(temporary / "data" / "runtime")
        server.ROOT = temporary
        server.DATA = temporary / "data"
        server.PRESENTATION_DELAYS_ENABLED = False
        server.RECOMMENDATION_LLM_ENABLED = False
        server.EXECUTION_THREADS.clear()

        store = RuntimeStore(temporary)
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

        # Successful approval and completed execution.
        completed_id, version = seed(
            store,
            "VAL-DC-002",
            plan("VAL-DC-002", "account_balance_analysis", balance_inputs, "manual_review"),
        )
        approved = server.approve_plan(
            completed_id,
            {"case_id": "VAL-DC-002", "plan_version": version},
        )
        assert approved["status"] == "approved"
        approvals = store.read("approvals")
        assert approvals[-1]["decision"] == "approve_plan"
        assert approvals[-1]["employee_id"] == "EMP-DEMO-001"
        started = server.start_execution(completed_id, version)
        completed = wait_terminal(started["execution_id"])
        assert completed["execution_status"] == "completed"
        assert all(item["status"] == "completed" for item in completed["steps"])
        assert completed["requires_final_employee_approval"] is True
        assert completed["client_response_draft"]
        assert completed["recommendation_status"] == "fallback"
        assert completed["resolution_recommendation"]["decision_code"] == (
            "APPROVE_ACCOUNT_CLOSURE"
        )
        assert completed["resolution_recommendation"]["key_findings"]
        assert completed["resolution_recommendation"]["employee_actions"]
        assert "safety_notice" not in completed

        # Double launch returns the same persisted execution.
        repeated = server.start_execution(completed_id, version)
        assert repeated["execution_id"] == completed["execution_id"]
        assert len(server.executions_for_plan(completed_id, version)) == 1

        # Reopening a terminal case reuses plan content in a fresh proposed run.
        reopened = server.get_or_create_case_analysis("VAL-DC-002")
        assert reopened["status"] == "proposed"
        assert reopened["plan_id"] != completed_id
        assert reopened["latest_execution"] is None
        assert reopened["metadata"]["model_requests"] == 0
        assert reopened["plan"] == plan(
            "VAL-DC-002",
            "account_balance_analysis",
            balance_inputs,
            "manual_review",
        )

        # Approval error never creates an execution.
        error_id, _ = seed(
            store,
            "VAL-DC-001",
            plan(
                "VAL-DC-001",
                "card_transaction_status_check",
                ["case_id", "account_id", "card_id", "authorization_events", "pending_operations"],
                "manual_review",
            ),
        )
        try:
            server.approve_plan(
                error_id,
                {"case_id": "WRONG-CASE", "plan_version": 1},
            )
            raise AssertionError("invalid approval was accepted")
        except RuntimeError:
            pass
        assert server.executions_for_plan(error_id, 1) == []

        # Choosing manual resolution is persisted and blocks execution.
        manual_choice_id, _ = seed(
            store,
            "VAL-DC-001",
            plan(
                "VAL-DC-001",
                "card_transaction_status_check",
                ["case_id", "account_id", "card_id", "authorization_events", "pending_operations"],
                "manual_review",
            ),
        )
        manual_choice = server.take_plan_manual(
            manual_choice_id,
            {
                "case_id": "VAL-DC-001",
                "plan_version": 1,
                "comment": "Оператор выбрал самостоятельное решение кейса.",
            },
        )
        assert manual_choice["status"] == "manual_review"
        manual_approval = store.read("approvals")[-1]
        assert manual_approval["decision"] == "manual_review"
        assert manual_approval["outcome"] == "manual_review"
        assert manual_approval["employee_id"] == "EMP-DEMO-001"
        assert server.plan_by_identity(manual_choice_id, 1)["status"] == "manual_review"
        assert server.executions_for_plan(manual_choice_id, 1) == []

        # Waiting for missing information.
        waiting_id, _ = seed(
            store,
            "VAL-DC-004",
            plan(
                "VAL-DC-004",
                "account_restriction_check",
                restriction_inputs,
                "request_information",
            ),
        )
        server.approve_plan(waiting_id, {"case_id": "VAL-DC-004", "plan_version": 1})
        waiting = wait_terminal(server.start_execution(waiting_id, 1)["execution_id"])
        assert waiting["execution_status"] == "waiting_for_information"
        assert waiting["missing_fields"] == ["Номер документа-основания ограничения"]
        assert waiting["resolution_recommendation"]["decision_code"] == (
            "REQUEST_INFORMATION"
        )

        # Manual review stop.
        manual_id, _ = seed(
            store,
            "VAL-DC-003",
            plan(
                "VAL-DC-003",
                "account_restriction_check",
                restriction_inputs,
                "manual_review",
            ),
        )
        server.approve_plan(manual_id, {"case_id": "VAL-DC-003", "plan_version": 1})
        manual = wait_terminal(server.start_execution(manual_id, 1)["execution_id"])
        assert manual["execution_status"] == "manual_review"
        assert manual["resolution_recommendation"]["decision_code"] == "MANUAL_REVIEW"

        # Presenter merges pending steps and never exposes raw stack/errors.
        raw = {
            "execution_id": "EXE-PRESENTER",
            "run_id": "RUN-PRESENTER",
            "case_id": "VAL-DC-001",
            "plan_id": error_id,
            "plan_version": 1,
            "execution_status": "executing",
            "started_at": "2026-07-19T00:00:00+00:00",
            "completed_at": None,
            "steps": [
                {
                    "step_id": "step_1",
                    "order": 1,
                    "action": "check_account_state",
                    "status": "failed",
                    "error": "secret internal stack trace / API_KEY",
                }
            ],
            "resolved_blockers": [],
            "remaining_blockers": [],
        }
        dto = server.execution_dto(raw)
        assert len(dto["steps"]) == 3
        assert dto["steps"][0]["status"] == "failed"
        assert dto["steps"][1]["status"] == "pending"
        assert "stack" not in str(dto).lower()
        assert "api_key" not in str(dto).lower()

        compact = server.compact_recommendation_dto(
            {
                "title": "Длинный заголовок " * 20,
                "summary": "Подробное повторение кейса " * 50,
                "key_findings": [
                    {"finding": "Факт " * 100, "source_step_id": "step_1", "result_code": "ok"}
                ] * 8,
                "remaining_risks": ["Риск " * 100] * 8,
                "employee_actions": ["Действие " * 100] * 8,
                "client_response_draft": "Ответ " * 200,
                "confidence": {"level": "medium", "score": 0.7, "reason": "Тест"},
                "decision_code": "TEST",
                "requires_employee_approval": True,
            }
        )
        assert len(compact["summary"]) <= 281
        assert len(compact["key_findings"]) == 4
        assert len(compact["remaining_risks"]) == 3
        assert len(compact["employee_actions"]) == 3

        server.PRESENTATION_PROGRESS["EXE-PRESENTER"] = {
            "started_at": time.monotonic() - 7,
            "durations": [5, 10, 5],
            "terminal_status": "completed",
        }
        progressing = server.execution_dto(raw)
        assert progressing["execution_status"] == "executing"
        assert progressing["steps"][0]["status"] == "failed"
        assert progressing["steps"][1]["status"] == "executing"
        assert progressing["steps"][2]["status"] == "pending"
        server.PRESENTATION_PROGRESS.clear()

        source = (PROJECT / "frontend" / "app.js").read_text(encoding="utf-8")
        assert "button.disabled = true" in source
        assert "terminalExecutionStatuses.has" in source
        assert "setTimeout(resolve, 1000)" in source
        assert "renderExecution(execution)" in source
        assert "Редактировать ответ" in source
        assert "Закрыть кейс" in source
        assert "Основания и ограничения" in source
        assert "<span>Ответ клиенту</span>" in source
        assert "Проект ответа клиенту" not in source
        assert "Реальные банковские операции" not in source
        assert "CasePilot выполнил только синтетические проверки" not in source

        print("PASS: frontend approval, execution, DTO, duplicate guard, and polling")
    finally:
        server.ROOT, server.DATA = original_root, original_data
        server.PRESENTATION_DELAYS_ENABLED = original_delays
        server.RECOMMENDATION_LLM_ENABLED = original_recommendation_llm
        shutil.rmtree(temporary)


if __name__ == "__main__":
    main()
