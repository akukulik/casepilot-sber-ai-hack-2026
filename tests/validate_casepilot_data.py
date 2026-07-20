"""Dependency-free contract checks for the synthetic CasePilot datasets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMAS = ROOT / "schemas"

COMMON_CASE_FIELDS = {
    "case_id",
    "client_id",
    "case_topic",
    "case_subtopic",
    "created_at",
    "priority",
    "case_description",
    "conversation_transcript",
    "client_context",
    "products",
    "synthetic_system_data",
}
HISTORICAL_ONLY_FIELDS = {
    "resolution_plan",
    "expertise_results",
    "final_result",
}
EXPERTISE_FIELDS = {
    "expertise_type",
    "title",
    "department",
    "description",
    "required_inputs",
    "possible_results",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_common_case(case: dict[str, Any]) -> None:
    require(COMMON_CASE_FIELDS <= case.keys(), f"{case.get('case_id')}: missing common fields")
    require(case["case_topic"] == "Дебетовые карты", f"{case['case_id']}: wrong topic")
    require(bool(case["case_subtopic"].strip()), f"{case['case_id']}: empty subtopic")
    require(case["priority"] in {"low", "normal", "high", "critical"}, f"{case['case_id']}: bad priority")
    datetime.fromisoformat(case["created_at"])
    require(len(case["case_description"]) >= 40, f"{case['case_id']}: short description")
    require(len(case["conversation_transcript"]) >= 2, f"{case['case_id']}: short transcript")
    require(len(case["products"]) >= 1, f"{case['case_id']}: products missing")
    for message in case["conversation_transcript"]:
        require(set(message) == {"speaker", "timestamp", "text"}, f"{case['case_id']}: bad transcript item")
        require(message["speaker"] in {"client", "employee", "system"}, f"{case['case_id']}: bad speaker")
        datetime.fromisoformat(message["timestamp"])


def main() -> None:
    for schema_name in (
        "historical_cases.schema.json",
        "validation_cases.schema.json",
        "expertise_catalog.schema.json",
        "scenario_catalog.schema.json",
        "scenario_learning_events.schema.json",
    ):
        schema = load_json(SCHEMAS / schema_name)
        require(schema.get("$schema", "").endswith("2020-12/schema"), f"{schema_name}: wrong draft")

    resolution_plan_schema = load_json(SCHEMAS / "resolution_plan.schema.json")
    proposed_plan = resolution_plan_schema["properties"]["proposed_plan"]
    require(proposed_plan["minItems"] == 2, "resolution plan minimum must be 2 steps")
    require(proposed_plan["maxItems"] == 20, "resolution plan maximum must be 20 steps")
    step_properties = proposed_plan["items"]["properties"]
    require(step_properties["order"]["maximum"] == 20, "step order maximum must be 20")
    require(
        step_properties["step_id"]["pattern"] == "^step_(?:[1-9]|1[0-9]|20)$",
        "step_id pattern must support step_1 through step_20",
    )

    historical = load_json(DATA / "historical_cases.json")
    validation = load_json(DATA / "validation_cases.json")
    expertise = load_json(DATA / "expertise_catalog.json")
    scenarios = load_json(DATA / "scenario_catalog.json")
    learning_events = load_json(DATA / "scenario_learning_events.json")

    require(len(historical) >= 3, "expected at least 3 historical cases")
    require(len(validation) >= 4, "expected at least 4 validation cases")
    require(len(expertise) >= 3, "expected at least 3 expertise types")
    require(len(scenarios) == 3, "expected exactly 3 approved scenarios")
    require(len(learning_events) >= 3, "expected scenario-learning demo evidence")
    require(
        all(item["resolution_status"] == "validated_success" for item in learning_events),
        "learning events must be expert-validated successes",
    )

    expertise_types = set()
    for item in expertise:
        require(set(item) == EXPERTISE_FIELDS, f"bad expertise shape: {item.get('expertise_type')}")
        expertise_types.add(item["expertise_type"])
        require(item["required_inputs"], f"{item['expertise_type']}: required_inputs empty")
        require(item["possible_results"], f"{item['expertise_type']}: possible_results empty")
    require(len(expertise_types) == len(expertise), "duplicate expertise_type")

    case_ids = set()
    for case in historical:
        validate_common_case(case)
        require(set(case) == COMMON_CASE_FIELDS | HISTORICAL_ONLY_FIELDS, f"{case['case_id']}: bad historical shape")
        require(case["case_id"] not in case_ids, f"duplicate case_id {case['case_id']}")
        case_ids.add(case["case_id"])
        require(case["resolution_plan"], f"{case['case_id']}: resolution_plan empty")
        for step in case["resolution_plan"]:
            require(step["expertise_type"] in expertise_types, f"{case['case_id']}: unknown plan expertise")
        for result in case["expertise_results"]:
            require(result["expertise_type"] in expertise_types, f"{case['case_id']}: unknown result expertise")

    for case in validation:
        validate_common_case(case)
        require(set(case) == COMMON_CASE_FIELDS, f"{case['case_id']}: validation shape leaks solution")
        require(not HISTORICAL_ONLY_FIELDS.intersection(case), f"{case['case_id']}: hidden answer leak")
        require(case["case_id"] not in case_ids, f"duplicate case_id {case['case_id']}")
        case_ids.add(case["case_id"])
    require(
        {"VAL-DC-001", "VAL-DC-002", "VAL-DC-003", "VAL-DC-004"}
        <= {case["case_id"] for case in validation},
        "baseline validation case IDs are missing",
    )

    allowed_actions = {
        "check_account_state",
        "check_pending_operations",
        "request_expertise",
        "check_account_closure_eligibility",
    }
    historical_ids = {case["case_id"] for case in historical}
    scenario_ids = set()
    for scenario in scenarios:
        scenario_ids.add(scenario["scenario_id"])
        require(scenario["status"] == "approved", "only approved scenarios may be retrieved")
        require(
            set(scenario["source_case_ids"]) <= historical_ids,
            f"{scenario['scenario_id']}: unknown source case",
        )
        require(
            set(scenario["allowed_expertises"]) <= expertise_types,
            f"{scenario['scenario_id']}: unknown expertise",
        )
        orders = [step["order"] for step in scenario["strategy_steps"]]
        require(orders == list(range(1, len(orders) + 1)), "scenario steps not sequential")
        require(
            all(step["action"] in allowed_actions for step in scenario["strategy_steps"]),
            f"{scenario['scenario_id']}: forbidden action",
        )
    require(len(scenario_ids) == len(scenarios), "duplicate scenario_id")
    missing_reference = next(case for case in validation if case["case_id"] == "VAL-DC-004")
    require(
        "restriction_reference" not in missing_reference["synthetic_system_data"],
        "VAL-DC-004 must omit restriction_reference",
    )

    reasons = {
        case["synthetic_system_data"]["closure_check_code"]
        for case in historical
        if "closure_check_code" in case["synthetic_system_data"]
    }
    require(
        {
            "ACCOUNT_BALANCE_NOT_ZERO",
            "ACTIVE_AUTHORIZATION_HOLD",
            "ACTIVE_ACCOUNT_RESTRICTION",
        } <= reasons,
        f"baseline closure reasons are missing: {sorted(reasons)}",
    )

    print("PASS: schemas parse and all CasePilot dataset contracts are satisfied")


if __name__ == "__main__":
    main()
