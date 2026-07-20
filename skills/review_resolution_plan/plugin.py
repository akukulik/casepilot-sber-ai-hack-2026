"""Ouroboros tool for CasePilot employee plan decisions."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR / "casepilot_project_dir.txt").read_text(encoding="utf-8").strip()
ROOT = (
    Path(_configured).expanduser()
    if _configured
    else (SKILL_DIR / _locator if not Path(_locator).is_absolute() else Path(_locator))
).resolve()
MODULE_PATH = ROOT / "casepilot" / "runtime.py"
SPEC = importlib.util.spec_from_file_location("casepilot_runtime_review", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Cannot load {MODULE_PATH}")
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


def register(api: Any) -> None:
    def review(
        _ctx: Any = None,
        case_id: str = "",
        plan_id: str = "",
        plan_version: int = 0,
        decision: str = "",
        employee_id: str = "",
        comment: Any = None,
    ) -> str:
        result = RUNTIME.review_plan(
            RUNTIME.RuntimeStore(ROOT),
            {
                "case_id": case_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "decision": decision,
                "employee_id": employee_id,
                "comment": comment,
            },
        )
        return json.dumps(result, ensure_ascii=False)

    api.register_tool(
        "review_resolution_plan",
        handler=review,
        description=(
            "Record the employee decision for the latest CasePilot plan. In Chat map "
            "'Подтверждаю' to approve_plan, 'Изменить: ...' to request_change with "
            "the text as comment, and 'Беру вручную' to manual_review. Resolve "
            "case_id, plan_id, and plan_version from the latest take_case result."
        ),
        schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "plan_version": {"type": "integer", "minimum": 1, "maximum": 2},
                "decision": {
                    "type": "string",
                    "enum": ["approve_plan", "request_change", "manual_review"],
                },
                "employee_id": {"type": "string", "const": "EMP-DEMO-001"},
                "comment": {"type": ["string", "null"]},
            },
            "required": [
                "case_id",
                "plan_id",
                "plan_version",
                "decision",
                "employee_id",
                "comment",
            ],
            "additionalProperties": False,
        },
        timeout_sec=30,
    )
