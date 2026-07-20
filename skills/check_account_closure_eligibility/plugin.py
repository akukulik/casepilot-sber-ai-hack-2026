"""Ouroboros wrapper for deterministic closure eligibility."""

from __future__ import annotations
import importlib.util, json, os
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR/"casepilot_project_dir.txt").read_text().strip()
ROOT = (Path(_configured).expanduser() if _configured else (SKILL_DIR/_locator if not Path(_locator).is_absolute() else Path(_locator))).resolve()
SPEC = importlib.util.spec_from_file_location("casepilot_runtime_eligibility", ROOT/"casepilot"/"runtime.py")
if SPEC is None or SPEC.loader is None: raise ImportError("CasePilot runtime unavailable")
RUNTIME = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(RUNTIME)

def register(api: Any) -> None:
    def run(_ctx: Any = None, case_id: str = "", account_id: str = "", previous_results: Any = None) -> str:
        try: result = RUNTIME.check_account_closure_eligibility(Path(ROOT), case_id, account_id, previous_results if isinstance(previous_results, list) else [])
        except Exception as error: result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)
    api.register_tool("closure_eligibility", handler=run, description="Assess synthetic closure eligibility; never closes an account.", schema={"type":"object","properties":{"case_id":{"type":"string"},"account_id":{"type":"string"},"previous_results":{"type":"array","items":{"type":"object","additionalProperties":True}}},"required":["case_id","account_id","previous_results"],"additionalProperties":False}, timeout_sec=30)
