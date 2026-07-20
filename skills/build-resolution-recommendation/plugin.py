"""Ouroboros tool for a persisted CasePilot resolution recommendation."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR / "casepilot_project_dir.txt").read_text(encoding="utf-8").strip()
PROJECT_DIR = (
    Path(_configured).expanduser()
    if _configured
    else (SKILL_DIR / _locator if not Path(_locator).is_absolute() else Path(_locator))
).resolve()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECOMMENDER = _load_module(
    "casepilot_resolution_recommendation",
    SKILL_DIR / "recommendation.py",
)
RUNTIME = _load_module(
    "casepilot_resolution_recommendation_runtime",
    PROJECT_DIR / "casepilot" / "runtime.py",
)


def create_recommendation(
    execution_id: str,
    api_key: str,
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    store = RUNTIME.RuntimeStore(PROJECT_DIR)
    existing = store.recommendation_for_execution(execution_id)
    if existing is not None:
        return existing
    execution = next(
        (
            item
            for item in store.read("executions")
            if item.get("execution_id") == execution_id
        ),
        None,
    )
    if execution is None:
        raise LookupError("execution not found")
    if execution.get("execution_status") not in RECOMMENDER.TERMINAL_STATUSES:
        raise ValueError("recommendation requires a terminal execution")
    plan_record = store.plan(
        str(execution["plan_id"]),
        int(execution["plan_version"]),
    )
    if plan_record is None:
        raise LookupError("plan not found")
    cases = RUNTIME.load_json(PROJECT_DIR / "data" / "validation_cases.json")
    case = next(
        (item for item in cases if item.get("case_id") == execution.get("case_id")),
        None,
    )
    if case is None:
        raise LookupError("case not found")
    source = {
        "case": case,
        "plan": plan_record["plan"],
        "execution": execution,
    }
    errors = RECOMMENDER.validate_source(source)
    if errors:
        raise ValueError("; ".join(errors))

    fallback_reason = None
    requests = 0
    if use_llm and api_key:
        try:
            recommendation, requests = RECOMMENDER.build_recommendation(
                source,
                api_key,
                PROJECT_DIR,
            )
            status = "generated"
        except Exception as error:
            fallback_reason = str(error)
            recommendation = RECOMMENDER.deterministic_fallback(source)
            status = "fallback"
    else:
        fallback_reason = (
            "LLM generation disabled"
            if not use_llm
            else "OPENROUTER_API_KEY is unavailable"
        )
        recommendation = RECOMMENDER.deterministic_fallback(source)
        status = "fallback"
    return store.save_recommendation(
        execution,
        recommendation,
        status=status,
        metadata={
            "model": RECOMMENDER.MODEL if use_llm and api_key else None,
            "reasoning_effort": (
                RECOMMENDER.REASONING_EFFORT if use_llm and api_key else None
            ),
            "model_requests": requests,
            "validation": "passed" if status == "generated" else "fallback",
            "fallback_reason": fallback_reason,
        },
    )


def register(api: Any) -> None:
    settings = api.get_settings(["OPENROUTER_API_KEY"])

    def generate(_ctx: Any = None, execution_id: str = "") -> str:
        try:
            record = create_recommendation(
                execution_id,
                str(settings.get("OPENROUTER_API_KEY") or "").strip(),
            )
            result = {"status": "ok", **record}
        except Exception as error:
            result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)

    api.register_tool(
        "build_resolution_rec",
        handler=generate,
        description=(
            "Create one validated, evidence-bound recommendation for a terminal "
            "CasePilot execution and persist it in runtime."
        ),
        schema={
            "type": "object",
            "properties": {"execution_id": {"type": "string", "minLength": 1}},
            "required": ["execution_id"],
            "additionalProperties": False,
        },
        timeout_sec=180,
    )
