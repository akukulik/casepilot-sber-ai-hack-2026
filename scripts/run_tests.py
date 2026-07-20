#!/usr/bin/env python3
"""Run the dependency-light CasePilot validation suite."""

from __future__ import annotations

import argparse
import subprocess
import sys
import os
from pathlib import Path


TESTS = (
    "tests/validate_casepilot_data.py",
    "tests/validate_scenario_candidates.py",
    "tests/test_scenario_evolution.py",
    "tests/test_casepilot_retrieval.py",
    "tests/test_casepilot_runtime.py",
    "tests/test_casepilot_outcomes.py",
    "tests/test_casepilot_extended_scenario.py",
    "tests/test_resolution_recommendation.py",
    "tests/test_frontend_execution_api.py",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-ouroboros",
        action="store_true",
        help="Also run native preflight against locally installed Ouroboros Skills.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    existing_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(root) if not existing_path else f"{root}{os.pathsep}{existing_path}"
    )
    selected = TESTS + (
        ("tests/preflight_ouroboros_casepilot.py",)
        if args.include_ouroboros
        else ()
    )
    for relative in selected:
        print(f"\n==> {relative}", flush=True)
        subprocess.run(
            [sys.executable, str(root / relative)],
            cwd=root,
            env=environment,
            check=True,
        )
    print(f"\nPASS: {len(selected)} CasePilot test programs.")


if __name__ == "__main__":
    main()
