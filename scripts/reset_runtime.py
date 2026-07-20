#!/usr/bin/env python3
"""Reset CasePilot runtime stores without touching synthetic source data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


STORE_NAMES = (
    "runs.json",
    "plans.json",
    "approvals.json",
    "executions.json",
    "recommendations.json",
    "scenario_drafts.json",
    "scenario_reviews.json",
    "published_scenarios.json",
    "scenario_learning_events.json",
)


def reset(project_root: Path) -> None:
    runtime = project_root / "data" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in STORE_NAMES:
        (runtime / name).write_text("[]\n", encoding="utf-8")
    (runtime / "audit_log.jsonl").write_text("", encoding="utf-8")
    (runtime / "scenario_evolution_audit.jsonl").write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    reset(args.project_root.resolve())
    print("CasePilot runtime reset: 9 JSON stores and 2 audit logs are empty.")


if __name__ == "__main__":
    main()
