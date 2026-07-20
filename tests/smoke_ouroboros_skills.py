"""Run the CasePilot Skills through Ouroboros' real skill_exec substrate."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUROBOROS_HOME = Path(os.environ.get("OUROBOROS_HOME", "~/Ouroboros")).expanduser()
sys.path.insert(0, str(OUROBOROS_HOME / "repo"))

from ouroboros.tools.registry import ToolContext  # noqa: E402
from ouroboros.tools.skill_exec import _handle_skill_exec  # noqa: E402


def execute(ctx: ToolContext, skill: str, script: str, args: list[str]) -> dict:
    rendered = _handle_skill_exec(ctx, skill=skill, script=script, args=args)
    envelope = json.loads(rendered)
    if envelope["exit_code"] != 0:
        raise AssertionError(rendered)
    return json.loads(envelope["stdout"])


def main() -> None:
    ctx = ToolContext(
        repo_dir=OUROBOROS_HOME / "repo",
        drive_root=OUROBOROS_HOME / "data",
        task_id="casepilot_skill_smoke",
        messages=[],
    )
    loaded = execute(
        ctx,
        "load_case",
        "load_case.py",
        ["VAL-DC-001"],
    )
    assert loaded["status"] == "ok"

    missing = execute(
        ctx,
        "load_case",
        "load_case.py",
        ["VAL-DC-999"],
    )
    assert missing["status"] == "not_found"

    similar = execute(
        ctx,
        "find_similar_cases",
        "find_similar_cases.py",
        [
            "--case-json",
            json.dumps(loaded["case"], ensure_ascii=False),
            "--limit",
            "3",
        ],
    )
    assert similar["status"] == "ok"
    assert similar["results"][0]["case_id"] == "HIST-DC-002"

    print(
        json.dumps(
            {
                "load_case": loaded["status"],
                "missing_case": missing["status"],
                "find_similar_cases": similar["status"],
                "ranking": [
                    {"case_id": item["case_id"], "score": item["score"]}
                    for item in similar["results"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
