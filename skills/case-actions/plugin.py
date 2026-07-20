"""Ouroboros wrappers for strictly allow-listed synthetic CasePilot actions."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR / "casepilot_project_dir.txt").read_text().strip()
ROOT = (
    Path(_configured).expanduser()
    if _configured
    else (SKILL_DIR / _locator if not Path(_locator).is_absolute() else Path(_locator))
).resolve()
SPEC = importlib.util.spec_from_file_location(
    "casepilot_runtime_actions", ROOT / "casepilot" / "runtime.py"
)
if SPEC is None or SPEC.loader is None:
    raise ImportError("CasePilot runtime unavailable")
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


def register(api: Any) -> None:
    schema = {
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "previous_results": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["case_id", "previous_results"],
        "additionalProperties": False,
    }
    tools = {
        "wait_settlement": (
            "wait_for_settlement",
            "Record a synthetic settlement waiting state.",
        ),
        "draft_postclose_instr": (
            "record_post_closure_instruction",
            "Draft a synthetic post-closure instruction.",
        ),
        "collect_compliance": (
            "collect_compliance_evidence",
            "Prepare a synthetic compliance evidence checklist.",
        ),
        "match_cash_surplus": (
            "match_collection_surplus",
            "Prepare a synthetic cash collection match review.",
        ),
        "draft_resolution": (
            "prepare_resolution_decision",
            "Draft a synthetic employee resolution decision.",
        ),
    }

    for tool_name, (action, description) in tools.items():
        def run(
            _ctx: Any = None,
            case_id: str = "",
            previous_results: list[dict[str, Any]] | None = None,
            *,
            _action: str = action,
        ) -> str:
            try:
                result = RUNTIME.perform_case_action(
                    Path(ROOT), case_id, _action, previous_results or []
                )
            except Exception as error:
                result = {"status": "error", "errors": [str(error)]}
            return json.dumps(result, ensure_ascii=False)

        api.register_tool(
            tool_name,
            handler=run,
            description=description + " No real banking mutation is performed.",
            schema=schema,
            timeout_sec=30,
        )
