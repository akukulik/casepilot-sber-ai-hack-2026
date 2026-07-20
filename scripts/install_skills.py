#!/usr/bin/env python3
"""Install CasePilot Skills into an existing Ouroboros profile."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_LOCATOR = "casepilot_project_dir.txt"
DATA_LOCATOR = "casepilot_data_dir.txt"


def install(project_root: Path, ouroboros_home: Path) -> list[str]:
    source_root = project_root / "skills"
    target_root = ouroboros_home / "data" / "skills" / "external"
    if not source_root.is_dir():
        raise FileNotFoundError(f"Skills directory not found: {source_root}")
    if not (ouroboros_home / "data").is_dir():
        raise FileNotFoundError(
            f"Ouroboros profile not found: {ouroboros_home}. "
            "Launch Ouroboros once before installing Skills."
        )
    target_root.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for source in sorted(source_root.iterdir()):
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            continue
        target = target_root / source.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        project_locator = target / PROJECT_LOCATOR
        data_locator = target / DATA_LOCATOR
        if project_locator.exists():
            project_locator.write_text(str(project_root) + "\n", encoding="utf-8")
        if data_locator.exists():
            data_locator.write_text(str(project_root / "data") + "\n", encoding="utf-8")
        installed.append(source.name)
    return installed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--ouroboros-home",
        type=Path,
        default=Path(os.environ.get("OUROBOROS_HOME", "~/Ouroboros")).expanduser(),
    )
    args = parser.parse_args()
    installed = install(args.project_root.resolve(), args.ouroboros_home.resolve())
    print(f"Installed {len(installed)} Skills into {args.ouroboros_home.resolve()}.")
    print("Open Ouroboros Skills and repeat review/enable for changed content hashes.")


if __name__ == "__main__":
    main()
