"""Structured Ouroboros tool surface for CasePilot planning."""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
from typing import Any


_PLANNER_PATH = Path(__file__).resolve().with_name("planner.py")
_SPEC = importlib.util.spec_from_file_location("casepilot_build_resolution_planner", _PLANNER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load planner module from {_PLANNER_PATH}")
_PLANNER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PLANNER)

_SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (_SKILL_DIR / "casepilot_project_dir.txt").read_text(encoding="utf-8").strip()
_PROJECT_DIR = (
    Path(_configured).expanduser()
    if _configured
    else (_SKILL_DIR / _locator if not Path(_locator).is_absolute() else Path(_locator))
).resolve()
_RUNTIME_PATH = _PROJECT_DIR / "casepilot" / "runtime.py"
_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "casepilot_build_resolution_runtime", _RUNTIME_PATH
)
if _RUNTIME_SPEC is None or _RUNTIME_SPEC.loader is None:
    raise ImportError(f"Cannot load runtime module from {_RUNTIME_PATH}")
_RUNTIME = importlib.util.module_from_spec(_RUNTIME_SPEC)
_RUNTIME_SPEC.loader.exec_module(_RUNTIME)

MODEL = _PLANNER.MODEL
REASONING_EFFORT = _PLANNER.REASONING_EFFORT
build_plan = _PLANNER.build_plan
validate_input = _PLANNER.validate_input


def register(api: Any) -> None:
    settings = api.get_settings(["OPENROUTER_API_KEY"])

    def generate(
        _ctx: Any = None,
        case: Any = None,
        scenarios: Any = None,
        similar_cases: Any = None,
        expertise_catalog: Any = None,
        revision_context: Any = None,
        run_id: str | None = None,
    ) -> str:
        source = {
            "case": case,
            "expertise_catalog": expertise_catalog,
        }
        if scenarios is not None:
            source["scenarios"] = scenarios
        if similar_cases is not None:
            source["similar_cases"] = similar_cases
        if revision_context is not None:
            source["revision_context"] = revision_context
        errors = validate_input(source)
        if errors:
            return json.dumps(
                {"status": "invalid_input", "errors": errors},
                ensure_ascii=False,
            )
        api_key = str(settings.get("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            return json.dumps(
                {
                    "status": "configuration_error",
                    "errors": ["OPENROUTER_API_KEY is unavailable"],
                },
                ensure_ascii=False,
            )
        try:
            plan, requests = build_plan(source, api_key)
        except Exception as error:
            return json.dumps(
                {
                    "status": "generation_error",
                    "errors": [str(error)],
                    "model": MODEL,
                    "reasoning_effort": REASONING_EFFORT,
                },
                ensure_ascii=False,
            )
        store = _RUNTIME.RuntimeStore(_PROJECT_DIR)
        if revision_context is None:
            if run_id:
                run = next(
                    (item for item in store.read("runs") if item.get("run_id") == run_id),
                    None,
                )
                if run is None or run.get("case_id") != plan["case_id"]:
                    return json.dumps(
                        {"status": "runtime_conflict", "errors": ["run_id is invalid"]},
                        ensure_ascii=False,
                    )
            else:
                run = store.start_run(plan["case_id"])
            plan_id = f"PLAN-{run['run_id']}"
            current = store.current_plan_for_run(str(run["run_id"]))
            if current is not None:
                return json.dumps(
                    {
                        "status": "runtime_conflict",
                        "errors": ["the run already has a plan"],
                        "plan_id": plan_id,
                    },
                    ensure_ascii=False,
                )
            runtime_record = store.seed_plan(
                plan_id,
                1,
                plan,
                run_id=str(run["run_id"]),
            )
        else:
            run = (
                next(
                    (item for item in store.read("runs") if item.get("run_id") == run_id),
                    None,
                )
                if run_id
                else store.latest_run(plan["case_id"])
            )
            current = (
                store.current_plan_for_run(str(run["run_id"]))
                if run is not None
                else None
            )
            if (
                current is None
                or current["plan_version"] != 1
                or current["status"] != "change_requested"
            ):
                return json.dumps(
                    {
                        "status": "revision_not_allowed",
                        "errors": [
                            "version 2 requires the current version 1 in change_requested state"
                        ],
                        "run_id": run_id,
                    },
                    ensure_ascii=False,
                )
            plan_id = str(current["plan_id"])
            runtime_record = store.seed_plan(
                plan_id,
                2,
                plan,
                run_id=str(current["run_id"]),
                supersedes_plan_version=1,
            )
        return json.dumps(
            {
                "status": "ok",
                "plan": plan,
                "runtime": {
                    "run_id": runtime_record["run_id"],
                    "plan_id": runtime_record["plan_id"],
                    "plan_version": runtime_record["plan_version"],
                    "status": runtime_record["status"],
                },
                "metadata": {
                    "model": MODEL,
                    "reasoning_effort": REASONING_EFFORT,
                    "model_requests": requests,
                    "validation": "passed",
                },
            },
            ensure_ascii=False,
        )

    api.register_tool(
        "build_resolution_plan",
        handler=generate,
        description=(
            "Build a validated, read-only CasePilot plan from one validation case, "
            "up to three approved scenario results (preferred) or five legacy "
            "similar-case results, and the allowed expertise catalog. "
            "Never executes the plan. In Chat, summarize the plan for an employee "
            "instead of exposing service JSON unless technical JSON was requested."
        ),
        schema={
            "type": "object",
            "properties": {
                "case": {
                    "type": "object",
                    "description": "Complete validation case without solution fields.",
                    "additionalProperties": True,
                },
                "scenarios": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "object", "additionalProperties": True},
                },
                "similar_cases": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {"type": "object", "additionalProperties": True},
                },
                "expertise_catalog": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "object", "additionalProperties": True},
                },
                "revision_context": {
                    "type": "object",
                    "properties": {
                        "previous_plan": {"type": "object", "additionalProperties": True},
                        "employee_comment": {"type": "string", "minLength": 1},
                    },
                    "required": ["previous_plan", "employee_comment"],
                    "additionalProperties": False,
                },
                "run_id": {
                    "type": "string",
                    "pattern": "^RUN-VAL-[A-Z0-9]+-[0-9]+-[0-9]{4}$",
                },
            },
            "required": ["case", "expertise_catalog"],
            "oneOf": [
                {"required": ["scenarios"]},
                {"required": ["similar_cases"]},
            ],
            "additionalProperties": False,
        },
        timeout_sec=180,
    )
