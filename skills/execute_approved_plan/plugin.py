"""Ouroboros wrapper for controlled CasePilot mock execution."""

from __future__ import annotations
import importlib.util, json, os
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR/"casepilot_project_dir.txt").read_text().strip()
ROOT = (Path(_configured).expanduser() if _configured else (SKILL_DIR/_locator if not Path(_locator).is_absolute() else Path(_locator))).resolve()
SPEC = importlib.util.spec_from_file_location("casepilot_runtime_execute", ROOT/"casepilot"/"runtime.py")
if SPEC is None or SPEC.loader is None: raise ImportError("CasePilot runtime unavailable")
RUNTIME = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(RUNTIME)

def register(api: Any) -> None:
    def run(_ctx: Any = None, plan_id: str = "", plan_version: int = 0) -> str:
        result = RUNTIME.execute_plan(RUNTIME.RuntimeStore(Path(ROOT)), plan_id, plan_version)
        return json.dumps(result, ensure_ascii=False)
    api.register_tool("execute_approved_plan", handler=run, description="Execute only the current approved plan with deterministic mock tools. Present compact step progress and a plain-language employee summary; hide service JSON and stack traces unless requested.", schema={"type":"object","properties":{"plan_id":{"type":"string"},"plan_version":{"type":"integer","minimum":1,"maximum":2}},"required":["plan_id","plan_version"],"additionalProperties":False}, timeout_sec=60)
