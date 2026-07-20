"""Record an expert-validated CasePilot outcome for scenario learning."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
locator = (SKILL_DIR / "casepilot_project_dir.txt").read_text().strip()
PROJECT = (
    Path(configured).expanduser()
    if configured
    else (SKILL_DIR / locator if not Path(locator).is_absolute() else Path(locator))
).resolve()
spec = importlib.util.spec_from_file_location(
    "casepilot_scenario_evolution_record",
    PROJECT / "casepilot" / "scenario_evolution.py",
)
if spec is None or spec.loader is None:
    raise ImportError("CasePilot scenario evolution module unavailable")
EVOLUTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVOLUTION)


def register(api: Any) -> None:
    def run(
        _ctx: Any = None,
        case_id: str = "",
        problem_signature: str = "",
        actions_taken: Any = None,
        expertise_types: Any = None,
        required_inputs: Any = None,
        resolution_summary: str = "",
        expert_id: str = "",
        operator_decision: str = "manual_resolution",
    ) -> str:
        try:
            result = EVOLUTION.record_learning_event(
                PROJECT,
                case_id=case_id.strip(),
                problem_signature=problem_signature.strip(),
                actions_taken=actions_taken if isinstance(actions_taken, list) else [],
                expertise_types=expertise_types if isinstance(expertise_types, list) else [],
                required_inputs=required_inputs if isinstance(required_inputs, list) else [],
                resolution_summary=resolution_summary,
                expert_id=expert_id.strip(),
                operator_decision=operator_decision,
            )
        except Exception as error:
            result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)

    api.register_tool(
        "record_scenario_outcome",
        handler=run,
        description=(
            "Record a successful synthetic outcome only after explicit expert "
            "validation; does not create or publish a scenario."
        ),
        schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "problem_signature": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "actions_taken": {
                    "type": "array", "minItems": 2, "maxItems": 20,
                    "items": {"type": "string"},
                },
                "expertise_types": {
                    "type": "array", "minItems": 1, "maxItems": 4,
                    "items": {"type": "string"},
                },
                "required_inputs": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string"},
                },
                "resolution_summary": {"type": "string", "minLength": 20},
                "expert_id": {"const": "EMP-DEMO-001"},
                "operator_decision": {
                    "enum": ["manual_resolution", "corrected_plan"],
                    "default": "manual_resolution",
                },
            },
            "required": [
                "case_id", "problem_signature", "actions_taken",
                "expertise_types", "required_inputs", "resolution_summary",
                "expert_id"
            ],
            "additionalProperties": False,
        },
        timeout_sec=60,
    )
