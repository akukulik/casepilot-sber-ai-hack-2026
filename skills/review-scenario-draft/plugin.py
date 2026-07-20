"""Human review and controlled publication of CasePilot scenario drafts."""

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
    "casepilot_scenario_evolution_review",
    PROJECT / "casepilot" / "scenario_evolution.py",
)
if spec is None or spec.loader is None:
    raise ImportError("CasePilot scenario evolution module unavailable")
EVOLUTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVOLUTION)


def register(api: Any) -> None:
    def run(
        _ctx: Any = None,
        draft_id: str = "",
        decision: str = "",
        expert_id: str = "",
        comment: Any = None,
    ) -> str:
        try:
            result = EVOLUTION.review_draft(
                PROJECT,
                draft_id=draft_id.strip(),
                decision=decision.strip(),
                expert_id=expert_id.strip(),
                comment=str(comment).strip() if comment is not None else None,
            )
        except Exception as error:
            result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)

    api.register_tool(
        "review_scenario_draft",
        handler=run,
        description=(
            "Approve or reject one independently validated scenario draft as "
            "EMP-DEMO-001."
        ),
        schema={
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "pattern": "^SCD-[0-9]{4}$"},
                "decision": {"enum": ["approve", "reject"]},
                "expert_id": {"const": "EMP-DEMO-001"},
                "comment": {"type": ["string", "null"]},
            },
            "required": ["draft_id", "decision", "expert_id"],
            "additionalProperties": False,
        },
        timeout_sec=60,
    )
