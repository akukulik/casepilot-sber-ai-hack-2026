"""Ouroboros tool that creates governed CasePilot scenario drafts."""

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
    "casepilot_scenario_evolution_analyze",
    PROJECT / "casepilot" / "scenario_evolution.py",
)
if spec is None or spec.loader is None:
    raise ImportError("CasePilot scenario evolution module unavailable")
EVOLUTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVOLUTION)


def register(api: Any) -> None:
    def run(_ctx: Any = None, minimum_cluster_size: int = 3) -> str:
        result = EVOLUTION.analyze_gaps(
            PROJECT,
            minimum_cluster_size=max(3, min(int(minimum_cluster_size), 10)),
        )
        return json.dumps(result, ensure_ascii=False)

    api.register_tool(
        "analyze_scenario_gaps",
        handler=run,
        description=(
            "Create draft scenarios from repeated expert-validated manual "
            "resolutions. Never publishes."
        ),
        schema={
            "type": "object",
            "properties": {
                "minimum_cluster_size": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 10,
                    "default": 3,
                }
            },
            "additionalProperties": False,
        },
        timeout_sec=60,
    )
