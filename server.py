"""Tiny dependency-free local server for the CasePilot demo frontend."""

from __future__ import annotations

import json
import importlib.util
import mimetypes
import os
import random
import shutil
import sys
import threading
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


CODE_ROOT = Path(__file__).resolve().parent
ROOT = CODE_ROOT
FRONTEND = ROOT / "frontend"
DATA = ROOT / "data"
HOST = os.environ.get("CASEPILOT_HOST", "127.0.0.1")
PORT = int(os.environ.get("CASEPILOT_PORT", "8080"))
TAKE_CASE_LOCK = threading.Lock()
TAKE_CASE_HANDLER = None
EXECUTION_LOCK = threading.Lock()
EXECUTION_THREADS: dict[tuple[str, int], threading.Thread] = {}
PRESENTATION_PROGRESS: dict[str, dict] = {}
PRESENTATION_DELAYS_ENABLED = True
RECOMMENDATION_LLM_ENABLED = True
OUROBOROS_PYTHON_CANDIDATES = tuple(
    Path(value).expanduser()
    for value in (
        os.environ.get("OUROBOROS_PYTHON", ""),
        shutil.which("python3") or "",
        "/Applications/Ouroboros.app/Contents/Resources/python-standalone/bin/python3",
    )
    if value
)


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def ensure_skill_runtime() -> None:
    """Restart under a Python with jsonschema when the current one lacks it."""
    try:
        import jsonschema  # noqa: F401
    except ModuleNotFoundError:
        runtime = next(
            (
                candidate
                for candidate in OUROBOROS_PYTHON_CANDIDATES
                if candidate.is_file() and candidate.resolve() != Path(sys.executable).resolve()
            ),
            None,
        )
        if runtime is None:
            raise RuntimeError(
                "Python dependency 'jsonschema' is missing. "
                "Run: python3 -m pip install -r requirements.txt"
            )
        os.execv(
            str(runtime),
            [str(runtime), str(Path(__file__).resolve()), *os.sys.argv[1:]],
        )


def latest_plan(case_id: str) -> dict | None:
    plans = [
        item for item in read_json(DATA / "runtime" / "plans.json")
        if item.get("case_id") == case_id
    ]
    if not plans:
        return None
    return max(
        plans,
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item.get("plan_version") or 0),
        ),
    )


def plan_by_identity(plan_id: str, plan_version: int) -> dict | None:
    return next(
        (
            item
            for item in read_json(DATA / "runtime" / "plans.json")
            if item.get("plan_id") == plan_id
            and int(item.get("plan_version") or 0) == plan_version
        ),
        None,
    )


def runtime_module():
    module_path = CODE_ROOT / "casepilot" / "runtime.py"
    spec = importlib.util.spec_from_file_location("casepilot_frontend_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CasePilot runtime is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execution_by_id(execution_id: str) -> dict | None:
    return next(
        (
            item
            for item in read_json(DATA / "runtime" / "executions.json")
            if item.get("execution_id") == execution_id
        ),
        None,
    )


def recommendation_by_execution(execution_id: str) -> dict | None:
    path = DATA / "runtime" / "recommendations.json"
    if not path.is_file():
        return None
    return next(
        (
            item
            for item in read_json(path)
            if item.get("execution_id") == execution_id
        ),
        None,
    )


def executions_for_plan(plan_id: str, plan_version: int) -> list[dict]:
    return [
        item
        for item in read_json(DATA / "runtime" / "executions.json")
        if item.get("plan_id") == plan_id
        and int(item.get("plan_version") or 0) == plan_version
    ]


ACTION_TITLES = {
    "check_account_state": "Проверка состояния счёта",
    "check_pending_operations": "Проверка незавершённых операций",
    "request_expertise": "Запрос профильной экспертизы",
    "check_account_closure_eligibility": "Проверка возможности закрытия",
    "wait_for_settlement": "Ожидание завершения расчётов",
    "record_post_closure_instruction": "Подготовка инструкции",
    "collect_compliance_evidence": "Сбор материалов проверки",
    "match_collection_surplus": "Сверка операции",
    "prepare_resolution_decision": "Подготовка решения",
}

ACTION_LABELS = {
    "check_account_state": "Проверка",
    "check_pending_operations": "Проверка",
    "request_expertise": "Экспертиза",
    "check_account_closure_eligibility": "Проверка",
    "wait_for_settlement": "Действие",
    "record_post_closure_instruction": "Действие",
    "collect_compliance_evidence": "Действие",
    "match_collection_surplus": "Действие",
    "prepare_resolution_decision": "Действие",
}

RESULT_SUMMARIES = {
    "account_state_retrieved": "Состояние счёта и ограничения проверены",
    "pending_reversal_confirmed": "Незавершённая операция подтверждена",
    "no_pending_operations": "Незавершённых операций не найдено",
    "active_hold_confirmed": "Активный карточный холд подтверждён",
    "zero_balance_confirmed": "Нулевой контрольный остаток подтверждён",
    "manual_legal_review_required": "Требуется ручная юридическая проверка",
    "closure_eligible": "Препятствий для закрытия не обнаружено",
    "closure_not_eligible": "Сохраняются препятствия для закрытия",
    "settlement_wait_recorded": "Ожидание расчёта зафиксировано",
    "post_closure_instruction_drafted": "Инструкция подготовлена",
    "compliance_evidence_checklist_prepared": "Перечень документов подготовлен",
    "collection_match_review_prepared": "Сверка подготовлена",
    "resolution_decision_drafted": "Решение подготовлено для сотрудника",
}

STATUS_LABELS = {
    "executing": "План выполняется",
    "completed": "Проверки по плану завершены",
    "waiting_for_information": "Нужны дополнительные данные",
    "replan_required": "Требуется обновление плана",
    "manual_review": "Требуется ручная проверка",
    "failed": "Выполнение остановлено",
}

RECOMMENDATION_LABELS = {
    "approve_case_closure": "Можно закрыть кейс с ответом клиенту.",
    "wait_for_reversal": "Дождаться завершения карточной операции и повторить проверку.",
    "employee_review_resolution": "Проверить результаты и принять финальное решение.",
    "request_missing_information": "Добавить недостающие сведения перед продолжением.",
    "build_revised_plan": "Сформировать обновлённый план с учётом результатов.",
    "perform_manual_review": "Продолжить разбор кейса самостоятельно.",
    "inspect_execution_failure": "Проверить причину остановки и решить, как продолжить.",
}

BLOCKER_LABELS = {
    "active_account_restriction": "Действующее ограничение по счёту",
    "negative_balance": "Отрицательный остаток",
    "active_authorization_hold": "Незавершённая карточная операция",
    "closure_eligibility_not_checked": "Возможность закрытия ещё не проверена",
}

FIELD_LABELS = {
    "restriction_reference": "Номер документа-основания ограничения",
    "authorization_events": "Данные об авторизациях",
    "pending_operations": "Данные о незавершённых операциях",
    "fee_events": "Данные о комиссиях",
    "account_id": "Идентификатор счёта",
    "card_id": "Идентификатор карты",
}


def safe_error(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Не удалось выполнить шаг"
    if "missing required expertise inputs:" in text:
        return "Не хватает обязательных данных для экспертизы"
    if "deviation" in text or "forbidden" in text or "contract mismatch" in text:
        return "Результат проверки требует ручного контроля"
    return "Шаг не удалось завершить"


def compact_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    boundary = text[: limit + 1].rfind(" ")
    return text[: boundary if boundary > 0 else limit].rstrip(" ,;:") + "…"


def compact_recommendation_dto(value: dict | None) -> dict | None:
    if not value:
        return None
    compact = deepcopy(value)
    compact["title"] = compact_text(compact.get("title"), 100)
    compact["summary"] = compact_text(compact.get("summary"), 280)
    compact["key_findings"] = [
        {**item, "finding": compact_text(item.get("finding"), 180)}
        for item in compact.get("key_findings", [])[:4]
    ]
    compact["remaining_risks"] = [
        compact_text(item, 180)
        for item in compact.get("remaining_risks", [])[:3]
    ]
    compact["employee_actions"] = [
        compact_text(item, 160)
        for item in compact.get("employee_actions", [])[:3]
    ]
    if compact.get("client_response_draft") is not None:
        compact["client_response_draft"] = compact_text(
            compact.get("client_response_draft"),
            500,
        )
    return compact


def execution_dto(execution: dict) -> dict:
    plan_record = plan_by_identity(
        str(execution["plan_id"]),
        int(execution["plan_version"]),
    )
    planned_steps = (
        sorted(
            plan_record["plan"].get("proposed_plan", []),
            key=lambda item: int(item.get("order") or 0),
        )
        if plan_record
        else []
    )
    runtime_steps = {
        str(item.get("step_id")): item
        for item in execution.get("steps", [])
    }
    steps = []
    for planned in planned_steps:
        current = runtime_steps.get(str(planned.get("step_id")), {})
        result = current.get("result") if isinstance(current.get("result"), dict) else {}
        result_code = str(result.get("result_code") or "")
        step = {
            "step_id": planned.get("step_id"),
            "order": planned.get("order"),
            "action": planned.get("action"),
            "action_label": ACTION_LABELS.get(str(planned.get("action")), "Проверка"),
            "title": planned.get("description")
            or ACTION_TITLES.get(str(planned.get("action")), "Шаг плана"),
            "status": current.get("status", "pending"),
            "started_at": current.get("started_at"),
            "completed_at": current.get("completed_at"),
        }
        if result:
            step["result"] = {
                "result_code": result_code,
                "summary": RESULT_SUMMARIES.get(
                    result_code,
                    str(result.get("explanation") or "Шаг завершён"),
                ),
            }
        if current.get("error"):
            step["error_message"] = safe_error(current.get("error"))
        if current.get("missing_fields"):
            step["missing_fields"] = [
                FIELD_LABELS.get(str(item), str(item).replace("_", " "))
                for item in current["missing_fields"]
            ]
        steps.append(step)

    status = str(execution.get("execution_status") or "failed")
    inferred_missing = [
        item
        for runtime_step in execution.get("steps", [])
        for item in runtime_step.get("missing_fields", [])
    ]
    recommendation = str(
        execution.get("recommended_next_action")
        or {
            "waiting_for_information": "request_missing_information",
            "replan_required": "build_revised_plan",
            "manual_review": "perform_manual_review",
            "failed": "inspect_execution_failure",
        }.get(status, "")
    )
    recommendation_record = recommendation_by_execution(
        str(execution.get("execution_id") or "")
    )
    resolution_recommendation = compact_recommendation_dto(
        recommendation_record.get("recommendation")
        if recommendation_record
        and isinstance(recommendation_record.get("recommendation"), dict)
        else None
    )
    active = EXECUTION_THREADS.get(
        (str(execution.get("plan_id") or ""), int(execution.get("plan_version") or 0))
    )
    recommendation_status = (
        str(recommendation_record.get("status"))
        if recommendation_record
        else "generating"
        if execution.get("execution_status") in {
            "completed",
            "failed",
            "waiting_for_information",
            "replan_required",
            "manual_review",
        }
        and active is not None
        and active.is_alive()
        else "not_created"
    )
    dto = {
        "execution_id": execution.get("execution_id"),
        "run_id": execution.get("run_id"),
        "case_id": execution.get("case_id"),
        "plan_id": execution.get("plan_id"),
        "plan_version": execution.get("plan_version"),
        "execution_status": status,
        "status_label": STATUS_LABELS.get(status, "Статус выполнения"),
        "started_at": execution.get("started_at"),
        "completed_at": execution.get("completed_at"),
        "steps": steps,
        "resolved_blockers": execution.get("resolved_blockers", []),
        "remaining_blockers": [
            BLOCKER_LABELS.get(str(item), str(item).replace("_", " "))
            for item in execution.get("remaining_blockers", [])
        ],
        "missing_fields": [
            FIELD_LABELS.get(str(item), str(item).replace("_", " "))
            for item in (execution.get("missing_fields") or inferred_missing)
        ],
        "stop_reason": (
            execution.get("stop_reason")
            if status == "manual_review"
            else None
        ),
        "requires_final_employee_approval": bool(
            execution.get("requires_final_employee_approval")
        ),
        "recommended_next_action": recommendation,
        "recommendation": RECOMMENDATION_LABELS.get(
            recommendation,
            "Проверить результаты выполнения.",
        ),
        "recommendation_status": recommendation_status,
        "resolution_recommendation": resolution_recommendation,
        "client_response_draft": (
            resolution_recommendation.get("client_response_draft")
            if resolution_recommendation
            else execution.get("client_response_draft")
        ),
    }
    return apply_presentation_progress(dto)


def start_presentation_progress(execution: dict) -> None:
    if not PRESENTATION_DELAYS_ENABLED:
        return
    execution_id = str(execution.get("execution_id") or "")
    if not execution_id or execution_id in PRESENTATION_PROGRESS:
        return
    plan_record = plan_by_identity(
        str(execution.get("plan_id") or ""),
        int(execution.get("plan_version") or 0),
    )
    if execution.get("execution_status") != "executing":
        planned_steps = execution.get("steps", [])
    else:
        planned_steps = (
            sorted(
                plan_record["plan"].get("proposed_plan", []),
                key=lambda item: int(item.get("order") or 0),
            )
            if plan_record
            else execution.get("steps", [])
        )
    durations = []
    for step in planned_steps:
        is_expertise = step.get("action") == "request_expertise"
        durations.append(random.randint(10, 15) if is_expertise else random.randint(5, 15))
    if not durations:
        return
    PRESENTATION_PROGRESS[execution_id] = {
        "started_at": time.monotonic(),
        "durations": durations,
        "terminal_status": execution.get("execution_status"),
    }


def apply_presentation_progress(dto: dict) -> dict:
    execution_id = str(dto.get("execution_id") or "")
    progress = PRESENTATION_PROGRESS.get(execution_id)
    if progress is None:
        return dto
    elapsed = time.monotonic() - float(progress["started_at"])
    durations = progress["durations"]
    total = sum(durations)
    if elapsed >= total:
        PRESENTATION_PROGRESS.pop(execution_id, None)
        return dto

    visible = {**dto, "execution_status": "executing", "status_label": "План выполняется"}
    visible["completed_at"] = None
    visible["remaining_blockers"] = []
    visible["missing_fields"] = []
    visible["stop_reason"] = None
    visible["requires_final_employee_approval"] = False
    visible["recommended_next_action"] = ""
    visible["recommendation"] = ""
    visible["recommendation_status"] = "generating"
    visible["resolution_recommendation"] = None

    cursor = 0.0
    simulated_steps = []
    for index, step in enumerate(dto.get("steps", [])):
        duration = durations[index] if index < len(durations) else 0
        end = cursor + duration
        simulated = {**step}
        if elapsed >= end:
            # Preserve the real status/result once this visual interval completes.
            pass
        elif elapsed >= cursor:
            simulated["status"] = "executing"
            simulated.pop("result", None)
            simulated.pop("error_message", None)
            simulated.pop("missing_fields", None)
            simulated["completed_at"] = None
        else:
            simulated["status"] = "pending"
            simulated["started_at"] = None
            simulated["completed_at"] = None
            simulated.pop("result", None)
            simulated.pop("error_message", None)
            simulated.pop("missing_fields", None)
        simulated_steps.append(simulated)
        cursor = end
    visible["steps"] = simulated_steps
    return visible


def review_plan_decision(plan_id: str, payload: dict, decision: str) -> dict:
    plan_version = int(payload.get("plan_version") or 0)
    record = plan_by_identity(plan_id, plan_version)
    if record is None:
        raise LookupError("План не найден")
    if decision not in {"approve_plan", "manual_review"}:
        raise ValueError("Неподдерживаемое решение")
    runtime = runtime_module()
    result = runtime.review_plan(
        runtime.RuntimeStore(ROOT),
        {
            "case_id": payload.get("case_id") or record["case_id"],
            "plan_id": plan_id,
            "plan_version": plan_version,
            "decision": decision,
            "employee_id": "EMP-DEMO-001",
            "comment": payload.get("comment"),
        },
    )
    expected_status = "approved" if decision == "approve_plan" else "manual_review"
    if result.get("status") != expected_status:
        message = (result.get("errors") or ["Решение не удалось сохранить"])[0]
        raise RuntimeError(str(message))
    return result


def approve_plan(plan_id: str, payload: dict) -> dict:
    return review_plan_decision(plan_id, payload, "approve_plan")


def take_plan_manual(plan_id: str, payload: dict) -> dict:
    return review_plan_decision(plan_id, payload, "manual_review")


def create_resolution_recommendation(execution: dict) -> dict:
    runtime = runtime_module()
    store = runtime.RuntimeStore(ROOT)
    existing = store.recommendation_for_execution(str(execution["execution_id"]))
    if existing is not None:
        return existing
    module_path = (
        CODE_ROOT
        / "skills"
        / "build-resolution-recommendation"
        / "recommendation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "casepilot_frontend_recommendation",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Recommendation generator is unavailable")
    recommender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recommender)
    plan_record = store.plan(
        str(execution["plan_id"]),
        int(execution["plan_version"]),
    )
    case = next(
        (
            item
            for item in read_json(DATA / "validation_cases.json")
            if item.get("case_id") == execution.get("case_id")
        ),
        None,
    )
    if plan_record is None or case is None:
        raise RuntimeError("Recommendation source is incomplete")
    source = {
        "case": case,
        "plan": plan_record["plan"],
        "execution": execution,
    }
    settings_path = Path.home() / "Ouroboros" / "data" / "settings.json"
    settings = read_json(settings_path) if settings_path.is_file() else {}
    api_key = str(settings.get("OPENROUTER_API_KEY") or "").strip()
    requests = 0
    fallback_reason = None
    if RECOMMENDATION_LLM_ENABLED and api_key:
        try:
            recommendation, requests = recommender.build_recommendation(
                source,
                api_key,
                ROOT,
            )
            status = "generated"
        except Exception as error:
            fallback_reason = str(error)
            recommendation = recommender.deterministic_fallback(source)
            status = "fallback"
    else:
        fallback_reason = (
            "LLM generation disabled"
            if not RECOMMENDATION_LLM_ENABLED
            else "OPENROUTER_API_KEY is unavailable"
        )
        recommendation = recommender.deterministic_fallback(source)
        status = "fallback"
    return store.save_recommendation(
        execution,
        recommendation,
        status=status,
        metadata={
            "model": recommender.MODEL if RECOMMENDATION_LLM_ENABLED and api_key else None,
            "reasoning_effort": (
                recommender.REASONING_EFFORT
                if RECOMMENDATION_LLM_ENABLED and api_key
                else None
            ),
            "model_requests": requests,
            "validation": "passed" if status == "generated" else "fallback",
            "fallback_reason": fallback_reason,
        },
    )


def _execute_background(plan_id: str, plan_version: int) -> None:
    try:
        runtime = runtime_module()
        execution = runtime.execute_plan(
            runtime.RuntimeStore(ROOT),
            plan_id,
            plan_version,
        )
        if execution.get("execution_status") in {
            "completed",
            "failed",
            "waiting_for_information",
            "replan_required",
            "manual_review",
        }:
            create_resolution_recommendation(execution)
    finally:
        with EXECUTION_LOCK:
            EXECUTION_THREADS.pop((plan_id, plan_version), None)


def start_execution(plan_id: str, plan_version: int) -> dict:
    key = (plan_id, plan_version)
    with EXECUTION_LOCK:
        existing = executions_for_plan(plan_id, plan_version)
        if existing:
            latest = max(existing, key=lambda item: str(item.get("started_at") or ""))
            return execution_dto(latest)
        active = EXECUTION_THREADS.get(key)
        if active is None:
            active = threading.Thread(
                target=_execute_background,
                args=(plan_id, plan_version),
                daemon=True,
                name=f"casepilot-{plan_id}-v{plan_version}",
            )
            EXECUTION_THREADS[key] = active
            active.start()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        existing = executions_for_plan(plan_id, plan_version)
        if existing:
            if active.is_alive():
                active.join(timeout=0.5)
                existing = executions_for_plan(plan_id, plan_version)
            latest = max(existing, key=lambda item: str(item.get("started_at") or ""))
            start_presentation_progress(latest)
            return execution_dto(latest)
        if not active.is_alive():
            break
        time.sleep(0.01)
    raise RuntimeError("Выполнение не удалось запустить")


def read_body(handler: SimpleHTTPRequestHandler) -> dict:
    length = min(int(handler.headers.get("Content-Length") or 0), 64_000)
    if length <= 0:
        return {}
    value = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Тело запроса должно быть объектом")
    return value


def take_case_handler():
    global TAKE_CASE_HANDLER
    if TAKE_CASE_HANDLER is not None:
        return TAKE_CASE_HANDLER

    settings_path = Path.home() / "Ouroboros" / "data" / "settings.json"
    settings = read_json(settings_path)

    class LocalPluginApi:
        def __init__(self):
            self.handler = None

        def get_settings(self, keys):
            return {key: settings.get(key) for key in keys}

        def register_tool(self, name, *, handler, **_kwargs):
            if name == "take_case":
                self.handler = handler

    plugin_path = ROOT / "skills" / "take_case" / "plugin.py"
    spec = importlib.util.spec_from_file_location("casepilot_frontend_take_case", plugin_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("take_case Skill is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = LocalPluginApi()
    module.register(api)
    if api.handler is None:
        raise RuntimeError("take_case handler was not registered")
    TAKE_CASE_HANDLER = api.handler
    return TAKE_CASE_HANDLER


def analysis_payload(record: dict, *, metadata: dict | None = None) -> dict:
    scenario, title = scenario_details(record["plan"])
    executions = executions_for_plan(
        str(record["plan_id"]),
        int(record["plan_version"]),
    )
    latest_execution = (
        max(executions, key=lambda item: str(item.get("started_at") or ""))
        if executions
        else None
    )
    return {
        "run_id": record.get("run_id"),
        "plan_id": record.get("plan_id"),
        "plan_version": record.get("plan_version"),
        "status": record.get("status"),
        "plan": record["plan"],
        "scenario": scenario,
        "scenario_title": title,
        "latest_execution": (
            execution_dto(latest_execution) if latest_execution else None
        ),
        "metadata": metadata or {},
    }


def get_or_create_case_analysis(case_id: str) -> dict:
    existing = latest_plan(case_id)
    if existing is not None:
        if existing.get("status") in {
            "completed",
            "failed",
            "manual_review",
            "executing",
            "approved",
        }:
            with TAKE_CASE_LOCK:
                current = latest_plan(case_id)
                if current is not None and current.get("status") in {
                    "completed",
                    "failed",
                    "manual_review",
                    "executing",
                    "approved",
                }:
                    runtime = runtime_module()
                    store = runtime.RuntimeStore(ROOT)
                    run = store.start_run(case_id)
                    existing = store.seed_plan(
                        f"PLAN-{run['run_id']}",
                        1,
                        deepcopy(current["plan"]),
                        run_id=run["run_id"],
                    )
                elif current is not None:
                    existing = current
        return analysis_payload(
            existing,
            metadata={
                "model_requests": 0,
                "reason": "latest_plan_reused",
            },
        )

    # Runtime JSON is an atomic but single-user demo store, so serialize new runs.
    with TAKE_CASE_LOCK:
        # A concurrent request may have created a plan while this request waited.
        existing = latest_plan(case_id)
        if existing is not None:
            return analysis_payload(
                existing,
                metadata={
                    "model_requests": 0,
                    "reason": "latest_plan_reused",
                },
            )
        raw = take_case_handler()(case_id=case_id)
    result = json.loads(raw)
    if result.get("status") != "ready_for_review":
        message = (result.get("errors") or ["CasePilot could not build a plan"])[0]
        raise RuntimeError(str(message))
    runtime = result["runtime"]
    record = plan_by_identity(
        str(runtime["plan_id"]),
        int(runtime["plan_version"]),
    )
    if record is None:
        raise RuntimeError("New plan was not found in runtime")
    return analysis_payload(record, metadata=result.get("metadata", {}))


def scenario_details(plan: dict) -> tuple[dict | None, str | None]:
    scenarios = read_json(DATA / "scenario_catalog.json")
    candidates_path = DATA / "scenario_candidates.json"
    if candidates_path.is_file():
        scenarios.extend(
            {
                **item,
                "scenario_id": item.get("proposed_scenario_id"),
            }
            for item in read_json(candidates_path)
            if item.get("status") == "approved_for_mvp"
        )
    used = (plan.get("scenarios_used") or [])
    if used:
        scenario_id = used[0].get("scenario_id")
        found = next((item for item in scenarios if item["scenario_id"] == scenario_id), None)
        return used[0], found.get("title") if found else scenario_id

    problem_type = str(plan.get("identified_problem", {}).get("type", ""))
    mapping = {
        "authorization": "SCN-DC-CLOSE-ACTIVE-HOLD",
        "hold": "SCN-DC-CLOSE-ACTIVE-HOLD",
        "balance": "SCN-DC-CLOSE-NEGATIVE-BALANCE",
        "overdraft": "SCN-DC-CLOSE-NEGATIVE-BALANCE",
        "restriction": "SCN-DC-CLOSE-ACCOUNT-RESTRICTION",
    }
    scenario_id = next(
        (value for key, value in mapping.items() if key in problem_type.lower()),
        "SCN-DC-CLOSE-ACCOUNT-RESTRICTION",
    )
    found = next((item for item in scenarios if item["scenario_id"] == scenario_id), None)
    similar = (plan.get("similar_cases_used") or [{}])[0]
    score = similar.get("similarity_score", 0.8)
    return {
        "scenario_id": scenario_id,
        "similarity_score": score,
        "useful_pattern": similar.get("useful_pattern", ""),
    }, found.get("title") if found else scenario_id


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format_string: str, *args) -> None:
        print(f"[CasePilot] {format_string % args}")

    def send_json(self, value, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/cases":
            self.send_json(read_json(DATA / "validation_cases.json"))
            return
        if path.startswith("/api/executions/"):
            execution_id = unquote(path.removeprefix("/api/executions/"))
            execution = execution_by_id(execution_id)
            self.send_json(
                execution_dto(execution) if execution else {"error": "execution_not_found"},
                200 if execution else 404,
            )
            return
        if path.startswith("/api/runs/"):
            run_id = unquote(path.removeprefix("/api/runs/"))
            run = next(
                (
                    item
                    for item in read_json(DATA / "runtime" / "runs.json")
                    if item.get("run_id") == run_id
                ),
                None,
            )
            if run is None:
                self.send_json({"error": "run_not_found"}, 404)
                return
            plans = [
                item
                for item in read_json(DATA / "runtime" / "plans.json")
                if item.get("run_id") == run_id
            ]
            executions = [
                execution_dto(item)
                for item in read_json(DATA / "runtime" / "executions.json")
                if item.get("run_id") == run_id
            ]
            self.send_json({"run": run, "plans": plans, "executions": executions})
            return
        if path.startswith("/api/cases/"):
            case_id = unquote(path.removeprefix("/api/cases/"))
            item = next(
                (case for case in read_json(DATA / "validation_cases.json") if case["case_id"] == case_id),
                None,
            )
            self.send_json(item or {"error": "case_not_found"}, 200 if item else 404)
            return
        self.serve_frontend(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/plans/") and path.endswith("/approve"):
            plan_id = unquote(
                path[len("/api/plans/"):-len("/approve")].rstrip("/")
            )
            try:
                result = approve_plan(plan_id, read_body(self))
                self.send_json(result)
            except LookupError as error:
                self.send_json({"error": "not_found", "message": str(error)}, 404)
            except Exception:
                self.send_json(
                    {
                        "error": "approval_failed",
                        "message": "План не удалось подтвердить. Обновите данные и попробуйте снова.",
                    },
                    409,
                )
            return
        if path.startswith("/api/plans/") and path.endswith("/manual-review"):
            plan_id = unquote(
                path[len("/api/plans/"):-len("/manual-review")].rstrip("/")
            )
            try:
                result = take_plan_manual(plan_id, read_body(self))
                self.send_json(result)
            except LookupError as error:
                self.send_json({"error": "not_found", "message": str(error)}, 404)
            except Exception:
                self.send_json(
                    {
                        "error": "manual_review_failed",
                        "message": "Решение не удалось сохранить. Обновите данные и попробуйте снова.",
                    },
                    409,
                )
            return
        if path.startswith("/api/plans/") and path.endswith("/execute"):
            plan_id = unquote(
                path[len("/api/plans/"):-len("/execute")].rstrip("/")
            )
            try:
                payload = read_body(self)
                result = start_execution(
                    plan_id,
                    int(payload.get("plan_version") or 0),
                )
                self.send_json(result, 202 if result["execution_status"] == "executing" else 200)
            except Exception:
                self.send_json(
                    {
                        "error": "execution_failed",
                        "message": "Выполнение не удалось запустить.",
                    },
                    409,
                )
            return
        suffix = "/analysis"
        if path.startswith("/api/cases/") and path.endswith(suffix):
            case_id = unquote(path[len("/api/cases/"):-len(suffix)].rstrip("/"))
            try:
                self.send_json(get_or_create_case_analysis(case_id))
            except Exception as error:
                self.send_json(
                    {
                        "error": "analysis_failed",
                        "message": str(error),
                    },
                    500,
                )
            return
        self.send_json({"error": "not_found"}, 404)

    def serve_frontend(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        target = (FRONTEND / relative).resolve()
        try:
            target.relative_to(FRONTEND.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.is_file():
            target = FRONTEND / "index.html"
        payload = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    ensure_skill_runtime()
    runtime_module().RuntimeStore(ROOT)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"CasePilot frontend: http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
