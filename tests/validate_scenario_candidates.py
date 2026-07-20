"""Validate draft scenario candidates without promoting them to runtime."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    schema = load("schemas/scenario_candidates.schema.json")
    candidates = load("data/scenario_candidates.json")
    historical = load("data/historical_cases.json")
    expertise = load("data/expertise_catalog.json")
    approved = load("data/scenario_catalog.json")

    require(schema["$schema"].endswith("2020-12/schema"), "wrong schema draft")
    require(len(candidates) >= 1, "candidate catalog is empty")

    historical_ids = {item["case_id"] for item in historical}
    expertise_types = {item["expertise_type"] for item in expertise}
    approved_ids = {item["scenario_id"] for item in approved}
    candidate_ids: set[str] = set()
    proposed_ids: set[str] = set()
    covered_sources: set[str] = set()

    required = set(schema["items"]["required"])
    for item in candidates:
        require(set(item) == required, f"{item.get('candidate_id')}: unexpected shape")
        require(item["status"] == "approved_for_mvp", "scenario must be MVP-approved")
        require(item["candidate_id"] not in candidate_ids, "duplicate candidate_id")
        require(item["proposed_scenario_id"] not in proposed_ids, "duplicate proposed scenario")
        require(item["proposed_scenario_id"] not in approved_ids, "candidate overwrites approved scenario")
        require(item["planning_supported"] is True, "planning flag must be true")
        require(item["execution_supported"] is True, "MVP mock execution must be enabled")
        require(item["evidence_count"] == len(item["source_case_ids"]), "evidence count mismatch")
        require(set(item["source_case_ids"]) <= historical_ids, "unknown source case")
        require(set(item["allowed_expertises"]) <= expertise_types, "unknown expertise")
        require(2 <= len(item["strategy_steps"]) <= 20, "invalid step count")
        require(
            [step["order"] for step in item["strategy_steps"]]
            == list(range(1, len(item["strategy_steps"]) + 1)),
            "non-sequential steps",
        )
        require(
            {
                step["expertise_type"]
                for step in item["strategy_steps"]
                if step["expertise_type"] is not None
            }
            <= set(item["allowed_expertises"]),
            "step uses expertise outside candidate allow-list",
        )
        require(
            {step["action"] for step in item["strategy_steps"]}
            <= set(item["required_new_actions"]),
            "strategy action missing from required_new_actions",
        )
        candidate_ids.add(item["candidate_id"])
        proposed_ids.add(item["proposed_scenario_id"])
        covered_sources.update(item["source_case_ids"])

    baseline_sources = {
        source_id
        for item in approved
        for source_id in item["source_case_ids"]
    }
    require(
        historical_ids == baseline_sources | covered_sources,
        f"historical coverage mismatch: {sorted(historical_ids - baseline_sources - covered_sources)}",
    )

    print(
        "PASS: "
        f"{len(candidates)} candidates cover {len(covered_sources)} non-baseline historical cases; "
        "all are enabled for synthetic MVP planning and mock execution"
    )


if __name__ == "__main__":
    main()
