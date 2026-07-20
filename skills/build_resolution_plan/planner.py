"""Generate and validate a read-only CasePilot resolution plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "z-ai/glm-5.2"
REASONING_EFFORT = "medium"
MAX_MODEL_REQUESTS = 2
MAX_OUTPUT_TOKENS = 5_000

SYSTEM_PROMPT = """You are CasePilot's read-only resolution planner for synthetic debit-card cases.
Return exactly one JSON object and no Markdown or prose outside it.

Use only the supplied case, scenarios (or legacy similar_cases), and expertise_catalog. The validation case has no known solution.
Infer the probable blocking cause and cite concrete evidence present in the input.
For scenario input, treat each approved scenario's strategy_steps and stop_conditions as the primary reusable strategy. Use its source_cases only as historical evidence. Adapt the scenario instead of copying mechanically.
For legacy similar_cases input, use historical resolution_plan, expertise_results, and final_result only as successful strategy examples.
Use only expertise_type values present in expertise_catalog. Use no more than two expertises normally and never more than four. Never invent an expertise, input field, status, system result, or completed action.
Create 2-20 atomic future steps. Derive the necessary sequence and level of detail from the relevant historical resolution plans, then adapt it to the current case; do not pad the plan with redundant steps. Do not execute any step. Every step status must be "pending". Every step must specify inputs, expected result, success condition, and failure behavior.
Every action must be exactly one of: check_account_state, check_pending_operations, request_expertise, check_account_closure_eligibility, wait_for_settlement, record_post_closure_instruction, collect_compliance_evidence, match_collection_surplus, prepare_resolution_decision.
Use action_type=expertise only with action=request_expertise. Use action_type=case_action for wait_for_settlement, record_post_closure_instruction, collect_compliance_evidence, match_collection_surplus, and prepare_resolution_decision. Other actions use action_type=check.
Use these exact required_inputs:
- check_account_state: case_id, account_id
- check_pending_operations: case_id, card_id, account_id
- request_expertise: exactly the selected catalog expertise's required_inputs
- check_account_closure_eligibility: case_id, account_id, previous_results
- every case_action: case_id, previous_results
Do not add a client communication step: a deterministic draft is produced after execution.
If any catalog-required expertise input is absent from the case, keep the expertise step but use failure_action=request_information and list the missing field in open_questions. Never invent the value.
For an ambiguous legal restriction, use account_restriction_check and manual_review on failure.
For an approved technical balance correction, use account_balance_analysis before the final closure eligibility check.
Allowed failure_action: continue, request_information, replan, manual_review.
Always set requires_employee_approval=true.
Allowed recommended_next_action: approve_plan, provide_information, manual_review.

Scenario/retrieval score policy:
- best score >= 0.65: a full plan is allowed; confidence may be high only when the cause also matches and inputs are sufficient.
- 0.45 <= best score < 0.65: confidence cannot exceed medium; list missing data in open_questions.
- best score < 0.45: confidence is low and next action is provide_information or manual_review.
Similarity score is evidence, not the confidence score itself.
If more than four expertises appear necessary, use low confidence and manual_review.

When revision_context is supplied, preserve sound parts of the previous plan, apply the employee comment, and return a complete revised plan. Never claim that the employee comment itself is system evidence.

The output must conform to the supplied JSON Schema."""


def _schema_path() -> Path:
    skill_root = Path(__file__).resolve().parent
    bundled = skill_root / "resolution_plan.schema.json"
    if bundled.is_file():
        return bundled
    configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / "schemas" / "resolution_plan.schema.json"
    locator = skill_root / "casepilot_project_dir.txt"
    if locator.is_file():
        project_dir = locator.read_text(encoding="utf-8").strip()
        if project_dir:
            return Path(project_dir).expanduser() / "schemas" / "resolution_plan.schema.json"
    for base in (skill_root, *skill_root.parents, Path.cwd(), *Path.cwd().parents):
        candidate = base / "schemas" / "resolution_plan.schema.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("resolution_plan.schema.json was not found")


def _load_schema() -> dict[str, Any]:
    return json.loads(_schema_path().read_text(encoding="utf-8"))


def validate_input(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    required = {"case", "expertise_catalog"}
    allowed = required | {"scenarios", "similar_cases", "revision_context"}
    missing = sorted(required - set(payload))
    extra = sorted(set(payload) - allowed)
    if missing:
        errors.append(f"missing input fields: {missing}")
    if extra:
        errors.append(f"unexpected input fields: {extra}")
    retrieval_fields = {"scenarios", "similar_cases"} & set(payload)
    if len(retrieval_fields) != 1:
        errors.append("provide exactly one of scenarios or similar_cases")
    case = payload.get("case")
    if not isinstance(case, dict) or not str(case.get("case_id") or "").strip():
        errors.append("case must be an object with case_id")
    elif {"resolution_plan", "expertise_results", "final_result"} & set(case):
        errors.append("validation case contains hidden solution fields")
    if "scenarios" in payload:
        scenarios = payload.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios or len(scenarios) > 3:
            errors.append("scenarios must be a non-empty array with at most 3 items")
        elif any(
            not isinstance(item, dict) or not item.get("scenario_id")
            for item in scenarios
        ):
            errors.append("each scenario must be an object with scenario_id")
    if "similar_cases" in payload:
        similar = payload.get("similar_cases")
        if not isinstance(similar, list) or len(similar) > 5:
            errors.append("similar_cases must be an array with at most 5 items")
        elif any(not isinstance(item, dict) or not item.get("case_id") for item in similar):
            errors.append("each similar case must be an object with case_id")
    catalog = payload.get("expertise_catalog")
    if not isinstance(catalog, list) or not catalog:
        errors.append("expertise_catalog must be a non-empty array")
    elif any(not isinstance(item, dict) or not item.get("expertise_type") for item in catalog):
        errors.append("each expertise must be an object with expertise_type")
    revision = payload.get("revision_context")
    if revision is not None:
        if not isinstance(revision, dict):
            errors.append("revision_context must be an object")
        elif set(revision) != {"previous_plan", "employee_comment"}:
            errors.append("revision_context requires exactly previous_plan and employee_comment")
        else:
            if not isinstance(revision.get("previous_plan"), dict):
                errors.append("revision_context.previous_plan must be an object")
            if not str(revision.get("employee_comment") or "").strip():
                errors.append("revision_context.employee_comment must be non-empty")
    return errors


def validate_plan(plan: Any, source: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(plan),
            key=lambda item: list(item.absolute_path),
        )
    ]
    if not isinstance(plan, dict):
        return errors or ["plan must be an object"]

    case_id = str(source["case"].get("case_id") or "")
    if plan.get("case_id") != case_id:
        errors.append("case_id must equal the input validation case ID")

    source_similar = {
        str(item.get("case_id")): float(item.get("score") or 0)
        for item in source.get("similar_cases", [])
        if isinstance(item, dict) and item.get("case_id")
    }
    for item in plan.get("similar_cases_used", []):
        if not isinstance(item, dict):
            continue
        historical_id = str(item.get("case_id") or "")
        if historical_id not in source_similar:
            errors.append(f"similar_cases_used references unknown case_id {historical_id!r}")
        elif abs(float(item.get("similarity_score") or 0) - source_similar[historical_id]) > 0.0001:
            errors.append(f"similarity_score for {historical_id!r} differs from input")

    source_scenarios = {
        str(item.get("scenario_id")): item
        for item in source.get("scenarios", [])
        if isinstance(item, dict) and item.get("scenario_id")
    }
    for item in plan.get("scenarios_used", []):
        if not isinstance(item, dict):
            continue
        scenario_id = str(item.get("scenario_id") or "")
        source_item = source_scenarios.get(scenario_id)
        if source_item is None:
            errors.append(f"scenarios_used references unknown scenario_id {scenario_id!r}")
            continue
        if abs(
            float(item.get("similarity_score") or 0)
            - float(source_item.get("score") or 0)
        ) > 0.0001:
            errors.append(f"similarity_score for {scenario_id!r} differs from input")
        allowed_sources = {
            str(case.get("case_id"))
            for case in source_item.get("source_cases", [])
            if isinstance(case, dict) and case.get("case_id")
        }
        if set(item.get("source_case_ids") or []) - allowed_sources:
            errors.append(
                f"source_case_ids for {scenario_id!r} are not supplied evidence"
            )

    catalog = {
        str(item["expertise_type"]): item
        for item in source["expertise_catalog"]
        if isinstance(item, dict) and item.get("expertise_type")
    }
    case = source["case"]
    system_data = (
        case.get("synthetic_system_data")
        if isinstance(case.get("synthetic_system_data"), dict)
        else {}
    )
    products = case.get("products") if isinstance(case.get("products"), list) else []
    available_source_inputs = set(case) | set(system_data)
    if any(
        isinstance(item, dict) and item.get("product_type") == "current_account"
        for item in products
    ):
        available_source_inputs.add("account_id")
    if any(
        isinstance(item, dict) and item.get("product_type") == "debit_card"
        for item in products
    ):
        available_source_inputs.add("card_id")
    transactions = (
        system_data.get("transactions")
        if isinstance(system_data.get("transactions"), list)
        else []
    )
    transaction_fields = {
        str(key)
        for item in transactions
        if isinstance(item, dict)
        for key, value in item.items()
        if value is not None and value != ""
    }
    available_source_inputs.update(transaction_fields)
    if "transaction_id" in transaction_fields:
        available_source_inputs.add("original_transaction_id")
    if transactions:
        available_source_inputs.update(
            {
                "reason",
                "dispute_reason",
                "claim_type",
                "review_type",
                "amount",
                "claimed_amount",
            }
        )
    if any(
        isinstance(item, dict) and item.get("type") == "refund"
        for item in transactions
    ):
        available_source_inputs.add("expected_refund_amount")
    available_source_inputs.add("customer_id")
    steps = plan.get("proposed_plan", [])
    step_ids = [item.get("step_id") for item in steps if isinstance(item, dict)]
    orders = [item.get("order") for item in steps if isinstance(item, dict)]
    if len(step_ids) != len(set(step_ids)):
        errors.append("proposed_plan step_id values must be unique")
    if orders != list(range(1, len(steps) + 1)):
        errors.append("proposed_plan order must be sequential and match array order")
    if step_ids != [f"step_{index}" for index in range(1, len(steps) + 1)]:
        errors.append("step_id values must be sequential and match order")

    expertise_steps: dict[str, str] = {}
    allowed_actions = {
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
    case_actions = {
        "wait_for_settlement",
        "record_post_closure_instruction",
        "collect_compliance_evidence",
        "match_collection_surplus",
        "prepare_resolution_decision",
    }
    action_inputs = {
        "check_account_state": {"case_id", "account_id"},
        "check_pending_operations": {"case_id", "card_id", "account_id"},
        "check_account_closure_eligibility": {
            "case_id",
            "account_id",
            "previous_results",
        },
        **{action: {"case_id", "previous_results"} for action in case_actions},
    }
    for step in steps:
        if not isinstance(step, dict):
            continue
        expertise_type = step.get("expertise_type")
        action_type = step.get("action_type")
        action = step.get("action")
        if action not in allowed_actions:
            errors.append(f"action {action!r} is not executable")
        if action == "request_expertise" and action_type != "expertise":
            errors.append("request_expertise must use action_type=expertise")
        if action in case_actions and action_type != "case_action":
            errors.append(f"{action!r} must use action_type=case_action")
        if action not in case_actions and action != "request_expertise" and action_type != "check":
            errors.append(f"{action!r} must use action_type=check")
        if action in action_inputs and set(step.get("required_inputs") or []) != action_inputs[action]:
            errors.append(
                f"{action!r} required_inputs must be exactly {sorted(action_inputs[action])}"
            )
        if action_type == "expertise":
            if expertise_type not in catalog:
                errors.append(f"expertise step references unknown expertise_type {expertise_type!r}")
            else:
                expertise_steps[str(step.get("step_id"))] = str(expertise_type)
                allowed_inputs = set(catalog[str(expertise_type)].get("required_inputs") or [])
                actual_inputs = set(step.get("required_inputs") or [])
                if actual_inputs != allowed_inputs:
                    errors.append(
                        f"expertise step {step.get('step_id')} required_inputs must be exactly "
                        f"{sorted(allowed_inputs)}"
                    )
                unavailable = sorted(allowed_inputs - available_source_inputs)
                if unavailable and step.get("failure_action") != "request_information":
                    errors.append(
                        f"expertise step {step.get('step_id')} has unavailable inputs "
                        f"{unavailable} and must use failure_action=request_information"
                    )
        elif expertise_type is not None:
            errors.append(f"non-expertise step {step.get('step_id')} must use expertise_type=null")

    required = plan.get("required_expertises", [])
    required_types: list[str] = []
    for item in required:
        if not isinstance(item, dict):
            continue
        expertise_type = str(item.get("expertise_type") or "")
        planned_step_id = str(item.get("planned_step_id") or "")
        required_types.append(expertise_type)
        if expertise_type not in catalog:
            errors.append(f"required_expertises references unknown expertise_type {expertise_type!r}")
        if expertise_steps.get(planned_step_id) != expertise_type:
            errors.append(
                f"required expertise {expertise_type!r} does not match expertise step {planned_step_id!r}"
            )
    if len(required_types) != len(set(required_types)):
        errors.append("required_expertises must not contain duplicates")
    if sorted(required_types) != sorted(expertise_steps.values()):
        errors.append("required_expertises must exactly match expertise steps")

    retrieval_scores = list(source_similar.values()) + [
        float(item.get("score") or 0)
        for item in source_scenarios.values()
    ]
    best_score = max(retrieval_scores, default=0.0)
    confidence = plan.get("confidence") if isinstance(plan.get("confidence"), dict) else {}
    level = confidence.get("level")
    next_action = plan.get("recommended_next_action")
    if best_score < 0.45:
        if level != "low":
            errors.append("best similarity below 0.45 requires low confidence")
        if next_action not in {"provide_information", "manual_review"}:
            errors.append("best similarity below 0.45 requires information or manual review")
    elif best_score < 0.65 and level == "high":
        errors.append("best similarity below 0.65 forbids high confidence")
    return list(dict.fromkeys(errors))


def normalize_contract_defaults(candidate: Any) -> Any:
    """Fill deterministic workflow constants that some providers omit."""
    if not isinstance(candidate, dict):
        return candidate
    steps = candidate.get("proposed_plan")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                step.setdefault("status", "pending")
    return candidate


def _extract_json(content: Any) -> Any:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _call_model(api_key: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> Any:
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
                    "name": "casepilot_resolution_plan",
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
            "X-Title": "CasePilot Build Resolution Plan",
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


def build_plan(source: dict[str, Any], api_key: str) -> tuple[dict[str, Any], int]:
    schema = _load_schema()
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
    candidate: Any = None
    validation_errors: list[str] = []
    for attempt in range(1, MAX_MODEL_REQUESTS + 1):
        if attempt == 2:
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
                    },
                    {
                        "role": "user",
                        "content": (
                            "The previous JSON failed validation. Correct only these errors and "
                            "return the complete JSON object again:\n- "
                            + "\n- ".join(validation_errors)
                        ),
                    },
                ]
            )
        try:
            candidate = normalize_contract_defaults(
                _call_model(api_key, messages, schema)
            )
        except ValueError as error:
            validation_errors = [str(error)]
            candidate = {}
            continue
        validation_errors = validate_plan(candidate, source, schema)
        if not validation_errors:
            return candidate, attempt
    raise ValueError(
        "model output remained invalid after two requests: " + "; ".join(validation_errors)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", required=True, help="CasePilot planning input object")
    args = parser.parse_args()
    try:
        source = json.loads(args.input_json)
    except json.JSONDecodeError as error:
        print(json.dumps({"status": "invalid_input", "errors": [str(error)]}, ensure_ascii=False))
        raise SystemExit(2)
    input_errors = validate_input(source)
    if input_errors:
        print(json.dumps({"status": "invalid_input", "errors": input_errors}, ensure_ascii=False))
        raise SystemExit(2)

    api_key = str(os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        print(
            json.dumps(
                {"status": "configuration_error", "errors": ["OPENROUTER_API_KEY is unavailable"]},
                ensure_ascii=False,
            )
        )
        raise SystemExit(3)
    try:
        plan, attempts = build_plan(source, api_key)
    except (RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "generation_error", "errors": [str(error)]},
                ensure_ascii=False,
            )
        )
        raise SystemExit(4)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print(
        f"CASEPILOT_META model={MODEL} reasoning_effort={REASONING_EFFORT} requests={attempts}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
