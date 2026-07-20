"""Ouroboros wrapper for deterministic account state."""

from __future__ import annotations
import importlib.util, json, os
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
_configured = os.environ.get("CASEPILOT_PROJECT_DIR", "").strip()
_locator = (SKILL_DIR/"casepilot_project_dir.txt").read_text().strip()
ROOT = (Path(_configured).expanduser() if _configured else (SKILL_DIR/_locator if not Path(_locator).is_absolute() else Path(_locator))).resolve()
SPEC = importlib.util.spec_from_file_location("casepilot_runtime_state", ROOT/"casepilot"/"runtime.py")
if SPEC is None or SPEC.loader is None: raise ImportError("CasePilot runtime unavailable")
RUNTIME = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(RUNTIME)

def register(api: Any) -> None:
    def run(_ctx: Any = None, case_id: str = "", account_id: str = "") -> str:
        try: result = RUNTIME.check_account_state(Path(ROOT), case_id, account_id)
        except Exception as error: result = {"status": "error", "errors": [str(error)]}
        return json.dumps(result, ensure_ascii=False)
    api.register_tool("check_account_state", handler=run, description="Read synthetic balances, holds, restrictions, and account status.", schema={"type":"object","properties":{"case_id":{"type":"string"},"account_id":{"type":"string"}},"required":["case_id","account_id"],"additionalProperties":False}, timeout_sec=30)
