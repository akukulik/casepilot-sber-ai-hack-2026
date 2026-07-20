"""Human-governed scenario learning for synthetic CasePilot data."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


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
EXPERT_ID = "EMP-DEMO-001"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2)
            target.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_runtime(project: Path) -> dict[str, Path]:
    runtime = project / "data" / "runtime"
    paths = {
        "drafts": runtime / "scenario_drafts.json",
        "reviews": runtime / "scenario_reviews.json",
        "published": runtime / "published_scenarios.json",
        "learning_events": runtime / "scenario_learning_events.json",
        "audit": runtime / "scenario_evolution_audit.jsonl",
    }
    runtime.mkdir(parents=True, exist_ok=True)
    for key in ("drafts", "reviews", "published", "learning_events"):
        if not paths[key].exists():
            atomic_write(paths[key], [])
    paths["audit"].touch(exist_ok=True)
    return paths


def audit(path: Path, event_type: str, **details: Any) -> None:
    event = {"timestamp": utc_now(), "event_type": event_type, **details}
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _slug(text: str) -> str:
    transliterated = {
        "Смена ПИН-кода после блокировки": "PIN-RECOVERY",
    }.get(text)
    if transliterated:
        return transliterated
    value = re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")
    return value or "LEARNED"


def _existing_scenarios(project: Path) -> list[dict[str, Any]]:
    result = load_json(project / "data" / "scenario_catalog.json")
    for item in load_json(project / "data" / "scenario_candidates.json"):
        result.append(
            {
                "scenario_id": item["proposed_scenario_id"],
                "case_topic": item["case_topic"],
                "case_subtopics": item["case_subtopics"],
            }
        )
    paths = ensure_runtime(project)
    result.extend(load_json(paths["published"]))
    return result


def analyze_gaps(
    project: Path,
    *,
    minimum_cluster_size: int = 3,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create drafts from repeated, expert-validated manual resolutions."""
    paths = ensure_runtime(project)
    source = events if events is not None else (
        load_json(project / "data" / "scenario_learning_events.json")
        + load_json(paths["learning_events"])
    )
    eligible = [
        item for item in source
        if item.get("resolution_status") == "validated_success"
        and item.get("operator_decision") in {"manual_resolution", "corrected_plan"}
        and item.get("validated_by")
    ]
    clusters: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        clusters[
            (
                str(item.get("case_topic")),
                str(item.get("case_subtopic")),
                str(item.get("problem_signature")),
            )
        ].append(item)

    existing = _existing_scenarios(project)
    drafts = load_json(paths["drafts"])
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for (topic, subtopic, signature), members in sorted(clusters.items()):
        if len(members) < minimum_cluster_size:
            skipped.append(
                {
                    "problem_signature": signature,
                    "reason": "insufficient_validated_evidence",
                    "evidence_count": len(members),
                }
            )
            continue
        duplicate = next(
            (
                item for item in drafts
                if item["proposed_scenario"].get("problem_signature") == signature
                and item["status"] not in {"rejected"}
            ),
            None,
        )
        if duplicate:
            skipped.append(
                {
                    "problem_signature": signature,
                    "reason": "active_draft_exists",
                    "draft_id": duplicate["draft_id"],
                }
            )
            continue
        overlap = next(
            (
                item for item in existing
                if item.get("case_topic") == topic
                and subtopic in (
                    item.get("case_subtopics") or [item.get("case_subtopic")]
                )
            ),
            None,
        )
        action_sequences = Counter(tuple(item["actions_taken"]) for item in members)
        actions = list(action_sequences.most_common(1)[0][0])
        expertises = sorted(
            {value for item in members for value in item.get("expertise_types", [])}
        )
        required_inputs = sorted(
            {value for item in members for value in item.get("required_inputs", [])}
        )
        steps = []
        expertise_index = 0
        for index, action in enumerate(actions, start=1):
            expertise_type = None
            if action == "request_expertise" and expertise_index < len(expertises):
                expertise_type = expertises[expertise_index]
                expertise_index += 1
            steps.append(
                {
                    "order": index,
                    "action": action,
                    "description": (
                        f"Выполнить подтверждённый ручными решениями шаг: {action}."
                    ),
                    "expertise_type": expertise_type,
                }
            )
        scenario_id = (
            str(overlap.get("scenario_id"))
            if overlap
            else f"SCN-DC-LEARNED-{_slug(subtopic)}"
        )
        proposed = {
            "scenario_id": scenario_id,
            "problem_signature": signature,
            "title": f"Сценарий: {subtopic}",
            "case_topic": topic,
            "case_subtopic": subtopic,
            "case_subtopics": [subtopic],
            "description": (
                f"Стратегия сформирована из {len(members)} подтверждённых "
                "успешных ручных решений и требует экспертной публикации."
            ),
            "trigger_conditions": [f"problem_signature={signature}"],
            "required_inputs": required_inputs,
            "product_types": ["debit_card", "current_account"],
            "strategy_steps": steps,
            "allowed_expertises": expertises,
            "stop_conditions": [
                "identity verification failed",
                "fraud indicators require manual review",
            ],
        }
        record = {
            "draft_id": f"SCD-{len(drafts) + len(created) + 1:04d}",
            "status": "draft",
            "proposal_type": "scenario_update" if overlap else "new_scenario",
            "target_scenario_id": overlap.get("scenario_id") if overlap else None,
            "proposed_scenario": proposed,
            "source_event_ids": [item["event_id"] for item in members],
            "source_case_ids": [item["case_id"] for item in members],
            "evidence_count": len(members),
            "created_at": utc_now(),
            "generation_method": "deterministic_cluster_synthesis_v1",
            "validation": None,
        }
        created.append(record)
    drafts.extend(created)
    atomic_write(paths["drafts"], drafts)
    for record in created:
        audit(
            paths["audit"],
            "scenario_draft_created",
            draft_id=record["draft_id"],
            proposal_type=record["proposal_type"],
            evidence_count=record["evidence_count"],
        )
    return {
        "status": "ok",
        "eligible_event_count": len(eligible),
        "clusters_analyzed": len(clusters),
        "drafts_created": created,
        "skipped": skipped,
        "publication_performed": False,
    }


def validate_draft(project: Path, draft_id: str) -> dict[str, Any]:
    """Validate one draft independently and run deterministic offline replay."""
    paths = ensure_runtime(project)
    drafts = load_json(paths["drafts"])
    draft = next((item for item in drafts if item.get("draft_id") == draft_id), None)
    if draft is None:
        return {"status": "not_found", "draft_id": draft_id}
    if draft["status"] not in {"draft", "validation_failed"}:
        return {"status": "invalid_state", "draft_id": draft_id, "current": draft["status"]}
    events = {
        item["event_id"]: item
        for item in (
            load_json(project / "data" / "scenario_learning_events.json")
            + load_json(paths["learning_events"])
        )
    }
    catalog_expertises = {
        item["expertise_type"]
        for item in load_json(project / "data" / "expertise_catalog.json")
    }
    errors: list[str] = []
    learning_schema = load_json(
        project / "schemas" / "scenario_learning_events.schema.json"
    )
    learning_payload = load_json(project / "data" / "scenario_learning_events.json")
    schema_errors = [
        issue.message
        for issue in Draft202012Validator(learning_schema).iter_errors(learning_payload)
    ]
    if schema_errors:
        errors.extend(f"learning event schema: {item}" for item in schema_errors)
    evidence = [events.get(item) for item in draft["source_event_ids"]]
    if any(item is None for item in evidence):
        errors.append("source event is missing")
    valid_evidence = [item for item in evidence if item is not None]
    if len(valid_evidence) < 3:
        errors.append("at least three validated source events are required")
    if any(item.get("resolution_status") != "validated_success" for item in valid_evidence):
        errors.append("source event is not a validated success")
    scenario = draft["proposed_scenario"]
    actions = [item.get("action") for item in scenario.get("strategy_steps", [])]
    unknown_actions = sorted(set(actions) - ALLOWED_ACTIONS)
    if unknown_actions:
        errors.append(f"unknown actions: {unknown_actions}")
    unknown_expertises = sorted(
        set(scenario.get("allowed_expertises", [])) - catalog_expertises
    )
    if unknown_expertises:
        errors.append(f"unknown expertises: {unknown_expertises}")
    if not 2 <= len(actions) <= 20:
        errors.append("strategy must contain 2-20 steps")
    expected_orders = list(range(1, len(actions) + 1))
    actual_orders = [item.get("order") for item in scenario.get("strategy_steps", [])]
    if actual_orders != expected_orders:
        errors.append("strategy step order is not sequential")
    exact_overlap = next(
        (
            item
            for item in _existing_scenarios(project)
            if item.get("case_topic") == scenario.get("case_topic")
            and scenario.get("case_subtopic")
            in (item.get("case_subtopics") or [item.get("case_subtopic")])
        ),
        None,
    )
    if draft["proposal_type"] == "new_scenario" and exact_overlap:
        errors.append(
            "exact topic/subtopic conflict; candidate must be a scenario_update"
        )
    if (
        draft["proposal_type"] == "scenario_update"
        and (
            not exact_overlap
            or exact_overlap.get("scenario_id") != draft.get("target_scenario_id")
        )
    ):
        errors.append("scenario_update target does not match the catalog")

    replay_results = []
    for event in valid_evidence:
        action_coverage = (
            len(set(actions) & set(event["actions_taken"]))
            / max(len(set(event["actions_taken"])), 1)
        )
        expertise_coverage = (
            len(set(scenario["allowed_expertises"]) & set(event["expertise_types"]))
            / max(len(set(event["expertise_types"])), 1)
        )
        passed = action_coverage == 1 and expertise_coverage == 1
        replay_results.append(
            {
                "event_id": event["event_id"],
                "passed": passed,
                "action_coverage": round(action_coverage, 4),
                "expertise_coverage": round(expertise_coverage, 4),
            }
        )
    replay_rate = (
        sum(1 for item in replay_results if item["passed"]) / len(replay_results)
        if replay_results else 0
    )
    if replay_rate < 0.8:
        errors.append("offline replay pass rate is below 0.8")

    validation = {
        "validated_at": utc_now(),
        "schema_valid": not schema_errors and actual_orders == expected_orders,
        "allowlists_valid": not unknown_actions and not unknown_expertises,
        "evidence_valid": len(valid_evidence) >= 3,
        "conflict_check": (
            f"update_existing:{draft.get('target_scenario_id')}"
            if draft["proposal_type"] == "scenario_update"
            else "no_exact_subtopic_conflict"
        ),
        "offline_replay": {
            "tested": len(replay_results),
            "passed": sum(1 for item in replay_results if item["passed"]),
            "pass_rate": round(replay_rate, 4),
            "results": replay_results,
        },
        "errors": errors,
        "recommendation": "expert_review" if not errors else "reject_or_rework",
    }
    draft["validation"] = validation
    draft["status"] = "ready_for_expert_review" if not errors else "validation_failed"
    atomic_write(paths["drafts"], drafts)
    audit(
        paths["audit"],
        "scenario_draft_validated",
        draft_id=draft_id,
        result=draft["status"],
        replay_rate=round(replay_rate, 4),
    )
    return {"status": draft["status"], "draft": draft}


def review_draft(
    project: Path,
    *,
    draft_id: str,
    decision: str,
    expert_id: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Publish or reject only after explicit expert review."""
    if expert_id != EXPERT_ID:
        raise ValueError("only EMP-DEMO-001 may review a scenario draft in the MVP")
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    paths = ensure_runtime(project)
    drafts = load_json(paths["drafts"])
    draft = next((item for item in drafts if item.get("draft_id") == draft_id), None)
    if draft is None:
        return {"status": "not_found", "draft_id": draft_id}
    if draft["status"] != "ready_for_expert_review":
        return {"status": "invalid_state", "current": draft["status"], "draft_id": draft_id}
    reviews = load_json(paths["reviews"])
    outcome = "published" if decision == "approve" else "rejected"
    review = {
        "review_id": f"SCR-{len(reviews) + 1:04d}",
        "draft_id": draft_id,
        "decision": decision,
        "expert_id": expert_id,
        "comment": comment,
        "created_at": utc_now(),
        "outcome": outcome,
    }
    reviews.append(review)
    atomic_write(paths["reviews"], reviews)
    published_record = None
    if decision == "approve":
        scenario = dict(draft["proposed_scenario"])
        scenario.pop("problem_signature", None)
        published = load_json(paths["published"])
        existing_versions = [
            int(item.get("version") or 0)
            for item in published
            if item.get("scenario_id") == scenario["scenario_id"]
        ]
        published_record = {
            **scenario,
            "version": max(existing_versions, default=0) + 1,
            "status": "approved",
            "approval_scope": "mvp_synthetic_planning_and_mock_execution",
            "source_case_ids": draft["source_case_ids"],
            "successful_cases": draft["evidence_count"],
            "success_rate": draft["validation"]["offline_replay"]["pass_rate"],
            "planning_supported": True,
            "execution_supported": True,
            "approved_by": expert_id,
            "approved_at": utc_now(),
        }
        published.append(published_record)
        atomic_write(paths["published"], published)
    draft["status"] = outcome
    atomic_write(paths["drafts"], drafts)
    audit(
        paths["audit"],
        "scenario_draft_reviewed",
        draft_id=draft_id,
        decision=decision,
        expert_id=expert_id,
        outcome=outcome,
    )
    return {
        "status": outcome,
        "review": review,
        "published_scenario": published_record,
    }


def record_learning_event(
    project: Path,
    *,
    case_id: str,
    problem_signature: str,
    actions_taken: list[str],
    expertise_types: list[str],
    required_inputs: list[str],
    resolution_summary: str,
    expert_id: str,
    operator_decision: str = "manual_resolution",
) -> dict[str, Any]:
    """Record one expert-validated outcome; never infer success from manual_review."""
    if expert_id != EXPERT_ID:
        raise ValueError("only EMP-DEMO-001 may validate a learning event in the MVP")
    if operator_decision not in {"manual_resolution", "corrected_plan"}:
        raise ValueError("unsupported operator_decision")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", problem_signature):
        raise ValueError("problem_signature must be a stable machine identifier")
    unknown_actions = sorted(set(actions_taken) - ALLOWED_ACTIONS)
    if unknown_actions:
        raise ValueError(f"unknown actions: {unknown_actions}")
    if not 2 <= len(actions_taken) <= 20:
        raise ValueError("actions_taken must contain 2-20 actions")
    catalog_expertises = {
        item["expertise_type"]
        for item in load_json(project / "data" / "expertise_catalog.json")
    }
    unknown_expertises = sorted(set(expertise_types) - catalog_expertises)
    if unknown_expertises:
        raise ValueError(f"unknown expertises: {unknown_expertises}")
    cases = load_json(project / "data" / "validation_cases.json")
    case = next((item for item in cases if item.get("case_id") == case_id), None)
    if case is None:
        raise ValueError("only a known synthetic validation case may be recorded")
    paths = ensure_runtime(project)
    events = load_json(paths["learning_events"])
    record = {
        "event_id": f"SLE-RUNTIME-{len(events) + 1:04d}",
        "case_id": case_id,
        "case_topic": case["case_topic"],
        "case_subtopic": case["case_subtopic"],
        "problem_signature": problem_signature,
        "resolution_status": "validated_success",
        "operator_decision": operator_decision,
        "actions_taken": actions_taken,
        "expertise_types": sorted(set(expertise_types)),
        "required_inputs": sorted(set(required_inputs)),
        "resolution_summary": resolution_summary.strip(),
        "validated_by": expert_id,
        "validated_at": utc_now(),
    }
    if len(record["resolution_summary"]) < 20:
        raise ValueError("resolution_summary is too short")
    schema = load_json(project / "schemas" / "scenario_learning_events.schema.json")
    issues = list(Draft202012Validator(schema).iter_errors([record]))
    if issues:
        raise ValueError("invalid learning event: " + "; ".join(item.message for item in issues))
    events.append(record)
    atomic_write(paths["learning_events"], events)
    audit(
        paths["audit"],
        "scenario_learning_event_recorded",
        event_id=record["event_id"],
        case_id=case_id,
        expert_id=expert_id,
    )
    return {"status": "recorded", "event": record}


def validate_runtime_schemas(project: Path) -> list[str]:
    """Validate learning input and all current scenario-evolution stores."""
    paths = ensure_runtime(project)
    checks = (
        ("scenario_learning_events.schema.json", project / "data" / "scenario_learning_events.json"),
        ("runtime_scenario_drafts.schema.json", paths["drafts"]),
        ("runtime_scenario_reviews.schema.json", paths["reviews"]),
        ("runtime_published_scenarios.schema.json", paths["published"]),
        ("scenario_learning_events.schema.json", paths["learning_events"]),
    )
    errors: list[str] = []
    for schema_name, data_path in checks:
        schema = load_json(project / "schemas" / schema_name)
        payload = load_json(data_path)
        for issue in Draft202012Validator(schema).iter_errors(payload):
            errors.append(f"{data_path.name}: {issue.message}")
    return errors
