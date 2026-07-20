"""Dependency-free checks for CasePilot filtering, BM25, and take_case context."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy_retrieval = load_module(
    "casepilot_legacy_retrieval_test",
    ROOT / "skills" / "find_similar_cases" / "scripts" / "find_similar_cases.py",
)
retrieval = load_module(
    "casepilot_scenario_retrieval_test",
    ROOT / "skills" / "find_case_scenarios" / "scripts" / "find_case_scenarios.py",
)
take_case = load_module(
    "casepilot_take_case_test",
    ROOT / "skills" / "take_case" / "plugin.py",
)
planner = load_module(
    "casepilot_planner_test",
    ROOT / "skills" / "build_resolution_plan" / "planner.py",
)


def main() -> None:
    validation = json.loads((ROOT / "data" / "validation_cases.json").read_text())
    history = json.loads((ROOT / "data" / "historical_cases.json").read_text())
    scenarios = json.loads((ROOT / "data" / "scenario_catalog.json").read_text())
    query = validation[0]

    unrelated = copy.deepcopy(history[0])
    unrelated["case_id"] = "HIST-OTHER-001"
    unrelated["case_topic"] = "Кредиты"
    unrelated["case_subtopic"] = "Досрочное погашение"
    legacy = legacy_retrieval.find_similar_cases(query, history + [unrelated], 5)
    assert legacy["filter_stage"] == "exact_topic_and_subtopic"
    result = retrieval.find_case_scenarios(query, scenarios, history, 3)
    assert result["filter_stage"] == "exact_topic_and_subtopic"
    assert result["candidate_count"] == 3
    assert result["results"][0]["scenario_id"] == "SCN-DC-CLOSE-ACTIVE-HOLD"
    assert result["algorithm"] == "scenario_topic_filter_bm25_business_rerank_v1"
    assert result["results"][0]["source_cases"][0]["case_id"] == "HIST-DC-002"

    bounded = retrieval.find_case_scenarios(query, scenarios, history, 99)
    assert bounded["limit"] == 3
    assert len(bounded["results"]) == 3

    context = take_case.prepare_context("VAL-DC-002")
    assert context["status"] == "ok"
    assert context["retrieval"]["filter_stage"] == "exact_topic_and_subtopic"
    assert context["retrieval"]["returned_count"] <= 3
    assert context["scenarios"][0]["scenario_id"] == "SCN-DC-CLOSE-NEGATIVE-BALANCE"
    assert planner.validate_input(
        {
            "case": context["case"],
            "scenarios": context["scenarios"],
            "expertise_catalog": context["expertise_catalog"],
        }
    ) == []
    four = context["scenarios"] + [copy.deepcopy(context["scenarios"][0])]
    errors = planner.validate_input(
        {
            "case": context["case"],
            "scenarios": four,
            "expertise_catalog": context["expertise_catalog"],
        }
    )
    assert errors == ["scenarios must be a non-empty array with at most 3 items"]

    missing = take_case.prepare_context("VAL-DC-999")
    assert missing["status"] == "not_found"

    plan_payload = json.loads(
        (ROOT / "tests" / "fixtures" / "VAL-DC-001_resolution_plan.json").read_text()
    )
    proposed = {
        "run_id": "RUN-TEST-0001",
        "plan_id": "PLAN-TEST-0001",
        "plan_version": 1,
        "status": "proposed",
        "plan": plan_payload,
    }
    proposed_view = take_case._operator_view(query, plan_payload, proposed)
    assert len(proposed_view["employee_actions"]) == 3
    completed = {**proposed, "status": "completed"}
    completed_view = take_case._operator_view(query, plan_payload, completed)
    assert completed_view["employee_actions"] == []
    assert "только для просмотра" in take_case._operator_message(completed_view)
    print("PASS: scenario filter, BM25 ranking, top-3 cap, take_case context")


if __name__ == "__main__":
    main()
