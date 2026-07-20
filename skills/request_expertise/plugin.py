"""Ouroboros wrapper for deterministic expertise."""

from __future__ import annotations
import importlib.util, json, os
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR/"casepilot_project_dir.txt").read_text().strip()
ROOT = (Path(_configured).expanduser() if _configured else (SKILL_DIR/_locator if not Path(_locator).is_absolute() else Path(_locator))).resolve()
SPEC = importlib.util.spec_from_file_location("casepilot_runtime_expertise", ROOT/"casepilot"/"runtime.py")
if SPEC is None or SPEC.loader is None: raise ImportError("CasePilot runtime unavailable")
RUNTIME = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(RUNTIME)

def register(api: Any) -> None:
    def run(_ctx: Any = None, plan_id: str = "", plan_version: int = 0, case_id: str = "", expertise_type: str = "", inputs: Any = None) -> str:
        try:
            store = RUNTIME.RuntimeStore(Path(ROOT)); record = store.plan(plan_id, plan_version)
            if record is None or record["status"] not in {"approved","executing"}: raise ValueError("approved plan not found")
            result = RUNTIME.request_expertise(Path(ROOT), record["plan"], case_id, expertise_type, inputs if isinstance(inputs, dict) else {})
        except Exception as error: result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)
    api.register_tool("request_expertise", handler=run, description="Run one deterministic expertise authorized by the current approved plan.", schema={"type":"object","properties":{"plan_id":{"type":"string"},"plan_version":{"type":"integer","minimum":1,"maximum":2},"case_id":{"type":"string"},"expertise_type":{"type":"string"},"inputs":{"type":"object","additionalProperties":True}},"required":["plan_id","plan_version","case_id","expertise_type","inputs"],"additionalProperties":False}, timeout_sec=30)
