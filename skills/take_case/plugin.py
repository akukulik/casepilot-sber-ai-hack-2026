"""Primary employee-facing CasePilot workflow for one case_id."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = SKILL_DIR.joinpath("casepilot_project_dir.txt").read_text(encoding="utf-8").strip()
PROJECT_DIR = (
    Path(_configured).expanduser()
    if _configured
    else (SKILL_DIR / _locator if not Path(_locator).is_absolute() else Path(_locator))
).resolve()
DATA_DIR = PROJECT_DIR / "data"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LOAD_CASE = _load_module(
    "casepilot_take_case_loader",
    PROJECT_DIR / "skills" / "load_case" / "scripts" / "load_case.py",
)
FIND_SCENARIOS = _load_module(
    "casepilot_take_case_scenario_retrieval",
    PROJECT_DIR
    / "skills"
    / "find_case_scenarios"
    / "scripts"
    / "find_case_scenarios.py",
)
PLANNER = _load_module(
    "casepilot_take_case_planner",
    PROJECT_DIR / "skills" / "build_resolution_plan" / "planner.py",
)
RUNTIME = _load_module(
    "casepilot_take_case_runtime",
    PROJECT_DIR / "casepilot" / "runtime.py",
)


def _operator_view(
    case: dict[str, Any],
    plan: dict[str, Any],
    runtime_record: dict[str, Any],
) -> dict[str, Any]:
    scenarios = plan.get("scenarios_used") or []
    if not scenarios and plan.get("similar_cases_used"):
        legacy_by_id = {
            str(item.get("case_id")): item
            for item in plan.get("similar_cases_used", [])
        }
        catalog = json.loads(
            DATA_DIR.joinpath("scenario_catalog.json").read_text(encoding="utf-8")
        )
        migrated = []
        for scenario in catalog:
            matching = [
                legacy_by_id[case_id]
                for case_id in scenario.get("source_case_ids", [])
                if case_id in legacy_by_id
            ]
            if matching:
                best = max(
                    matching,
                    key=lambda item: float(item.get("similarity_score") or 0),
                )
                migrated.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "similarity_score": best.get("similarity_score", 0),
                        "useful_pattern": scenario["description"],
                        "source_case_ids": scenario.get("source_case_ids", []),
                    }
                )
        scenarios = sorted(
            migrated,
            key=lambda item: -float(item.get("similarity_score") or 0),
        )
    strongest = scenarios[0] if scenarios else None
    employee_actions = (
        [
            {"command": "Подтверждаю", "decision": "approve_plan"},
            {"command": "Изменить: <комментарий>", "decision": "request_change"},
            {"command": "Беру вручную", "decision": "manual_review"},
        ]
        if runtime_record["status"] == "proposed"
        else []
    )
    return {
        "case": {
            "case_id": case["case_id"],
            "created_at": case.get("created_at"),
            "topic": case.get("case_topic"),
            "subtopic": case.get("case_subtopic"),
            "priority": case.get("priority"),
            "description": case.get("case_description"),
        },
        "problem": plan.get("identified_problem"),
        "primary_scenario": strongest,
        "steps": [
            {
                "order": step.get("order"),
                "description": step.get("description"),
                "action": step.get("action"),
                "expertise_type": step.get("expertise_type"),
            }
            for step in plan.get("proposed_plan", [])
        ],
        "required_expertises": plan.get("required_expertises", []),
        "confidence": plan.get("confidence"),
        "run_id": runtime_record["run_id"],
        "plan_id": runtime_record["plan_id"],
        "plan_version": runtime_record["plan_version"],
        "plan_status": runtime_record["status"],
        "employee_actions": employee_actions,
    }


def _operator_message(view: dict[str, Any]) -> str:
    case = view["case"]
    problem = view.get("problem") or {}
    scenario = view.get("primary_scenario") or {}
    confidence = view.get("confidence") or {}
    lines = [
        f"## Кейс {case['case_id']}",
        f"**{case.get('topic')} / {case.get('subtopic')}**",
        f"Создан: {case.get('created_at')} · Приоритет: {case.get('priority')}",
        "",
        f"**Проблема:** {problem.get('description') or case.get('description')}",
        "",
    ]
    evidence = problem.get("evidence") or []
    if evidence:
        lines.extend(["**Ключевые признаки:**"])
        lines.extend(f"- {item}" for item in evidence)
        lines.append("")
    if scenario:
        lines.extend(
            [
                "**Основной сценарий:** "
                f"{scenario.get('scenario_id')} — "
                f"{float(scenario.get('similarity_score') or 0):.0%}",
                f"{scenario.get('useful_pattern')}",
                "",
            ]
        )
    lines.append(f"**Стратегия решения — {len(view['steps'])} шагов:**")
    lines.extend(
        f"{step['order']}. {step['description']}"
        for step in view["steps"]
    )
    lines.extend(
        [
            "",
            f"**Уверенность:** {confidence.get('level')} "
            f"({float(confidence.get('score') or 0):.0%}) — {confidence.get('reason')}",
            "",
        ]
    )
    if view["employee_actions"]:
        lines.extend(
            [
                "**Выберите действие:**",
                "- `Подтверждаю`",
                "- `Изменить: <комментарий>`",
                "- `Беру вручную`",
            ]
        )
    else:
        lines.append(
            f"План открыт только для просмотра: текущий статус — "
            f"`{view['plan_status']}`."
        )
    return "\n".join(lines)


def prepare_context(case_id: str) -> dict[str, Any]:
    loaded = LOAD_CASE.load_case(case_id, DATA_DIR)
    if loaded.get("status") != "ok":
        return loaded
    case = loaded["case"]
    retrieval = FIND_SCENARIOS.find_case_scenarios(
        case,
        FIND_SCENARIOS.load_runtime_scenarios(DATA_DIR),
        FIND_SCENARIOS._load_array(DATA_DIR / "historical_cases.json"),
        3,
    )
    expertise_catalog = json.loads(
        DATA_DIR.joinpath("expertise_catalog.json").read_text(encoding="utf-8")
    )
    return {
        "status": "ok",
        "case": case,
        "scenarios": retrieval["results"],
        "retrieval": {
            "algorithm": retrieval["algorithm"],
            "filter_stage": retrieval["filter_stage"],
            "candidate_count": retrieval["candidate_count"],
            "returned_count": len(retrieval["results"]),
        },
        "expertise_catalog": expertise_catalog,
    }


def register(api: Any) -> None:
    settings = api.get_settings(["OPENROUTER_API_KEY"])

    def open_latest_case_run(_ctx: Any = None, case_id: str = "") -> str:
        try:
            context = prepare_context(case_id.strip())
            if context.get("status") != "ok":
                return json.dumps(context, ensure_ascii=False)
            case = context["case"]
            store = RUNTIME.RuntimeStore(PROJECT_DIR)
            latest = store.latest_run(case["case_id"])
            current = (
                store.current_plan_for_run(str(latest["run_id"]))
                if latest is not None
                else None
            )
            if current is None:
                return json.dumps(
                    {
                        "status": "not_found",
                        "errors": ["no previous run exists for this case"],
                        "case_id": case["case_id"],
                    },
                    ensure_ascii=False,
                )
            view = _operator_view(case, current["plan"], current)
            return json.dumps(
                {
                    "status": "existing_plan",
                    "runtime": {
                        "run_id": current["run_id"],
                        "plan_id": current["plan_id"],
                        "plan_version": current["plan_version"],
                        "status": current["status"],
                    },
                    "operator_view": view,
                    "operator_message": _operator_message(view),
                    "metadata": {"model_requests": 0, "reason": "latest_run_reopen"},
                },
                ensure_ascii=False,
            )
        except Exception as error:
            return json.dumps(
                {"status": "workflow_error", "errors": [str(error)]},
                ensure_ascii=False,
            )

    def take_case(_ctx: Any = None, case_id: str = "") -> str:
        try:
            context = prepare_context(case_id.strip())
            if context.get("status") != "ok":
                return json.dumps(context, ensure_ascii=False)
            case = context["case"]
            store = RUNTIME.RuntimeStore(PROJECT_DIR)
            api_key = str(settings.get("OPENROUTER_API_KEY") or "").strip()
            if not api_key:
                return json.dumps(
                    {
                        "status": "configuration_error",
                        "errors": ["OPENROUTER_API_KEY is unavailable"],
                    },
                    ensure_ascii=False,
                )
            source = {
                "case": case,
                "scenarios": context["scenarios"],
                "expertise_catalog": context["expertise_catalog"],
            }
            errors = PLANNER.validate_input(source)
            if errors:
                return json.dumps(
                    {"status": "invalid_input", "errors": errors},
                    ensure_ascii=False,
                )
            run = store.start_run(case["case_id"])
            try:
                plan, requests = PLANNER.build_plan(source, api_key)
            except Exception:
                store.update_run_status(run["run_id"], "failed")
                raise
            plan_id = f"PLAN-{run['run_id']}"
            runtime_record = store.seed_plan(
                plan_id,
                1,
                plan,
                run_id=run["run_id"],
            )
            view = _operator_view(case, plan, runtime_record)
            return json.dumps(
                {
                    "status": "ready_for_review",
                    "runtime": {
                        "run_id": runtime_record["run_id"],
                        "plan_id": runtime_record["plan_id"],
                        "plan_version": runtime_record["plan_version"],
                        "status": runtime_record["status"],
                    },
                    "retrieval": context["retrieval"],
                    "operator_view": view,
                    "operator_message": _operator_message(view),
                    "metadata": {
                        "model": PLANNER.MODEL,
                        "reasoning_effort": PLANNER.REASONING_EFFORT,
                        "model_requests": requests,
                        "validation": "passed",
                    },
                },
                ensure_ascii=False,
            )
        except Exception as error:
            return json.dumps(
                {
                    "status": "workflow_error",
                    "errors": [str(error)],
                },
                ensure_ascii=False,
            )

    api.register_tool(
        "take_case",
        handler=take_case,
        description=(
            "Primary CasePilot operator workflow. Automatically use when the user "
            "supplies a CasePilot case_id (for example VAL-DC-002) or asks to take "
            "a case into work. Load the case, retrieve top-3 approved scenarios, "
            "build and persist a proposed plan, and return an employee review card. "
            "Every call starts a new independent run, even when the same case_id "
            "was completed earlier. Never reopen an old plan with this tool. "
            "Never approve or execute. In Chat render only operator_message, then "
            "accept: 'Подтверждаю', 'Изменить: ...', or 'Беру вручную'."
        ),
        schema={
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "string",
                    "pattern": "^VAL-[A-Z0-9]+-[0-9]+$",
                }
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
        timeout_sec=180,
    )

    api.register_tool(
        "open_latest_case_run",
        handler=open_latest_case_run,
        description=(
            "Open the latest persisted CasePilot run without an LLM call. Use only "
            "when the employee explicitly asks to view the previous/latest run. "
            "Never use for a bare case_id or a request to take a case into work."
        ),
        schema={
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "string",
                    "pattern": "^VAL-[A-Z0-9]+-[0-9]+$",
                }
            },
            "required": ["case_id"],
            "additionalProperties": False,
        },
        timeout_sec=30,
    )
