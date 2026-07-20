"""Independent deterministic validation for a CasePilot scenario draft."""

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
    "casepilot_scenario_evolution_validate",
    PROJECT / "casepilot" / "scenario_evolution.py",
)
if spec is None or spec.loader is None:
    raise ImportError("CasePilot scenario evolution module unavailable")
EVOLUTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVOLUTION)


def register(api: Any) -> None:
    def run(_ctx: Any = None, draft_id: str = "") -> str:
        return json.dumps(
            EVOLUTION.validate_draft(PROJECT, draft_id.strip()),
            ensure_ascii=False,
        )

    api.register_tool(
        "validate_scenario_draft",
        handler=run,
        description=(
            "Validate a scenario draft and run offline replay; never approves "
            "or publishes it."
        ),
        schema={
            "type": "object",
            "properties": {"draft_id": {"type": "string", "pattern": "^SCD-[0-9]{4}$"}},
            "required": ["draft_id"],
            "additionalProperties": False,
        },
        timeout_sec=60,
    )
