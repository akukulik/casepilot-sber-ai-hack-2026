"""Contract tests for CasePilot resolution recommendations without provider calls."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    PROJECT
    / "skills"
    / "build-resolution-recommendation"
    / "recommendation.py"
)
SPEC = importlib.util.spec_from_file_location("casepilot_recommendation_test", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("recommendation module unavailable")
RECOMMENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOMMENDER)
OUTCOMES_SPEC = importlib.util.spec_from_file_location(
    "casepilot_outcomes_fixture",
    PROJECT / "tests" / "test_casepilot_outcomes.py",
)
if OUTCOMES_SPEC is None or OUTCOMES_SPEC.loader is None:
    raise RuntimeError("outcome fixture module unavailable")
OUTCOMES = importlib.util.module_from_spec(OUTCOMES_SPEC)
OUTCOMES_SPEC.loader.exec_module(OUTCOMES)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_for(root: Path, execution: dict) -> dict:
    plans = load(root / "data" / "runtime" / "plans.json")
    cases = load(root / "data" / "validation_cases.json")
    plan = next(
        item["plan"]
        for item in plans
        if item.get("plan_id") == execution.get("plan_id")
        and item.get("plan_version") == execution.get("plan_version")
    )
    case = next(item for item in cases if item["case_id"] == execution["case_id"])
    return {"case": case, "plan": plan, "execution": execution}


def main() -> None:
    schema = load(PROJECT / "schemas" / "resolution_recommendation.schema.json")
    fixture_root = Path(tempfile.mkdtemp(prefix="casepilot-recommendation-runtime-"))
    shutil.copytree(PROJECT / "data", fixture_root / "data")
    shutil.copytree(PROJECT / "schemas", fixture_root / "schemas")
    shutil.rmtree(fixture_root / "data" / "runtime")
    balance_inputs = [
        "case_id", "account_id", "ledger_balance", "available_balance", "fee_events"
    ]
    restriction_inputs = [
        "case_id", "account_id", "restriction_flags",
        "restriction_reference", "restriction_status",
    ]
    samples = {
        "completed": OUTCOMES.run_case(
            fixture_root,
            OUTCOMES.plan(
                "VAL-DC-002",
                "account_balance_analysis",
                balance_inputs,
                "manual_review",
            ),
        ),
        "manual_review": OUTCOMES.run_case(
            fixture_root,
            OUTCOMES.plan(
                "VAL-DC-003",
                "account_restriction_check",
                restriction_inputs,
                "manual_review",
            ),
        ),
        "waiting_for_information": OUTCOMES.run_case(
            fixture_root,
            OUTCOMES.plan(
                "VAL-DC-004",
                "account_restriction_check",
                restriction_inputs,
                "request_information",
            ),
        ),
    }

    expected = {
        "waiting_for_information": "REQUEST_INFORMATION",
        "manual_review": "MANUAL_REVIEW",
    }
    for status in ("completed", "waiting_for_information", "manual_review"):
        source = source_for(fixture_root, samples[status])
        assert RECOMMENDER.validate_source(source) == []
        recommendation = RECOMMENDER.deterministic_fallback(source)
        assert list(Draft202012Validator(schema).iter_errors(recommendation)) == []
        assert RECOMMENDER.validate_recommendation(
            recommendation, source, schema
        ) == []
        assert recommendation["requires_employee_approval"] is True
        assert len(recommendation["title"]) <= 100
        assert len(recommendation["summary"]) <= 280
        assert len(recommendation["key_findings"]) <= 4
        assert len(recommendation["remaining_risks"]) <= 3
        assert len(recommendation["employee_actions"]) <= 3
        if status in expected:
            assert recommendation["decision_code"] == expected[status]
            assert recommendation["confidence"]["level"] == "low"

    completed_source = source_for(fixture_root, samples["completed"])
    invalid = RECOMMENDER.deterministic_fallback(completed_source)
    invalid["key_findings"].append(
        {
            "finding": "Выдуманный факт.",
            "source_step_id": "step_999",
            "result_code": "INVENTED",
        }
    )
    assert any(
        "unknown evidence" in error
        for error in RECOMMENDER.validate_recommendation(
            invalid, completed_source, schema
        )
    )
    inconsistent = RECOMMENDER.deterministic_fallback(completed_source)
    inconsistent["confidence"] = {
        "level": "medium",
        "score": 0,
        "reason": "Несогласованная тестовая оценка.",
    }
    assert any(
        "inconsistent with score" in error
        for error in RECOMMENDER.validate_recommendation(
            inconsistent, completed_source, schema
        )
    )
    verbose = RECOMMENDER.deterministic_fallback(completed_source)
    verbose["summary"] = "Очень длинное описание " * 100
    verbose["remaining_risks"] = ["Риск " * 100] * 10
    verbose["employee_actions"] = ["Действие " * 100] * 10
    compact = RECOMMENDER.compact_recommendation(verbose)
    assert len(compact["summary"]) <= 281
    assert len(compact["remaining_risks"]) == 3
    assert len(compact["employee_actions"]) == 3

    temporary = Path(tempfile.mkdtemp(prefix="casepilot-recommendation-schema-"))
    try:
        shutil.copytree(PROJECT / "schemas", temporary / "schemas")
        runtime_schema = load(
            temporary / "schemas" / "runtime_recommendations.schema.json"
        )
        assert runtime_schema["items"]["properties"]["recommendation"]["$ref"] == (
            "resolution_recommendation.schema.json"
        )
    finally:
        shutil.rmtree(temporary)
        shutil.rmtree(fixture_root)

    print("PASS: recommendation schema, evidence binding, and safe fallbacks")


if __name__ == "__main__":
    main()
