"""Load a CasePilot validation case by case_id."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


_DATA_FILE = "validation_cases.json"
_FORBIDDEN_FIELDS = {"resolution_plan", "expertise_results", "final_result"}


def _default_data_dir() -> Path:
    configured = os.environ.get("CASEPILOT_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    skill_root = Path(__file__).resolve().parents[1]
    locator = skill_root / "casepilot_data_dir.txt"
    if locator.is_file():
        located = locator.read_text(encoding="utf-8").strip()
        if located:
            path = Path(located).expanduser()
            return (path if path.is_absolute() else skill_root / path).resolve()

    for base in (skill_root, *skill_root.parents, Path.cwd(), *Path.cwd().parents):
        candidate = base / "data"
        if (candidate / _DATA_FILE).is_file():
            return candidate

    raise FileNotFoundError(
        "CasePilot data directory was not found. Set CASEPILOT_DATA_DIR, "
        "create casepilot_data_dir.txt in the Skill root, or pass --data-dir."
    )


def _load_cases(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / _DATA_FILE
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, list):
        raise ValueError(f"{_DATA_FILE} must contain a JSON array")
    cases = [item for item in payload if isinstance(item, dict)]
    if len(cases) != len(payload):
        raise ValueError(f"{_DATA_FILE} contains a non-object item")
    for case in cases:
        leaked = sorted(_FORBIDDEN_FIELDS.intersection(case))
        if leaked:
            raise ValueError(
                f"validation case {case.get('case_id', '<unknown>')} contains forbidden fields: {leaked}"
            )
    return cases


def load_case(case_id: str, data_dir: Path) -> dict[str, Any]:
    normalized_id = case_id.strip()
    if not normalized_id:
        return {
            "status": "invalid_request",
            "case_id": normalized_id,
            "case": None,
            "error": "case_id must not be empty",
        }
    for case in _load_cases(data_dir):
        if case.get("case_id") == normalized_id:
            return {
                "status": "ok",
                "case_id": normalized_id,
                "case": case,
                "error": None,
            }
    return {
        "status": "not_found",
        "case_id": normalized_id,
        "case": None,
        "error": f"Validation case '{normalized_id}' was not found.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id", help="Validation case ID, for example VAL-DC-001")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_default_data_dir(),
        help="Directory containing validation_cases.json",
    )
    args = parser.parse_args()
    try:
        result = load_case(args.case_id, args.data_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        result = {
            "status": "data_error",
            "case_id": args.case_id.strip(),
            "case": None,
            "error": str(error),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
