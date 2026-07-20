"""Generate an evidence-bound CasePilot recommendation for one terminal execution."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "z-ai/glm-5.2"
REASONING_EFFORT = "medium"
MAX_MODEL_REQUESTS = 2
MAX_OUTPUT_TOKENS = 3_000
TERMINAL_STATUSES = {
    "completed",
    "failed",
    "waiting_for_information",
    "replan_required",
    "manual_review",
}
RESTRICTED_DECISIONS = {
    "waiting_for_information": "REQUEST_INFORMATION",
    "replan_required": "REPLAN_CASE",
    "manual_review": "MANUAL_REVIEW",
    "failed": "TECHNICAL_REVIEW",
}

SYSTEM_PROMPT = """You are CasePilot's read-only resolution recommendation writer.
Return exactly one JSON object in Russian and no Markdown or prose outside it.

Write for a busy bank operator. Be concise and do not retell the case or every
plan step. Title: one short line. Summary: at most two short sentences.
key_findings: 2-4 compact facts. remaining_risks: 0-3 items. employee_actions:
1-3 imperative actions. Avoid internal IDs unless they are needed for the
employee's next action. Keep the client response to 2-4 short sentences.

Use only the supplied case, approved plan, and terminal execution. Treat completed
step result_code values and their result payloads as the only verified findings.
Never claim that an operation, client communication, account change, refund,
dispute, closure, or restriction removal was performed. Recommend a future
employee-controlled decision only.

Every key_findings item must copy source_step_id and result_code from one supplied
completed step. Do not invent evidence or result codes. Remaining risks must be
grounded in remaining_blockers, missing_fields, stop_reason, failed steps, or an
explicit limitation in a completed result. Employee actions must be concrete,
safe, and require employee control.

For completed execution, choose a concise business decision code matching the
evidence, such as APPROVE_ACCOUNT_CLOSURE, WAIT_FOR_REVERSAL,
START_DISPUTE_REVIEW, or REVIEW_PREPARED_RESOLUTION.
For other statuses use exactly:
- waiting_for_information: REQUEST_INFORMATION
- replan_required: REPLAN_CASE
- manual_review: MANUAL_REVIEW
- failed: TECHNICAL_REVIEW

Confidence cannot be high when there are remaining blockers or missing fields.
For any non-completed execution confidence must be low. Always set
requires_employee_approval=true. The client response is only a draft and may be
null when a safe response cannot be prepared.

The output must conform to the supplied JSON Schema."""


def schema_path(project_dir: Path) -> Path:
    return project_dir / "schemas" / "resolution_recommendation.schema.json"


def load_schema(project_dir: Path) -> dict[str, Any]:
    return json.loads(schema_path(project_dir).read_text(encoding="utf-8"))


def validate_source(source: Any) -> list[str]:
    if not isinstance(source, dict):
        return ["input must be an object"]
    if set(source) != {"case", "plan", "execution"}:
        return ["input requires exactly case, plan, and execution"]
    case = source.get("case")
    plan = source.get("plan")
    execution = source.get("execution")
    if not isinstance(case, dict) or not case.get("case_id"):
        return ["case must contain case_id"]
    if not isinstance(plan, dict) or not plan.get("case_id"):
        return ["plan must contain case_id"]
    if not isinstance(execution, dict) or not execution.get("execution_id"):
        return ["execution must contain execution_id"]
    case_ids = {
        str(case.get("case_id")),
        str(plan.get("case_id")),
        str(execution.get("case_id")),
    }
    if len(case_ids) != 1:
        return ["case_id differs between case, plan, and execution"]
    if execution.get("execution_status") not in TERMINAL_STATUSES:
        return ["recommendation requires a terminal execution"]
    return []


def _evidence_pairs(execution: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(step.get("step_id")), str(step.get("result", {}).get("result_code")))
        for step in execution.get("steps", [])
        if step.get("status") == "completed"
        and isinstance(step.get("result"), dict)
        and step["result"].get("result_code")
    }


def validate_recommendation(
    recommendation: Any,
    source: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    errors = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(recommendation),
            key=lambda item: list(item.absolute_path),
        )
    ]
    if not isinstance(recommendation, dict):
        return errors or ["recommendation must be an object"]
    execution = source["execution"]
    status = str(execution["execution_status"])
    restricted = RESTRICTED_DECISIONS.get(status)
    if restricted and recommendation.get("decision_code") != restricted:
        errors.append(f"{status} requires decision_code={restricted}")
    if status != "completed":
        confidence = recommendation.get("confidence")
        if not isinstance(confidence, dict) or confidence.get("level") != "low":
            errors.append("non-completed execution requires low confidence")
    if (
        execution.get("remaining_blockers") or execution.get("missing_fields")
    ) and recommendation.get("confidence", {}).get("level") == "high":
        errors.append("remaining blockers or missing fields forbid high confidence")
    confidence = (
        recommendation.get("confidence")
        if isinstance(recommendation.get("confidence"), dict)
        else {}
    )
    level = confidence.get("level")
    score = confidence.get("score")
    if isinstance(score, (int, float)):
        allowed_ranges = {
            "low": (0, 0.49),
            "medium": (0.5, 0.79),
            "high": (0.8, 1),
        }
        bounds = allowed_ranges.get(str(level))
        if bounds and not bounds[0] <= float(score) <= bounds[1]:
            errors.append(
                f"confidence level {level} is inconsistent with score {score}"
            )
    evidence = _evidence_pairs(execution)
    for finding in recommendation.get("key_findings", []):
        pair = (
            str(finding.get("source_step_id")),
            str(finding.get("result_code")),
        )
        if pair not in evidence:
            errors.append(
                f"key finding references unknown evidence {pair[0]!r}/{pair[1]!r}"
            )
    return list(dict.fromkeys(errors))


def _shorten(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    candidate = text[: limit + 1]
    sentence = max(candidate.rfind(". "), candidate.rfind("! "), candidate.rfind("? "))
    if sentence >= int(limit * 0.55):
        return candidate[: sentence + 1]
    boundary = candidate.rfind(" ")
    return candidate[: boundary if boundary > 0 else limit].rstrip(" ,;:") + "…"


def compact_recommendation(candidate: Any) -> Any:
    """Apply operator-facing hard caps independently of model compliance."""
    if not isinstance(candidate, dict):
        return candidate
    compact = dict(candidate)
    compact["title"] = _shorten(compact.get("title"), 100)
    compact["summary"] = _shorten(compact.get("summary"), 280)
    findings = []
    for item in compact.get("key_findings", [])[:4]:
        if isinstance(item, dict):
            findings.append(
                {
                    **item,
                    "finding": _shorten(item.get("finding"), 180),
                }
            )
    compact["key_findings"] = findings
    compact["remaining_risks"] = [
        _shorten(item, 180) for item in compact.get("remaining_risks", [])[:3]
    ]
    compact["employee_actions"] = [
        _shorten(item, 160) for item in compact.get("employee_actions", [])[:3]
    ]
    if compact.get("client_response_draft") is not None:
        compact["client_response_draft"] = _shorten(
            compact.get("client_response_draft"),
            500,
        )
    confidence = compact.get("confidence")
    if isinstance(confidence, dict):
        compact["confidence"] = {
            **confidence,
            "reason": _shorten(confidence.get("reason"), 180),
        }
    return compact


def _extract_json(content: Any) -> Any:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _call_model(
    api_key: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
) -> Any:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": REASONING_EFFORT},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "casepilot_resolution_recommendation",
                    "strict": True,
                    "schema": schema,
                },
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/razzant/ouroboros",
            "X-Title": "CasePilot Resolution Recommendation",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OpenRouter returned HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("OpenRouter request failed or timed out") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("OpenRouter returned an unreadable response") from None
    try:
        return _extract_json(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"model response is not valid JSON: {error}") from None


def build_recommendation(
    source: dict[str, Any],
    api_key: str,
    project_dir: Path,
) -> tuple[dict[str, Any], int]:
    schema = load_schema(project_dir)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "JSON Schema:\n"
                + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                + "\n\nInput:\n"
                + json.dumps(source, ensure_ascii=False, separators=(",", ":"))
            ),
        },
    ]
    candidate: Any = {}
    validation_errors: list[str] = []
    for attempt in range(1, MAX_MODEL_REQUESTS + 1):
        if attempt == 2:
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            candidate, ensure_ascii=False, separators=(",", ":")
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Исправь только перечисленные ошибки и верни полный JSON:\n- "
                            + "\n- ".join(validation_errors)
                        ),
                    },
                ]
            )
        try:
            candidate = compact_recommendation(
                _call_model(api_key, messages, schema)
            )
        except ValueError as error:
            candidate = {}
            validation_errors = [str(error)]
            continue
        validation_errors = validate_recommendation(candidate, source, schema)
        if not validation_errors:
            return candidate, attempt
    raise ValueError(
        "model output remained invalid after two requests: "
        + "; ".join(validation_errors)
    )


def deterministic_fallback(source: dict[str, Any]) -> dict[str, Any]:
    execution = source["execution"]
    status = str(execution["execution_status"])
    recommendation_code = str(execution.get("recommended_next_action") or "")
    decision_by_next_action = {
        "approve_case_closure": "APPROVE_ACCOUNT_CLOSURE",
        "wait_for_reversal": "WAIT_FOR_REVERSAL",
        "employee_review_resolution": "REVIEW_PREPARED_RESOLUTION",
        "request_missing_information": "REQUEST_INFORMATION",
        "build_revised_plan": "REPLAN_CASE",
        "perform_manual_review": "MANUAL_REVIEW",
        "inspect_execution_failure": "TECHNICAL_REVIEW",
    }
    decision_code = RESTRICTED_DECISIONS.get(
        status,
        decision_by_next_action.get(
            recommendation_code,
            "REVIEW_PREPARED_RESOLUTION",
        ),
    )
    titles = {
        "APPROVE_ACCOUNT_CLOSURE": "Подтвердить возможность закрытия счёта",
        "WAIT_FOR_REVERSAL": "Дождаться завершения операции",
        "REVIEW_PREPARED_RESOLUTION": "Проверить подготовленное решение",
        "REQUEST_INFORMATION": "Запросить недостающие данные",
        "REPLAN_CASE": "Обновить план решения",
        "MANUAL_REVIEW": "Продолжить ручную проверку",
        "TECHNICAL_REVIEW": "Проверить техническую ошибку",
    }
    action_by_code = {
        "APPROVE_ACCOUNT_CLOSURE": "Проверить результаты и подтвердить закрытие счёта.",
        "WAIT_FOR_REVERSAL": "Дождаться завершения операции и повторить проверку.",
        "REVIEW_PREPARED_RESOLUTION": "Проверить результаты и принять решение по кейсу.",
        "REQUEST_INFORMATION": "Добавить недостающие сведения перед продолжением.",
        "REPLAN_CASE": "Сформировать обновлённый план с учётом результатов.",
        "MANUAL_REVIEW": "Продолжить разбор кейса вручную.",
        "TECHNICAL_REVIEW": "Проверить причину остановки перед повторным запуском.",
    }
    findings = []
    for step in execution.get("steps", []):
        result = step.get("result")
        if step.get("status") != "completed" or not isinstance(result, dict):
            continue
        result_code = str(result.get("result_code") or "")
        if not result_code:
            continue
        findings.append(
            {
                "finding": str(
                    result.get("explanation")
                    or result.get("summary")
                    or f"Проверка завершена с результатом {result_code}."
                ),
                "source_step_id": str(step["step_id"]),
                "result_code": result_code,
            }
        )
    risks = [
        str(item).replace("_", " ")
        for item in execution.get("remaining_blockers", [])
    ]
    risks.extend(
        f"Не хватает данных: {str(item).replace('_', ' ')}"
        for item in execution.get("missing_fields", [])
    )
    if execution.get("stop_reason"):
        risks.append(str(execution["stop_reason"]))
    if not risks and status != "completed":
        risks.append("Автоматическое выполнение не завершено.")
    level = (
        "high"
        if status == "completed" and not risks and len(findings) >= 2
        else "medium"
        if status == "completed"
        else "low"
    )
    score = {"high": 0.85, "medium": 0.65, "low": 0.3}[level]
    summary = {
        "completed": "Проверки завершены; сотруднику необходимо проверить вывод и принять финальное решение.",
        "waiting_for_information": "Продолжение невозможно без недостающих данных.",
        "replan_required": "Полученные результаты требуют обновления плана.",
        "manual_review": "Автоматическое продолжение остановлено и передано сотруднику.",
        "failed": "Техническая ошибка не позволяет сформировать автоматическое бизнес-решение.",
    }[status]
    return compact_recommendation({
        "decision_code": decision_code,
        "title": titles[decision_code],
        "summary": summary,
        "key_findings": findings[:10],
        "remaining_risks": list(dict.fromkeys(risks))[:8],
        "employee_actions": [action_by_code[decision_code]],
        "client_response_draft": execution.get("client_response_draft"),
        "confidence": {
            "level": level,
            "score": score,
            "reason": (
                "Оценка основана только на сохранённых результатах выполненных шагов."
            ),
        },
        "requires_employee_approval": True,
    })
