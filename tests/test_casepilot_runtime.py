"""Preflight, main-flow, and negative tests for CasePilot runtime iteration."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from casepilot.runtime import (
    RuntimeStore,
    check_account_state,
    check_pending_operations,
    execute_plan,
    request_expertise,
    review_plan,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_ID = "PLAN-VAL-DC-001-001"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_project() -> Path:
    root = Path(tempfile.mkdtemp(prefix="casepilot-runtime-"))
    shutil.copytree(ROOT / "data", root / "data")
    shutil.copytree(ROOT / "schemas", root / "schemas")
    (root / "tests" / "fixtures").mkdir(parents=True)
    shutil.copy(
        ROOT / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json",
        root / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json",
    )
    runtime = root / "data" / "runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    return root


def decision(version: int, kind: str, comment: str | None = None) -> dict[str, object]:
    return {
        "case_id": "VAL-DC-001",
        "plan_id": PLAN_ID,
        "plan_version": version,
        "decision": kind,
        "employee_id": "EMP-DEMO-001",
        "comment": comment,
    }


def preflight_plugins() -> None:
    class FakeAPI:
        def __init__(self) -> None:
            self.tools: list[str] = []

        def register_tool(self, name: str, **_: object) -> None:
            self.tools.append(name)

        def get_settings(self, _: object) -> dict[str, str]:
            return {}

    expected = {
        "review_resolution_plan",
        "check_account_state",
        "check_pending_operations",
        "request_expertise",
        "closure_eligibility",
        "execute_approved_plan",
        "wait_settlement",
        "draft_postclose_instr",
        "collect_compliance",
        "match_cash_surplus",
        "draft_resolution",
    }
    registered: set[str] = set()
    directories = {
        "review_resolution_plan",
        "check_account_state",
        "check_pending_operations",
        "request_expertise",
        "check_account_closure_eligibility",
        "execute_approved_plan",
        "case-actions",
    }
    for name in directories:
        path = ROOT / "skills" / name / "plugin.py"
        spec = importlib.util.spec_from_file_location(f"preflight_{name}", path)
        require(spec is not None and spec.loader is not None, f"cannot import {name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        api = FakeAPI()
        module.register(api)
        registered.update(api.tools)
    require(registered == expected, f"unexpected tool registration: {registered}")


def main_flow() -> None:
    root = make_project()
    try:
        store = RuntimeStore(root)
        plan = json.loads(
            (root / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json").read_text()
        )
        errors = list(
            Draft202012Validator(
                json.loads((root / "schemas" / "resolution_plan.schema.json").read_text())
            ).iter_errors(plan)
        )
        require(not errors, f"artifact schema errors: {[item.message for item in errors]}")
        first_run = store.start_run("VAL-DC-001")
        store.seed_plan(PLAN_ID, 1, plan, run_id=first_run["run_id"])
        approved = review_plan(store, decision(1, "approve_plan"))
        require(approved["status"] == "approved", f"approval failed: {approved}")
        result = execute_plan(store, PLAN_ID, 1)
        require(result["execution_status"] == "completed", f"execution failed: {result}")
        require(len(result["steps"]) == 4, "not all approved steps executed")
        require(
            all(item["status"] == "completed" for item in result["steps"]),
            "a step did not complete",
        )
        require(result["requires_final_employee_approval"] is True, "final HITL missing")
        require(result["closure_eligibility"]["eligible"] is False, "hold should remain")
        events = [
            json.loads(line)
            for line in store.audit_path.read_text().splitlines()
            if line.strip()
        ]
        require(events[0]["event_type"] == "case_run_started", "run audit start missing")
        require(events[-1]["event_type"] == "execution_completed", "audit end missing")
        require(
            all(item.get("run_id") == first_run["run_id"] for item in events),
            "audit events are not correlated by run_id",
        )
        forbidden = {"api_key", "system_prompt", "authorization"}
        require(all(not forbidden.intersection(item) for item in events), "secret audit key")
    finally:
        shutil.rmtree(root)


def negative_flows() -> None:
    root = make_project()
    try:
        store = RuntimeStore(root)
        plan = json.loads(
            (root / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json").read_text()
        )
        store.seed_plan(PLAN_ID, 1, plan)
        require(
            execute_plan(store, PLAN_ID, 1)["status"] == "not_approved",
            "unapproved execution was not blocked",
        )
        change = review_plan(
            store,
            decision(1, "request_change", "Сначала проверить reversal."),
        )
        require(change["status"] == "change_requested", "first revision was blocked")
        repeated_v1 = review_plan(
            store,
            decision(1, "request_change", "Ещё одно изменение до версии 2."),
        )
        require(
            repeated_v1["status"] == "manual_review",
            "repeated version-1 request_change did not stop",
        )

        store = RuntimeStore(make_project())
        store.seed_plan(PLAN_ID, 1, plan)
        review_plan(store, decision(1, "request_change", "Сначала проверить reversal."))
        revised = deepcopy(plan)
        revised["case_summary"] += " План уточнён сотрудником."
        store.seed_plan(PLAN_ID, 2, revised, supersedes_plan_version=1)
        stale = review_plan(store, decision(1, "approve_plan"))
        require(stale["status"] == "stale_plan", "stale plan approval was allowed")
        second = review_plan(
            store,
            decision(2, "request_change", "Нужно изменить снова."),
        )
        require(second["status"] == "manual_review", "second revision did not stop")
        require(second["reason"] == "revision_limit_exceeded", "wrong revision reason")
        require(store.current_plan(PLAN_ID)["plan_version"] == 2, "version 3 was created")

        store2 = RuntimeStore(make_project())
        store2.seed_plan(PLAN_ID, 1, plan)
        review_plan(store2, decision(1, "manual_review", "Ручной анализ."))
        require(
            execute_plan(store2, PLAN_ID, 1)["status"] == "not_approved",
            "manual-review plan executed",
        )

        try:
            request_expertise(
                root, plan, "VAL-DC-001", "nonexistent_expertise", {"case_id": "VAL-DC-001"}
            )
            raise AssertionError("unknown expertise was accepted")
        except ValueError as error:
            require("not present" in str(error), "wrong unknown-expertise error")
        try:
            request_expertise(
                root,
                plan,
                "VAL-DC-001",
                "card_transaction_status_check",
                {"case_id": "VAL-DC-001"},
            )
            raise AssertionError("missing expertise inputs were accepted")
        except ValueError as error:
            require("missing required" in str(error), "wrong missing-input error")

        state = check_account_state(root, "VAL-DC-001", "SYN-ACC-9001")
        pending = check_pending_operations(
            root, "VAL-DC-001", "SYN-CARD-9001", "SYN-ACC-9001"
        )
        require(state["result_code"] == "account_state_retrieved", "bad state mock")
        require(pending["result_code"] == "pending_reversal_confirmed", "bad pending mock")
    finally:
        shutil.rmtree(root)
        if "store" in locals() and store.project_dir != root:
            shutil.rmtree(store.project_dir)
        if "store2" in locals():
            shutil.rmtree(store2.project_dir)


def repeatable_runs() -> None:
    root = make_project()
    try:
        store = RuntimeStore(root)
        plan = json.loads(
            (root / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json").read_text()
        )
        first = store.start_run("VAL-DC-001")
        second = store.start_run("VAL-DC-001")
        first_plan = store.seed_plan(
            f"PLAN-{first['run_id']}", 1, plan, run_id=first["run_id"]
        )
        second_plan = store.seed_plan(
            f"PLAN-{second['run_id']}", 1, plan, run_id=second["run_id"]
        )
        require(first["run_id"] != second["run_id"], "repeat run_id was reused")
        require(first_plan["plan_id"] != second_plan["plan_id"], "plan was overwritten")
        require(
            store.latest_run("VAL-DC-001")["run_id"] == second["run_id"],
            "latest run lookup is incorrect",
        )
        require(
            store.current_plan_for_run(first["run_id"])["plan_id"] == first_plan["plan_id"],
            "first run is no longer independently addressable",
        )
    finally:
        shutil.rmtree(root)


def main() -> None:
    preflight_plugins()
    main_flow()
    negative_flows()
    repeatable_runs()
    print("PASS: CasePilot runtime preflight, main flow, and negative scenarios")


if __name__ == "__main__":
    main()
