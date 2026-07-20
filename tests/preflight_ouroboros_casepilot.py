"""Run Ouroboros' deterministic skill preflight for CasePilot extensions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


OUROBOROS_HOME = Path(os.environ.get("OUROBOROS_HOME", "~/Ouroboros")).expanduser()
sys.path.insert(0, str(OUROBOROS_HOME / "repo"))

from ouroboros.tools.registry import ToolContext  # noqa: E402
from ouroboros.tools.skill_preflight import _handle_skill_preflight  # noqa: E402


SKILLS = [
    "find_case_scenarios",
    "take_case",
    "build_resolution_plan",
    "review_resolution_plan",
    "check_account_state",
    "check_pending_operations",
    "request_expertise",
    "check_account_closure_eligibility",
    "execute_approved_plan",
    "case-actions",
    "build-resolution-recommendation",
    "analyze-scenario-gaps",
    "validate-scenario-draft",
    "review-scenario-draft",
    "record-scenario-outcome",
]


def main() -> None:
    context = ToolContext(
        repo_dir=OUROBOROS_HOME / "repo",
        drive_root=OUROBOROS_HOME / "data",
        task_id="casepilot_iteration_3_preflight",
        messages=[],
    )
    results = {}
    for skill in SKILLS:
        rendered = _handle_skill_preflight(context, skill=skill)
        results[skill] = rendered
        if "SKILL_PREFLIGHT_ERROR" in rendered or '"ok": false' in rendered.lower():
            raise AssertionError(f"{skill}: {rendered}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
