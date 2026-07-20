"""End-to-end tests for human-governed CasePilot scenario evolution."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

from casepilot.scenario_evolution import (
    analyze_gaps,
    record_learning_event,
    review_draft,
    validate_draft,
    validate_runtime_schemas,
)


ROOT = Path(__file__).resolve().parents[1]


def load_retrieval():
    path = ROOT / "skills" / "find_case_scenarios" / "scripts" / "find_case_scenarios.py"
    spec = importlib.util.spec_from_file_location("scenario_evolution_retrieval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="casepilot-scenario-evolution-"))
    try:
        shutil.copytree(ROOT / "data", project / "data")
        shutil.copytree(ROOT / "schemas", project / "schemas")
        shutil.rmtree(project / "data" / "runtime")

        recorded = record_learning_event(
            project,
            case_id="VAL-DC-016",
            problem_signature="operator_corrected_recurring_timing",
            actions_taken=[
                "check_account_state",
                "request_expertise",
                "prepare_resolution_decision",
            ],
            expertise_types=["recurring_payment_check"],
            required_inputs=[
                "case_id", "card_id", "transaction_id",
                "cancellation_timestamp", "renewal_timestamp",
            ],
            resolution_summary=(
                "Эксперт подтвердил успешное ручное решение по моменту отмены подписки."
            ),
            expert_id="EMP-DEMO-001",
            operator_decision="corrected_plan",
        )
        assert recorded["status"] == "recorded"

        analyzed = analyze_gaps(project)
        assert analyzed["status"] == "ok"
        assert len(analyzed["drafts_created"]) == 1
        draft = analyzed["drafts_created"][0]
        assert draft["status"] == "draft"
        assert draft["proposal_type"] == "new_scenario"
        assert analyzed["publication_performed"] is False
        assert any(
            item["reason"] == "insufficient_validated_evidence"
            for item in analyzed["skipped"]
        )
        assert json.loads(
            (project / "data" / "runtime" / "published_scenarios.json").read_text()
        ) == []

        repeated = analyze_gaps(project)
        assert repeated["drafts_created"] == []
        assert any(
            item["reason"] == "active_draft_exists"
            for item in repeated["skipped"]
        )

        validated = validate_draft(project, draft["draft_id"])
        assert validated["status"] == "ready_for_expert_review"
        replay = validated["draft"]["validation"]["offline_replay"]
        assert replay["tested"] == 3
        assert replay["pass_rate"] == 1

        blocked = review_draft(
            project,
            draft_id=draft["draft_id"],
            decision="approve",
            expert_id="EMP-NOT-ALLOWED",
        )
        raise AssertionError(f"unauthorized review was not blocked: {blocked}")
    except ValueError as error:
        assert "EMP-DEMO-001" in str(error)
        approved = review_draft(
            project,
            draft_id=draft["draft_id"],
            decision="approve",
            expert_id="EMP-DEMO-001",
            comment="Синтетический MVP-сценарий проверен экспертом.",
        )
        assert approved["status"] == "published"
        assert approved["published_scenario"]["status"] == "approved"
        assert validate_runtime_schemas(project) == []

        retrieval = load_retrieval()
        scenarios = retrieval.load_runtime_scenarios(project / "data")
        assert any(
            item.get("scenario_id") == "SCN-DC-LEARNED-PIN-RECOVERY"
            for item in scenarios
        )
        print(
            "PASS: gap -> draft -> independent validation -> expert publication "
            "-> retrieval"
        )
    finally:
        shutil.rmtree(project)


if __name__ == "__main__":
    main()
