"""Retrieve approved CasePilot scenarios for one validation case."""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[a-zа-яё0-9_=-]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "для", "или", "как", "при", "что", "это", "после", "клиент",
    "счёт", "счета", "карта", "карты", "закрыть", "закрытие",
}


def _default_data_dir() -> Path:
    configured = os.environ.get("CASEPILOT_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    skill_root = Path(__file__).resolve().parents[1]
    locator = skill_root / "casepilot_data_dir.txt"
    if locator.is_file():
        path = Path(locator.read_text(encoding="utf-8").strip()).expanduser()
        return (path if path.is_absolute() else skill_root / path).resolve()
    for base in (skill_root, *skill_root.parents, Path.cwd(), *Path.cwd().parents):
        candidate = base / "data"
        if (candidate / "scenario_catalog.json").is_file():
            return candidate
    raise FileNotFoundError(
        "CasePilot data directory was not found. Set CASEPILOT_DATA_DIR."
    )


def _load_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"{path.name} must contain an array of objects")
    return payload


def _case_tokens(case: dict[str, Any]) -> list[str]:
    transcript = " ".join(
        str(item.get("text") or "")
        for item in case.get("conversation_transcript", [])
        if isinstance(item, dict)
    )
    system = case.get("synthetic_system_data")
    system_text = (
        " ".join(f"{key}={value}" for key, value in system.items())
        if isinstance(system, dict)
        else ""
    )
    products = " ".join(
        str(item.get("product_type") or "")
        for item in case.get("products", [])
        if isinstance(item, dict)
    )
    text = (
        f"{case.get('case_topic', '')} {case.get('case_subtopic', '')} "
        f"{case.get('case_description', '')} {transcript} {system_text} {products}"
    ).lower()
    return [token for token in _TOKEN_RE.findall(text) if token not in _STOPWORDS]


def _scenario_tokens(scenario: dict[str, Any]) -> list[str]:
    steps = " ".join(
        f"{step.get('action', '')} {step.get('description', '')} "
        f"{step.get('expertise_type', '')}"
        for step in scenario.get("strategy_steps", [])
        if isinstance(step, dict)
    )
    text = " ".join(
        [
            str(scenario.get("title") or ""),
            str(scenario.get("description") or ""),
            " ".join(scenario.get("trigger_conditions") or []),
            " ".join(scenario.get("required_inputs") or []),
            " ".join(scenario.get("product_types") or []),
            " ".join(scenario.get("stop_conditions") or []),
            steps,
        ]
    ).lower()
    return [token for token in _TOKEN_RE.findall(text) if token not in _STOPWORDS]


def normalize_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Convert an MVP-approved candidate to the runtime scenario contract."""
    if scenario.get("status") != "approved_for_mvp":
        return scenario
    strength_rate = {"single_case": 0.75, "moderate": 0.85, "strong": 0.95}
    return {
        "scenario_id": scenario["proposed_scenario_id"],
        "version": 1,
        "status": "approved",
        "approval_scope": "mvp_synthetic_planning_and_mock_execution",
        "title": scenario["title"],
        "case_topic": scenario["case_topic"],
        "case_subtopic": scenario["case_subtopics"][0],
        "case_subtopics": scenario["case_subtopics"],
        "description": scenario["description"],
        "trigger_conditions": scenario["trigger_conditions"],
        "required_inputs": scenario["required_inputs"],
        "product_types": ["debit_card", "current_account"],
        "strategy_steps": [
            {
                "order": step["order"],
                "action": (
                    "request_expertise"
                    if step.get("expertise_type")
                    else step["action"]
                ),
                "description": step["description"],
                "expertise_type": step.get("expertise_type"),
            }
            for step in scenario["strategy_steps"]
        ],
        "allowed_expertises": scenario["allowed_expertises"],
        "stop_conditions": scenario["stop_conditions"],
        "source_case_ids": scenario["source_case_ids"],
        "successful_cases": scenario["evidence_count"],
        "success_rate": strength_rate[scenario["evidence_strength"]],
        "planning_supported": True,
        "execution_supported": True,
    }


def load_runtime_scenarios(data_dir: Path) -> list[dict[str, Any]]:
    approved = _load_array(data_dir / "scenario_catalog.json")
    candidates_path = data_dir / "scenario_candidates.json"
    candidates = _load_array(candidates_path) if candidates_path.is_file() else []
    published_path = data_dir / "runtime" / "published_scenarios.json"
    published = _load_array(published_path) if published_path.is_file() else []
    return approved + published + [
        normalize_scenario(item)
        for item in candidates
        if item.get("status") == "approved_for_mvp"
    ]


def _filter(
    case: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    approved = [normalize_scenario(item) for item in scenarios]
    approved = [item for item in approved if item.get("status") == "approved"]
    exact = [
        item for item in approved
        if item.get("case_topic") == case.get("case_topic")
        and case.get("case_subtopic") in (
            item.get("case_subtopics") or [item.get("case_subtopic")]
        )
    ]
    if exact:
        return exact, "exact_topic_and_subtopic"
    topic = [
        item for item in approved
        if item.get("case_topic") == case.get("case_topic")
    ]
    if topic:
        return topic, "topic_only_fallback"
    return approved, "all_approved_scenarios_fallback"


def _bm25(query: list[str], scenarios: list[dict[str, Any]]) -> dict[str, float]:
    terms = set(query)
    documents = {
        str(item["scenario_id"]): _scenario_tokens(item)
        for item in scenarios
    }
    if not terms or not documents:
        return {key: 0.0 for key in documents}
    average_length = sum(len(tokens) for tokens in documents.values()) / len(documents)
    average_length = average_length or 1.0
    frequencies = {
        term: sum(1 for tokens in documents.values() if term in set(tokens))
        for term in terms
    }
    raw: dict[str, float] = {}
    count = len(documents)
    for scenario_id, tokens in documents.items():
        token_counts = collections.Counter(tokens)
        score = 0.0
        for term in terms:
            frequency = token_counts.get(term, 0)
            if not frequency:
                continue
            docs_with_term = frequencies[term]
            idf = math.log(1 + (count - docs_with_term + 0.5) / (docs_with_term + 0.5))
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * len(tokens) / average_length
            )
            score += idf * frequency * 2.5 / denominator
        raw[scenario_id] = score
    maximum = max(raw.values(), default=0.0)
    return {
        key: (value / maximum if maximum else 0.0)
        for key, value in raw.items()
    }


def _available_inputs(case: dict[str, Any]) -> set[str]:
    result = set(case)
    system = case.get("synthetic_system_data")
    if isinstance(system, dict):
        result.update(
            key for key, value in system.items()
            if value is not None and value != ""
        )
    for product in case.get("products", []):
        if not isinstance(product, dict):
            continue
        if product.get("product_type") == "debit_card":
            result.add("card_id")
        if product.get("product_type") == "current_account":
            result.add("account_id")
    transactions = (
        system.get("transactions")
        if isinstance(system, dict) and isinstance(system.get("transactions"), list)
        else []
    )
    for transaction in transactions:
        if not isinstance(transaction, dict):
            continue
        result.update(
            key for key, value in transaction.items()
            if value is not None and value != ""
        )
        if transaction.get("transaction_id"):
            result.add("original_transaction_id")
        if transaction.get("type") == "refund":
            result.add("expected_refund_amount")
    return result


def _product_types(case: dict[str, Any]) -> set[str]:
    return {
        str(item.get("product_type"))
        for item in case.get("products", [])
        if isinstance(item, dict) and item.get("product_type")
    }


def _closure_code(case: dict[str, Any]) -> str:
    system = case.get("synthetic_system_data")
    return str(system.get("closure_check_code") or "") if isinstance(system, dict) else ""


def find_case_scenarios(
    case: dict[str, Any],
    scenarios: list[dict[str, Any]],
    history: list[dict[str, Any]],
    limit: int = 3,
) -> dict[str, Any]:
    if not str(case.get("case_id") or "").strip():
        raise ValueError("case must contain case_id")
    candidates, filter_stage = _filter(case, scenarios)
    bm25 = _bm25(_case_tokens(case), candidates)
    available = _available_inputs(case)
    products = _product_types(case)
    closure_code = _closure_code(case)
    history_by_id = {str(item.get("case_id")): item for item in history}
    ranked: list[dict[str, Any]] = []
    for scenario in candidates:
        scenario_id = str(scenario["scenario_id"])
        trigger_text = " ".join(scenario.get("trigger_conditions") or [])
        closure_match = bool(closure_code and closure_code in trigger_text)
        scenario_products = set(scenario.get("product_types") or [])
        product_overlap = (
            len(products & scenario_products) / len(products | scenario_products)
            if products | scenario_products else 0.0
        )
        required = set(scenario.get("required_inputs") or [])
        coverage = len(required & available) / len(required) if required else 1.0
        success_rate = float(scenario.get("success_rate") or 0)
        components = {
            "exact_topic_and_subtopic": (
                0.20 if filter_stage == "exact_topic_and_subtopic" else 0.0
            ),
            "closure_reason": 0.40 if closure_match else 0.0,
            "bm25": round(0.25 * bm25.get(scenario_id, 0.0), 6),
            "products": round(0.10 * product_overlap, 6),
            "required_input_coverage": round(0.15 * coverage, 6),
            "success_rate": round(0.10 * success_rate, 6),
        }
        missing = sorted(required - available)
        explanations = [
            f"фильтр {filter_stage}",
            f"BM25 {bm25.get(scenario_id, 0.0):.2f}",
            f"покрытие входов {coverage:.2f}",
            f"успешность {success_rate:.2f}",
        ]
        if closure_match:
            explanations.append(f"совпадает причина {closure_code}")
        if missing:
            explanations.append("не хватает: " + ", ".join(missing))
        source_ids = list(scenario.get("source_case_ids") or [])
        ranked.append(
            {
                "scenario_id": scenario_id,
                "score": round(min(1.0, sum(components.values())), 4),
                "explanation": "; ".join(explanations),
                "score_components": components,
                "missing_required_inputs": missing,
                "scenario": scenario,
                "source_cases": [
                    history_by_id[source_id]
                    for source_id in source_ids
                    if source_id in history_by_id
                ],
            }
        )
    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            -float(item["scenario"].get("success_rate") or 0),
            str(item["scenario_id"]),
        )
    )
    bounded = max(1, min(int(limit), 3))
    return {
        "status": "ok",
        "query_case_id": case["case_id"],
        "algorithm": "scenario_topic_filter_bm25_business_rerank_v1",
        "filter_stage": filter_stage,
        "candidate_count": len(candidates),
        "limit": bounded,
        "results": ranked[:bounded],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-json", required=True)
    parser.add_argument("--data-dir", type=Path, default=_default_data_dir())
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    try:
        case = json.loads(args.case_json)
        if isinstance(case, dict) and isinstance(case.get("case"), dict):
            case = case["case"]
        if not isinstance(case, dict):
            raise ValueError("--case-json must decode to an object")
        result = find_case_scenarios(
            case,
            load_runtime_scenarios(args.data_dir),
            _load_array(args.data_dir / "historical_cases.json"),
            args.limit,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "status": "error",
            "query_case_id": None,
            "algorithm": "scenario_topic_filter_bm25_business_rerank_v1",
            "filter_stage": None,
            "candidate_count": 0,
            "limit": max(1, min(args.limit, 3)),
            "results": [],
            "error": str(error),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
