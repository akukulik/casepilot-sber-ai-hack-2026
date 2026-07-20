"""Deterministic runtime, review, and mock execution for CasePilot."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PLAN_STATUSES = {
    "proposed",
    "change_requested",
    "approved",
    "executing",
    "completed",
    "failed",
    "manual_review",
}
RUN_STATUSES = {
    "preparing",
    "proposed",
    "change_requested",
    "approved",
    "executing",
    "completed",
    "failed",
    "waiting_for_information",
    "replan_required",
    "manual_review",
}
EXECUTION_STATUSES = {
    "executing",
    "completed",
    "failed",
    "waiting_for_information",
    "replan_required",
    "manual_review",
}
DECISIONS = {"approve_plan", "request_change", "manual_review"}
ALLOWED_ACTIONS = {
    "check_account_state",
    "check_pending_operations",
    "request_expertise",
    "check_account_closure_eligibility",
    "wait_for_settlement",
    "record_post_closure_instruction",
    "collect_compliance_evidence",
    "match_collection_surplus",
    "prepare_resolution_decision",
}
CASE_ACTIONS = {
    "wait_for_settlement",
    "record_post_closure_instruction",
    "collect_compliance_evidence",
    "match_collection_surplus",
    "prepare_resolution_decision",
}


class MissingInputsError(ValueError):
    def __init__(self, fields: list[str]):
        self.fields = fields
        super().__init__("missing required expertise inputs: " + ", ".join(fields))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False, indent=2)
            target.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RuntimeStore:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir.resolve()
        self.runtime_dir = self.project_dir / "data" / "runtime"
        self.runs_path = self.runtime_dir / "runs.json"
        self.plans_path = self.runtime_dir / "plans.json"
        self.approvals_path = self.runtime_dir / "approvals.json"
        self.executions_path = self.runtime_dir / "executions.json"
        self.recommendations_path = self.runtime_dir / "recommendations.json"
        self.audit_path = self.runtime_dir / "audit_log.jsonl"
        self.ensure()

    def ensure(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        for path in (
            self.runs_path,
            self.plans_path,
            self.approvals_path,
            self.executions_path,
            self.recommendations_path,
        ):
            if not path.exists():
                atomic_write_json(path, [])
        self.audit_path.touch(exist_ok=True)
        self._migrate_legacy_runtime()

    def _migrate_legacy_runtime(self) -> None:
        plans = load_json(self.plans_path)
        approvals = load_json(self.approvals_path)
        executions = load_json(self.executions_path)
        runs = load_json(self.runs_path)
        if not all(isinstance(value, list) for value in (plans, approvals, executions, runs)):
            raise ValueError("runtime stores must contain JSON arrays")
        changed = False
        run_by_plan = {
            str(item.get("plan_id")): str(item.get("run_id"))
            for item in plans
            if item.get("plan_id") and item.get("run_id")
        }
        sequence_by_case: dict[str, int] = {}
        for run in runs:
            case_id = str(run.get("case_id") or "")
            try:
                sequence = int(str(run.get("run_id") or "").rsplit("-", 1)[-1])
            except ValueError:
                sequence = 0
            sequence_by_case[case_id] = max(sequence_by_case.get(case_id, 0), sequence)
        for plan_id in dict.fromkeys(
            str(item.get("plan_id")) for item in plans if item.get("plan_id")
        ):
            if plan_id in run_by_plan:
                continue
            related = [item for item in plans if str(item.get("plan_id")) == plan_id]
            case_id = str(related[0].get("case_id") or "")
            sequence = sequence_by_case.get(case_id, 0) + 1
            sequence_by_case[case_id] = sequence
            run_id = f"RUN-{case_id}-{sequence:04d}"
            run_by_plan[plan_id] = run_id
            current = max(related, key=lambda item: int(item.get("plan_version") or 0))
            runs.append(
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "run_number": sequence,
                    "status": current.get("status", "completed"),
                    "created_at": current.get("created_at") or utc_now(),
                    "updated_at": current.get("updated_at") or current.get("created_at") or utc_now(),
                    "legacy_plan_id": plan_id,
                }
            )
            changed = True
        for collection in (plans, approvals, executions):
            for item in collection:
                if not item.get("run_id") and item.get("plan_id") in run_by_plan:
                    item["run_id"] = run_by_plan[str(item["plan_id"])]
                    changed = True
        latest_execution_by_run: dict[str, dict[str, Any]] = {}
        for execution in executions:
            run_id = str(execution.get("run_id") or "")
            if run_id:
                latest_execution_by_run[run_id] = execution
        for run in runs:
            execution = latest_execution_by_run.get(str(run.get("run_id") or ""))
            execution_status = execution.get("execution_status") if execution else None
            if execution_status in RUN_STATUSES and run.get("status") != execution_status:
                run["status"] = execution_status
                run["updated_at"] = execution.get("completed_at") or run.get("updated_at") or utc_now()
                changed = True
        if changed:
            atomic_write_json(self.runs_path, runs)
            atomic_write_json(self.plans_path, plans)
            atomic_write_json(self.approvals_path, approvals)
            atomic_write_json(self.executions_path, executions)

    def read(self, name: str) -> list[dict[str, Any]]:
        path = getattr(self, f"{name}_path")
        value = load_json(path)
        if not isinstance(value, list):
            raise ValueError(f"{path.name} must contain a JSON array")
        return value

    def write(self, name: str, value: list[dict[str, Any]]) -> None:
        atomic_write_json(getattr(self, f"{name}_path"), value)

    def audit(self, event_type: str, **details: Any) -> dict[str, Any]:
        event = {"timestamp": utc_now(), "event_type": event_type, **details}
        forbidden = {"api_key", "system_prompt", "authorization"}
        if forbidden & set(event):
            raise ValueError("audit event contains a forbidden secret field")
        with self.audit_path.open("a", encoding="utf-8") as target:
            target.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        return event

    def current_plan(self, plan_id: str) -> dict[str, Any] | None:
        matches = [item for item in self.read("plans") if item.get("plan_id") == plan_id]
        return max(matches, key=lambda item: int(item["plan_version"])) if matches else None

    def current_plan_for_run(self, run_id: str) -> dict[str, Any] | None:
        matches = [item for item in self.read("plans") if item.get("run_id") == run_id]
        return max(matches, key=lambda item: int(item["plan_version"])) if matches else None

    def latest_run(self, case_id: str) -> dict[str, Any] | None:
        matches = [item for item in self.read("runs") if item.get("case_id") == case_id]
        return max(matches, key=lambda item: int(item["run_number"])) if matches else None

    def start_run(self, case_id: str) -> dict[str, Any]:
        runs = self.read("runs")
        number = max(
            (
                int(item.get("run_number") or 0)
                for item in runs
                if item.get("case_id") == case_id
            ),
            default=0,
        ) + 1
        record = {
            "run_id": f"RUN-{case_id}-{number:04d}",
            "case_id": case_id,
            "run_number": number,
            "status": "preparing",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "legacy_plan_id": None,
        }
        runs.append(record)
        self.write("runs", runs)
        self.audit(
            "case_run_started",
            run_id=record["run_id"],
            case_id=case_id,
            run_number=number,
        )
        return record

    def update_run_status(self, run_id: str, status: str) -> dict[str, Any]:
        if status not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        runs = self.read("runs")
        record = next((item for item in runs if item.get("run_id") == run_id), None)
        if record is None:
            raise ValueError("run not found")
        record["status"] = status
        record["updated_at"] = utc_now()
        self.write("runs", runs)
        return record

    def plan(self, plan_id: str, version: int) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.read("plans")
                if item.get("plan_id") == plan_id and item.get("plan_version") == version
            ),
            None,
        )

    def seed_plan(
        self,
        plan_id: str,
        plan_version: int,
        plan: dict[str, Any],
        *,
        run_id: str | None = None,
        supersedes_plan_version: int | None = None,
    ) -> dict[str, Any]:
        plans = self.read("plans")
        existing = next(
            (
                item
                for item in plans
                if item["plan_id"] == plan_id and item["plan_version"] == plan_version
            ),
            None,
        )
        if existing:
            return existing
        if run_id is None:
            latest = self.latest_run(plan["case_id"])
            run_id = (
                str(latest["run_id"])
                if latest and latest.get("status") == "preparing"
                else str(self.start_run(plan["case_id"])["run_id"])
            )
        record = {
            "run_id": run_id,
            "plan_id": plan_id,
            "case_id": plan["case_id"],
            "plan_version": plan_version,
            "plan": deepcopy(plan),
            "status": "proposed",
            "created_at": utc_now(),
            "supersedes_plan_version": supersedes_plan_version,
        }
        plans.append(record)
        self.write("plans", plans)
        self.audit(
            "plan_created",
            run_id=run_id,
            case_id=record["case_id"],
            plan_id=plan_id,
            plan_version=plan_version,
            status="proposed",
        )
        self.update_run_status(run_id, "proposed")
        return record

    def update_plan_status(self, plan_id: str, version: int, status: str) -> dict[str, Any]:
        if status not in PLAN_STATUSES:
            raise ValueError(f"unsupported plan status: {status}")
        plans = self.read("plans")
        record = next(
            (
                item
                for item in plans
                if item["plan_id"] == plan_id and item["plan_version"] == version
            ),
            None,
        )
        if record is None:
            raise ValueError("plan not found")
        record["status"] = status
        record["updated_at"] = utc_now()
        self.write("plans", plans)
        self.update_run_status(str(record["run_id"]), status)
        return record

    def recommendation_for_execution(self, execution_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.read("recommendations")
                if item.get("execution_id") == execution_id
            ),
            None,
        )

    def save_recommendation(
        self,
        execution: dict[str, Any],
        recommendation: dict[str, Any],
        *,
        status: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if status not in {"generated", "fallback"}:
            raise ValueError("unsupported recommendation status")
        recommendations = self.read("recommendations")
        existing = next(
            (
                item
                for item in recommendations
                if item.get("execution_id") == execution.get("execution_id")
            ),
            None,
        )
        if existing is not None:
            return existing
        schema = load_json(
            self.project_dir / "schemas" / "resolution_recommendation.schema.json"
        )
        errors = list(Draft202012Validator(schema).iter_errors(recommendation))
        if errors:
            raise ValueError(
                "invalid resolution recommendation: "
                + "; ".join(error.message for error in errors)
            )
        record = {
            "recommendation_id": f"REC-{len(recommendations) + 1:04d}",
            "run_id": execution["run_id"],
            "case_id": execution["case_id"],
            "plan_id": execution["plan_id"],
            "plan_version": execution["plan_version"],
            "execution_id": execution["execution_id"],
            "recommendation_version": 1,
            "status": status,
            "recommendation": deepcopy(recommendation),
            "metadata": deepcopy(metadata),
            "created_at": utc_now(),
        }
        recommendations.append(record)
        self.write("recommendations", recommendations)
        self.audit(
            "resolution_recommendation_created",
            run_id=record["run_id"],
            case_id=record["case_id"],
            plan_id=record["plan_id"],
            plan_version=record["plan_version"],
            execution_id=record["execution_id"],
            recommendation_id=record["recommendation_id"],
            recommendation_status=status,
            decision_code=recommendation["decision_code"],
            model_requests=metadata.get("model_requests", 0),
        )
        return record


def review_plan(store: RuntimeStore, payload: dict[str, Any]) -> dict[str, Any]:
    required = {"case_id", "plan_id", "plan_version", "decision", "employee_id", "comment"}
    missing = sorted(required - set(payload))
    if missing:
        return {"status": "invalid_input", "errors": [f"missing fields: {missing}"]}
    if payload["decision"] not in DECISIONS:
        return {"status": "invalid_input", "errors": ["unsupported decision"]}
    if payload["employee_id"] != "EMP-DEMO-001":
        return {"status": "invalid_input", "errors": ["employee_id must be EMP-DEMO-001"]}
    if payload["decision"] == "request_change" and not str(payload.get("comment") or "").strip():
        return {"status": "invalid_input", "errors": ["request_change requires comment"]}

    record = store.plan(str(payload["plan_id"]), int(payload["plan_version"]))
    if record is None:
        return {"status": "not_found", "errors": ["plan_id and plan_version were not found"]}
    if record["case_id"] != payload["case_id"]:
        return {"status": "conflict", "errors": ["case_id does not match plan"]}
    current = store.current_plan(record["plan_id"])
    if current is None or current["plan_version"] != record["plan_version"]:
        return {"status": "stale_plan", "errors": ["decision on an obsolete plan is forbidden"]}
    if record["status"] not in {"proposed", "change_requested"}:
        return {"status": "conflict", "errors": [f"plan status is {record['status']}"]}

    decision = payload["decision"]
    if decision == "request_change" and (
        record["plan_version"] >= 2 or record["status"] == "change_requested"
    ):
        record = store.update_plan_status(record["plan_id"], record["plan_version"], "manual_review")
        outcome = "manual_review"
        reason = "revision_limit_exceeded"
    elif record["status"] == "change_requested":
        return {
            "status": "conflict",
            "errors": ["version 1 already awaits creation of version 2"],
        }
    elif decision == "request_change":
        record = store.update_plan_status(record["plan_id"], record["plan_version"], "change_requested")
        outcome = "change_requested"
        reason = None
    elif decision == "approve_plan":
        record = store.update_plan_status(record["plan_id"], record["plan_version"], "approved")
        outcome = "approved"
        reason = None
    else:
        record = store.update_plan_status(record["plan_id"], record["plan_version"], "manual_review")
        outcome = "manual_review"
        reason = None

    approval = {
        "approval_id": f"APR-{len(store.read('approvals')) + 1:04d}",
        "run_id": record["run_id"],
        "case_id": record["case_id"],
        "plan_id": record["plan_id"],
        "plan_version": record["plan_version"],
        "decision": decision,
        "employee_id": payload["employee_id"],
        "comment": payload["comment"],
        "outcome": outcome,
        "reason": reason,
        "created_at": utc_now(),
    }
    approvals = store.read("approvals")
    approvals.append(approval)
    store.write("approvals", approvals)
    store.audit(
        "plan_reviewed",
        run_id=record["run_id"],
        case_id=record["case_id"],
        plan_id=record["plan_id"],
        plan_version=record["plan_version"],
        decision=decision,
        outcome=outcome,
        employee_id=payload["employee_id"],
        reason=reason,
    )
    result = {
        "status": outcome,
        "run_id": record["run_id"],
        "case_id": record["case_id"],
        "plan_id": record["plan_id"],
        "plan_version": record["plan_version"],
        "requires_revision": outcome == "change_requested",
    }
    if reason:
        result["reason"] = reason
    return result


def _validation_case(project_dir: Path, case_id: str) -> dict[str, Any]:
    cases = load_json(project_dir / "data" / "validation_cases.json")
    case = next((item for item in cases if item["case_id"] == case_id), None)
    if case is None:
        raise ValueError("case not found")
    return case


def _ids(case: dict[str, Any]) -> tuple[str, str]:
    card = next(item for item in case["products"] if item["product_type"] == "debit_card")
    account = next(item for item in case["products"] if item["product_type"] == "current_account")
    return card["product_id"], account["product_id"]


def check_account_state(project_dir: Path, case_id: str, account_id: str) -> dict[str, Any]:
    case = _validation_case(project_dir, case_id)
    _, expected_account = _ids(case)
    if account_id != expected_account:
        raise ValueError("account_id does not belong to case")
    account = next(item for item in case["products"] if item["product_id"] == account_id)
    system = case["synthetic_system_data"]
    return {
        "status": "ok",
        "result_code": "account_state_retrieved",
        "case_id": case_id,
        "account_id": account_id,
        "current_balance": system["ledger_balance"],
        "available_balance": system["available_balance"],
        "holds_amount": sum(
            float(item.get("amount") or 0)
            for item in system.get("authorization_events", [])
            if item.get("status") in {"active", "reversal_pending"}
        ),
        "restrictions": system.get("restriction_flags", []),
        "account_status": account["status"],
    }


def check_pending_operations(
    project_dir: Path, case_id: str, card_id: str, account_id: str
) -> dict[str, Any]:
    case = _validation_case(project_dir, case_id)
    expected_card, expected_account = _ids(case)
    if (card_id, account_id) != (expected_card, expected_account):
        raise ValueError("card_id or account_id does not belong to case")
    system = case["synthetic_system_data"]
    authorizations = system.get("authorization_events", [])
    pending = system.get("pending_operations", [])
    reversal_status = next(
        (item.get("status") for item in authorizations if item.get("status") == "reversal_pending"),
        "not_pending",
    )
    return {
        "status": "ok",
        "result_code": "pending_reversal_confirmed" if pending else "no_pending_operations",
        "case_id": case_id,
        "pending_operations": deepcopy(pending),
        "hold": deepcopy(authorizations[0]) if authorizations else None,
        "reversal_status": reversal_status,
        "checked_at": "2026-07-19T12:00:00+03:00",
    }


def request_expertise(
    project_dir: Path,
    approved_plan: dict[str, Any],
    case_id: str,
    expertise_type: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    catalog = load_json(project_dir / "data" / "expertise_catalog.json")
    expertise = next(
        (item for item in catalog if item["expertise_type"] == expertise_type),
        None,
    )
    if expertise is None:
        raise ValueError("expertise_type is not present in expertise_catalog")
    approved = {
        item["expertise_type"] for item in approved_plan.get("required_expertises", [])
    }
    if expertise_type not in approved:
        raise ValueError("expertise_type was not approved in the plan")
    missing = sorted(
        key
        for key in expertise["required_inputs"]
        if key not in inputs or inputs.get(key) is None or inputs.get(key) == ""
    )
    if missing:
        raise MissingInputsError(missing)
    if expertise_type == "card_transaction_status_check" and case_id == "VAL-DC-001":
        return {
            "status": "ok",
            "result_code": "active_hold_confirmed",
            "expertise_type": expertise_type,
            "case_id": case_id,
            "authorization_id": "SYN-AUTH-901",
            "operation_id": "SYN-OP-901",
            "reversal_status": "reversal_pending",
            "expected_release_at": "2026-07-21T23:59:59+03:00",
            "explanation": "Активный холд подтверждён; reversal обрабатывается штатно.",
        }
    case = _validation_case(project_dir, case_id)
    system = case["synthetic_system_data"]
    if expertise_type == "account_balance_analysis":
        correction_approved = any(
            item.get("status") == "technical_correction_approved"
            for item in system.get("fee_events", [])
        )
        if correction_approved:
            return {
                "status": "ok",
                "result_code": "zero_balance_confirmed",
                "expertise_type": expertise_type,
                "case_id": case_id,
                "corrected_ledger_balance": 0,
                "corrected_available_balance": 0,
                "resolved_blocker": "negative_balance",
                "explanation": "Одобренная техническая корректировка применена в mock-контуре; контрольный остаток равен нулю.",
            }
    if (
        expertise_type == "account_restriction_check"
        and system.get("restriction_status") == "ambiguous_legal_basis"
    ):
        return {
            "status": "ok",
            "result_code": "manual_legal_review_required",
            "expertise_type": expertise_type,
            "case_id": case_id,
            "restriction_reference": system.get("restriction_reference"),
            "explanation": "Основание ограничения неоднозначно; автоматическое решение запрещено, требуется юридическая проверка.",
        }
    result_code = expertise["possible_results"][0]
    return {
        "status": "ok",
        "result_code": result_code,
        "expertise_type": expertise_type,
        "case_id": case_id,
        "explanation": "Детерминированный синтетический результат.",
    }


def check_account_closure_eligibility(
    project_dir: Path,
    case_id: str,
    account_id: str,
    previous_results: list[dict[str, Any]],
) -> dict[str, Any]:
    _validation_case(project_dir, case_id)
    state = next(
        (item for item in previous_results if item.get("result_code") == "account_state_retrieved"),
        {},
    )
    pending = next(
        (item for item in previous_results if item.get("result_code") == "pending_reversal_confirmed"),
        {},
    )
    balance_expertise = next(
        (
            item
            for item in previous_results
            if item.get("result_code") == "zero_balance_confirmed"
        ),
        {},
    )
    blockers: list[str] = []
    if state.get("restrictions"):
        blockers.append("active_account_restriction")
    if float(state.get("current_balance") or 0) < 0 and not balance_expertise:
        blockers.append("negative_balance")
    if pending:
        blockers.append("active_authorization_hold")
    return {
        "status": "ok",
        "result_code": "closure_eligible" if not blockers else "closure_not_eligible",
        "case_id": case_id,
        "account_id": account_id,
        "eligible": not blockers,
        "remaining_blockers": blockers,
        "explanation": (
            "Синтетическая проверка не выявила препятствий."
            if not blockers
            else "Закрытие пока невозможно: " + ", ".join(blockers)
        ),
    }


def perform_case_action(
    project_dir: Path,
    case_id: str,
    action: str,
    previous_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute a synthetic, non-mutating case action from the strict allow-list."""
    if action not in CASE_ACTIONS:
        raise ValueError(f"case action {action!r} is not allowed")
    case = _validation_case(project_dir, case_id)
    result_codes = [str(item.get("result_code") or "") for item in previous_results]
    details = {
        "wait_for_settlement": (
            "settlement_wait_recorded",
            "Ожидание расчёта зафиксировано только в mock-исполнении.",
        ),
        "record_post_closure_instruction": (
            "post_closure_instruction_drafted",
            "Инструкция подготовлена как синтетический черновик и не отправлена в банк.",
        ),
        "collect_compliance_evidence": (
            "compliance_evidence_checklist_prepared",
            "Подготовлен синтетический перечень документов без раскрытия закрытых данных.",
        ),
        "match_collection_surplus": (
            "collection_match_review_prepared",
            "Подготовлена mock-сверка инкассационного излишка; проводка не создавалась.",
        ),
        "prepare_resolution_decision": (
            "resolution_decision_drafted",
            "Решение подготовлено для сотрудника; финансовые и клиентские действия не выполнялись.",
        ),
    }
    result_code, explanation = details[action]
    return {
        "status": "ok",
        "result_code": result_code,
        "case_id": case["case_id"],
        "action": action,
        "based_on_result_codes": result_codes,
        "mock_only": True,
        "requires_employee_approval": True,
        "explanation": explanation,
    }


def _step_inputs(case: dict[str, Any], prior: list[dict[str, Any]]) -> dict[str, Any]:
    card_id, account_id = _ids(case)
    system = case["synthetic_system_data"]
    result = {
        "case_id": case["case_id"],
        "client_id": case["client_id"],
        "customer_id": case["client_id"],
        "account_id": account_id,
        "card_id": card_id,
        "ledger_balance": system.get("ledger_balance"),
        "available_balance": system.get("available_balance"),
        "fee_events": system.get("fee_events", []),
        "authorization_events": system.get("authorization_events", []),
        "pending_operations": system.get("pending_operations", []),
        "restriction_flags": system.get("restriction_flags", []),
        "restriction_reference": system.get("restriction_reference"),
        "restriction_status": system.get("restriction_status"),
        "previous_results": prior,
    }
    transactions = system.get("transactions", [])
    first_transaction = transactions[0] if transactions and isinstance(transactions[0], dict) else {}
    refund = next(
        (
            item for item in transactions
            if isinstance(item, dict) and item.get("type") == "refund"
        ),
        {},
    )
    evidence = system.get("evidence", [])
    result.update(
        {
            "transaction_id": first_transaction.get("transaction_id"),
            "original_transaction_id": first_transaction.get("transaction_id"),
            "atm_id": first_transaction.get("atm_id"),
            "merchant": first_transaction.get("merchant"),
            "amount": abs(float(first_transaction.get("amount") or 0)),
            "claimed_amount": abs(float(first_transaction.get("amount") or 0)),
            "expected_refund_amount": abs(float(refund.get("amount") or 0)),
            "reason": system.get("service_issue_code"),
            "dispute_reason": system.get("service_issue_code"),
            "claim_type": system.get("service_issue_code"),
            "review_type": system.get("source_topic") or system.get("service_issue_code"),
            "evidence": evidence,
        }
    )
    return result


def _execute_step(
    project_dir: Path,
    plan: dict[str, Any],
    step: dict[str, Any],
    prior: list[dict[str, Any]],
) -> dict[str, Any]:
    case = _validation_case(project_dir, plan["case_id"])
    inputs = _step_inputs(case, prior)
    action = step["action"]
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"action {action!r} is not in the execution allowlist")
    if action == "check_account_state":
        return check_account_state(project_dir, case["case_id"], inputs["account_id"])
    if action == "check_pending_operations":
        return check_pending_operations(
            project_dir, case["case_id"], inputs["card_id"], inputs["account_id"]
        )
    if action == "request_expertise":
        expertise_inputs = {key: inputs.get(key) for key in step["required_inputs"]}
        return request_expertise(
            project_dir,
            plan,
            case["case_id"],
            str(step["expertise_type"]),
            expertise_inputs,
        )
    if action in CASE_ACTIONS:
        return perform_case_action(
            project_dir,
            case["case_id"],
            action,
            prior,
        )
    return check_account_closure_eligibility(
        project_dir, case["case_id"], inputs["account_id"], prior
    )


def execute_plan(store: RuntimeStore, plan_id: str, plan_version: int) -> dict[str, Any]:
    record = store.plan(plan_id, plan_version)
    if record is None:
        return {"status": "not_found", "errors": ["plan not found"]}
    current = store.current_plan(plan_id)
    if current is None or current["plan_version"] != plan_version:
        return {"status": "stale_plan", "errors": ["obsolete plan cannot be executed"]}
    if record["status"] != "approved":
        return {"status": "not_approved", "errors": ["plan status must be approved"]}

    schema = load_json(store.project_dir / "schemas" / "resolution_plan.schema.json")
    schema_errors = list(Draft202012Validator(schema).iter_errors(record["plan"]))
    if schema_errors:
        return {
            "status": "invalid_plan",
            "errors": [error.message for error in schema_errors],
        }
    steps = sorted(record["plan"]["proposed_plan"], key=lambda item: item["order"])
    if [item["order"] for item in steps] != list(range(1, len(steps) + 1)):
        return {"status": "invalid_plan", "errors": ["step order is not sequential"]}
    catalog = {
        item["expertise_type"]: set(item["required_inputs"])
        for item in load_json(store.project_dir / "data" / "expertise_catalog.json")
    }
    action_inputs = {
        "check_account_state": {"case_id", "account_id"},
        "check_pending_operations": {"case_id", "card_id", "account_id"},
        "check_account_closure_eligibility": {
            "case_id",
            "account_id",
            "previous_results",
        },
        **{action: {"case_id", "previous_results"} for action in CASE_ACTIONS},
    }
    for step in steps:
        action = step["action"]
        if action not in ALLOWED_ACTIONS:
            return {"status": "invalid_plan", "errors": [f"action {action!r} is forbidden"]}
        expected_inputs = (
            catalog.get(str(step.get("expertise_type")))
            if action == "request_expertise"
            else action_inputs.get(action)
        )
        if expected_inputs is None or set(step["required_inputs"]) != expected_inputs:
            return {
                "status": "invalid_plan",
                "errors": [f"required_inputs contract mismatch for {action!r}"],
            }

    execution = {
        "execution_id": f"EXE-{len(store.read('executions')) + 1:04d}",
        "run_id": record["run_id"],
        "case_id": record["case_id"],
        "plan_id": plan_id,
        "plan_version": plan_version,
        "execution_status": "executing",
        "started_at": utc_now(),
        "completed_at": None,
        "steps": [],
        "resolved_blockers": [],
        "remaining_blockers": [],
    }
    executions = store.read("executions")
    executions.append(execution)
    store.write("executions", executions)
    store.update_plan_status(plan_id, plan_version, "executing")
    store.audit(
        "execution_started",
        run_id=record["run_id"],
        case_id=record["case_id"],
        plan_id=plan_id,
        plan_version=plan_version,
        execution_id=execution["execution_id"],
    )

    prior: list[dict[str, Any]] = []
    expected_expertise_codes = {
        item["expertise_type"]: set(item["possible_results"])
        for item in load_json(store.project_dir / "data" / "expertise_catalog.json")
    }
    for step in steps:
        step_record = {
            "step_id": step["step_id"],
            "order": step["order"],
            "action": step["action"],
            "status": "executing",
            "started_at": utc_now(),
        }
        execution["steps"].append(step_record)
        store.write("executions", executions)
        store.audit(
            "execution_step_started",
            run_id=record["run_id"],
            execution_id=execution["execution_id"],
            step_id=step["step_id"],
            action=step["action"],
        )
        try:
            result = _execute_step(store.project_dir, record["plan"], step, prior)
            if step["action"] == "request_expertise":
                allowed_codes = expected_expertise_codes.get(str(step["expertise_type"]), set())
                if result.get("result_code") not in allowed_codes:
                    raise RuntimeError("expertise_result_deviation")
            prior.append(result)
            step_record.update(
                {"status": "completed", "completed_at": utc_now(), "result": result}
            )
            store.audit(
                "execution_step_completed",
                run_id=record["run_id"],
                execution_id=execution["execution_id"],
                step_id=step["step_id"],
                result_code=result.get("result_code"),
            )
            if result.get("result_code") in {
                "manual_legal_review_required",
                "manual_reconciliation_required",
            }:
                execution.update(
                    {
                        "execution_status": "manual_review",
                        "completed_at": utc_now(),
                        "stop_reason": result.get("explanation"),
                        "required_human_action": "manual_review",
                        "closure_eligibility": {
                            "eligible": False,
                            "reason": "Автоматическое закрытие запрещено до ручной проверки.",
                        },
                        "remaining_blockers": ["active_account_restriction"],
                        "recommended_next_action": "perform_manual_review",
                    }
                )
                store.write("executions", executions)
                store.update_plan_status(plan_id, plan_version, "manual_review")
                store.audit(
                    "execution_stopped",
                    run_id=record["run_id"],
                    execution_id=execution["execution_id"],
                    execution_status="manual_review",
                    result_code=result.get("result_code"),
                )
                return execution
        except Exception as error:
            failure = step["failure_action"]
            step_record.update(
                {
                    "status": "failed",
                    "completed_at": utc_now(),
                    "error": str(error),
                    "failure_action": failure,
                }
            )
            if isinstance(error, MissingInputsError):
                step_record["missing_fields"] = error.fields
            store.audit(
                "execution_step_failed",
                run_id=record["run_id"],
                execution_id=execution["execution_id"],
                step_id=step["step_id"],
                failure_action=failure,
                error_code=type(error).__name__,
            )
            if str(error) == "expertise_result_deviation":
                failure = "manual_review"
            if failure == "continue":
                continue
            target = {
                "request_information": "waiting_for_information",
                "replan": "replan_required",
                "manual_review": "manual_review",
            }.get(failure, "failed")
            execution["execution_status"] = target
            execution["completed_at"] = utc_now()
            execution["closure_eligibility"] = {
                "eligible": False,
                "reason": "План остановлен до завершения проверки возможности закрытия.",
            }
            execution["remaining_blockers"] = ["closure_eligibility_not_checked"]
            execution["recommended_next_action"] = {
                "waiting_for_information": "request_missing_information",
                "replan_required": "build_revised_plan",
                "manual_review": "perform_manual_review",
            }.get(target, "inspect_execution_failure")
            if isinstance(error, MissingInputsError):
                execution["missing_fields"] = error.fields
            store.write("executions", executions)
            store.update_plan_status(
                plan_id,
                plan_version,
                "manual_review" if target == "manual_review" else "failed",
            )
            store.update_run_status(str(record["run_id"]), target)
            store.audit(
                "execution_stopped",
                run_id=record["run_id"],
                execution_id=execution["execution_id"],
                execution_status=target,
            )
            return execution
        finally:
            store.write("executions", executions)

    closure = next(
        (item for item in reversed(prior) if "eligible" in item),
        None,
    )
    is_closure_case = _validation_case(
        store.project_dir, record["case_id"]
    ).get("case_subtopic") == "Закрытие счёта"
    if closure is None:
        closure = {
            "eligible": False,
            "remaining_blockers": (
                ["closure_eligibility_not_checked"] if is_closure_case else []
            ),
            "explanation": (
                "Проверка возможности закрытия не выполнена."
                if is_closure_case
                else "Стратегия кейса пройдена в синтетическом mock-контуре."
            ),
        }
    execution.update(
        {
            "execution_status": "completed",
            "completed_at": utc_now(),
            "resolved_blockers": [
                item["resolved_blocker"]
                for item in prior
                if item.get("resolved_blocker")
            ],
            "remaining_blockers": closure.get("remaining_blockers", []),
            "closure_eligibility": {
                "eligible": bool(closure.get("eligible")),
                "reason": closure.get("explanation"),
            },
            "client_response_draft": (
                "Проверка по вашему обращению завершена. Закрытие счёта пока невозможно: "
                "активный холд ожидает завершения reversal. Мы не закрывали счёт и не "
                "отправляли это сообщение автоматически."
                if is_closure_case and not closure.get("eligible")
                else "Проверки завершены, препятствий для закрытия счёта не обнаружено. "
                "Закрытие и отправка сообщения требуют подтверждения сотрудника."
                if is_closure_case
                else "Стратегия решения подготовлена в синтетическом контуре. "
                "Никакие операции и сообщения клиенту автоматически не выполнялись."
            ),
            "requires_final_employee_approval": True,
            "recommended_next_action": (
                "approve_case_closure"
                if is_closure_case and closure.get("eligible")
                else "wait_for_reversal"
                if is_closure_case
                else "employee_review_resolution"
            ),
        }
    )
    store.write("executions", executions)
    store.update_plan_status(plan_id, plan_version, "completed")
    store.audit(
        "execution_completed",
        run_id=record["run_id"],
        execution_id=execution["execution_id"],
        case_id=record["case_id"],
        plan_id=plan_id,
        plan_version=plan_version,
        closure_eligible=bool(closure.get("eligible")),
        requires_final_employee_approval=True,
    )
    return execution
