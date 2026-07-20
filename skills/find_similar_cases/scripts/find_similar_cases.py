"""Find explainably similar historical CasePilot cases."""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
from pathlib import Path
from typing import Any


_DATA_FILE = "historical_cases.json"
_FORBIDDEN_INPUT_FIELDS = {"resolution_plan", "expertise_results", "final_result"}
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "для",
    "или",
    "как",
    "при",
    "что",
    "это",
    "был",
    "была",
    "были",
    "после",
    "клиент",
    "счёт",
    "счета",
    "карта",
    "карты",
    "закрыть",
    "закрытие",
}


def _default_data_dir() -> Path:
    configured = os.environ.get("CASEPILOT_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    skill_root = Path(__file__).resolve().parents[1]
    locator = skill_root / "casepilot_data_dir.txt"
    if locator.is_file():
        located = locator.read_text(encoding="utf-8").strip()
        if located:
            path = Path(located).expanduser()
            return (path if path.is_absolute() else skill_root / path).resolve()

    for base in (skill_root, *skill_root.parents, Path.cwd(), *Path.cwd().parents):
        candidate = base / "data"
        if (candidate / _DATA_FILE).is_file():
            return candidate

    raise FileNotFoundError(
        "CasePilot data directory was not found. Set CASEPILOT_DATA_DIR, "
        "create casepilot_data_dir.txt in the Skill root, or pass --data-dir."
    )


def _load_history(data_dir: Path) -> list[dict[str, Any]]:
    with (data_dir / _DATA_FILE).open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"{_DATA_FILE} must contain an array of objects")
    return payload


def _tokens(case: dict[str, Any]) -> list[str]:
    transcript = " ".join(
        str(item.get("text") or "")
        for item in case.get("conversation_transcript", [])
        if isinstance(item, dict)
    )
    system_data = case.get("synthetic_system_data")
    system_text = (
        " ".join(f"{key} {value}" for key, value in system_data.items())
        if isinstance(system_data, dict)
        else ""
    )
    product_text = " ".join(sorted(_product_types(case)))
    text = (
        f"{case.get('case_description', '')} {transcript} "
        f"{system_text} {product_text}"
    ).lower()
    return [token for token in _TOKEN_RE.findall(text) if token not in _STOPWORDS]


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _product_types(case: dict[str, Any]) -> set[str]:
    return {
        str(item.get("product_type") or "")
        for item in case.get("products", [])
        if isinstance(item, dict) and item.get("product_type")
    }


def _closure_code(case: dict[str, Any]) -> str:
    system_data = case.get("synthetic_system_data")
    return (
        str(system_data.get("closure_check_code") or "")
        if isinstance(system_data, dict)
        else ""
    )


def _filter_candidates(
    validation_case: dict[str, Any],
    historical_cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    topic = validation_case.get("case_topic")
    subtopic = validation_case.get("case_subtopic")
    exact = [
        case
        for case in historical_cases
        if case.get("case_topic") == topic and case.get("case_subtopic") == subtopic
    ]
    if exact:
        return exact, "exact_topic_and_subtopic"
    topic_only = [case for case in historical_cases if case.get("case_topic") == topic]
    if topic_only:
        return topic_only, "topic_only_fallback"
    return historical_cases, "all_history_fallback"


def _bm25_scores(
    validation_case: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> dict[str, float]:
    query_terms = set(_tokens(validation_case))
    documents = {
        str(case.get("case_id") or ""): _tokens(case)
        for case in candidates
    }
    if not documents or not query_terms:
        return {case_id: 0.0 for case_id in documents}
    average_length = sum(len(tokens) for tokens in documents.values()) / len(documents)
    average_length = average_length or 1.0
    document_frequency = {
        term: sum(1 for tokens in documents.values() if term in set(tokens))
        for term in query_terms
    }
    raw: dict[str, float] = {}
    document_count = len(documents)
    for case_id, tokens in documents.items():
        frequencies = collections.Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            frequency_in_docs = document_frequency[term]
            inverse_document_frequency = math.log(
                1 + (document_count - frequency_in_docs + 0.5) / (frequency_in_docs + 0.5)
            )
            denominator = frequency + k1 * (1 - b + b * length / average_length)
            score += inverse_document_frequency * (
                frequency * (k1 + 1) / denominator
            )
        raw[case_id] = score
    maximum = max(raw.values(), default=0.0)
    return {
        case_id: (score / maximum if maximum else 0.0)
        for case_id, score in raw.items()
    }


def _score(
    validation_case: dict[str, Any],
    historical_case: dict[str, Any],
    bm25_normalized: float,
) -> tuple[float, list[str], dict[str, float]]:
    components: dict[str, float] = {}
    explanations: list[str] = []

    validation_code = _closure_code(validation_case)
    historical_code = _closure_code(historical_case)
    if validation_code and validation_code == historical_code:
        components["closure_reason"] = 0.45
        explanations.append(f"совпадает причина блокировки {validation_code}")
    else:
        components["closure_reason"] = 0.0

    if validation_case.get("priority") == historical_case.get("priority"):
        components["priority"] = 0.05
        explanations.append("совпадает приоритет")
    else:
        components["priority"] = 0.0

    product_overlap = _jaccard(
        _product_types(validation_case),
        _product_types(historical_case),
    )
    components["products"] = round(0.15 * product_overlap, 6)
    if product_overlap:
        explanations.append(f"пересечение типов продуктов {product_overlap:.2f}")

    components["bm25"] = round(0.35 * bm25_normalized, 6)
    if bm25_normalized:
        explanations.append(f"BM25-сходство {bm25_normalized:.2f}")

    return round(sum(components.values()), 4), explanations, components


def find_similar_cases(
    validation_case: dict[str, Any],
    historical_cases: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    leaked = sorted(_FORBIDDEN_INPUT_FIELDS.intersection(validation_case))
    if leaked:
        raise ValueError(f"validation case contains hidden solution fields: {leaked}")
    if not validation_case.get("case_id"):
        raise ValueError("validation case must contain case_id")

    candidates, filter_stage = _filter_candidates(validation_case, historical_cases)
    bm25 = _bm25_scores(validation_case, candidates)
    ranked: list[dict[str, Any]] = []
    for historical_case in candidates:
        case_id = str(historical_case.get("case_id") or "")
        score, explanation_parts, components = _score(
            validation_case,
            historical_case,
            bm25.get(case_id, 0.0),
        )
        ranked.append(
            {
                "case_id": historical_case.get("case_id"),
                "score": score,
                "explanation": "; ".join(explanation_parts) or "совпадений не найдено",
                "score_components": components,
                "historical_case": historical_case,
                "resolution_plan": historical_case.get("resolution_plan", []),
                "expertise_results": historical_case.get("expertise_results", []),
                "final_result": historical_case.get("final_result"),
            }
        )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["case_id"])))
    bounded_limit = max(1, min(limit, 5))
    return {
        "status": "ok",
        "query_case_id": validation_case["case_id"],
        "algorithm": "topic_subtopic_filter_bm25_business_rerank_v2",
        "filter_stage": filter_stage,
        "candidate_count": len(candidates),
        "limit": bounded_limit,
        "results": ranked[:bounded_limit],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-json", required=True, help="Validation-case JSON object")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_default_data_dir(),
        help="Directory containing historical_cases.json",
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum results, capped at 5")
    args = parser.parse_args()
    try:
        validation_case = json.loads(args.case_json)
        if not isinstance(validation_case, dict):
            raise ValueError("--case-json must decode to an object")
        if isinstance(validation_case.get("case"), dict):
            validation_case = validation_case["case"]
        result = find_similar_cases(
            validation_case,
            _load_history(args.data_dir),
            args.limit,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        result = {
            "status": "error",
            "query_case_id": None,
            "algorithm": "topic_subtopic_filter_bm25_business_rerank_v2",
            "filter_stage": None,
            "candidate_count": 0,
            "limit": max(1, min(args.limit, 5)),
            "results": [],
            "error": str(error),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
