from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent
OUT_DEFAULT = (
    REPO
    / "outputs"
    / "manifests_20260601"
    / "A1_1BO_6UL_manual_roi_page1"
)
WATER_ENDPOINT_DIR = Path(
    r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\00 NAPL"
)
PRODUCTION_DIR = Path(
    r"G:\Microfluid\00 A1 1-BO 6 UL WATER DISPLACEMENT\01 WATER"
)

WATER_ENDPOINTS = [
    ("water_ep_00_napl_00_3s", "00 NAPL 3 SECONDS.tif"),
    ("water_ep_00_napl_00_3s_1", "00 NAPL 3 SECONDS_1.tif"),
    ("water_ep_00_napl_01_1s", "01 NAPL 1 SECONDS.tif"),
]

ENDPOINT_POLICY = {
    "primary": {
        "id": "A_full_consistency_primary",
        "short_name": "A",
        "water_label": "water_ep_00_napl_00_3s_1",
        "napl_label": "full_01_water_1s_3",
    },
    "sensitivity": {
        "id": "B_residual_separation_primary",
        "short_name": "B",
        "water_label": "water_ep_00_napl_01_1s",
        "napl_label": "full_00_water_3s_2",
    },
}


def natural_sort_key(path_value: Path) -> tuple:
    parts = re.split(r"(\d+)", path_value.stem.lower())
    key: list[object] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part)
    return tuple(key)


def label_for_production(path_value: Path) -> tuple[str, str]:
    stem = path_value.stem
    lower = stem.lower()
    if lower.startswith(("00 water", "01 water")):
        prefix = "full"
        role = "full_napl"
    elif lower.startswith("02 water"):
        prefix = "residual"
        role = "residual"
    else:
        prefix = "production"
        role = "production"

    normalized = re.sub(r"\s+seconds", "s", lower)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]+", "", normalized)
    return f"{prefix}_{normalized}", role


def require_file(path_value: Path) -> None:
    if not path_value.is_file():
        raise FileNotFoundError(f"Missing required file: {path_value}")


def build_rows(water_endpoint_dir: Path, production_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (label, name) in enumerate(WATER_ENDPOINTS, 1):
        path_value = water_endpoint_dir / name
        require_file(path_value)
        rows.append(
            {
                "label": label,
                "role": "water_endpoint",
                "frame_order": index,
                "timeseries_order": "",
                "source_path": str(path_value),
                "source_page": 1,
                "time_s": "",
                "include_in_timeseries": 0,
                "fit_sample": 1,
            }
        )

    tif_paths = sorted(production_dir.glob("*.tif"), key=natural_sort_key)
    if not tif_paths:
        raise FileNotFoundError(f"No .tif files found in: {production_dir}")

    seen_labels = {row["label"] for row in rows}
    for order, path_value in enumerate(tif_paths, 1):
        label, role = label_for_production(path_value)
        if label in seen_labels:
            raise ValueError(f"Duplicate generated label: {label}")
        seen_labels.add(label)
        rows.append(
            {
                "label": label,
                "role": role,
                "frame_order": len(WATER_ENDPOINTS) + order,
                "timeseries_order": order,
                "source_path": str(path_value),
                "source_page": 1,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 1,
            }
        )

    endpoint_labels = {
        ENDPOINT_POLICY["primary"]["water_label"],
        ENDPOINT_POLICY["primary"]["napl_label"],
        ENDPOINT_POLICY["sensitivity"]["water_label"],
        ENDPOINT_POLICY["sensitivity"]["napl_label"],
    }
    missing = sorted(endpoint_labels - seen_labels)
    if missing:
        raise ValueError(f"Endpoint policy refers to missing labels: {missing}")
    return rows


def write_manifest(rows: list[dict[str, object]], out_dir: Path, force: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "accepted_frames.csv"
    endpoint_path = out_dir / "endpoint_policy.json"
    summary_path = out_dir / "accepted_frames_summary.json"
    for path_value in [manifest_path, endpoint_path, summary_path]:
        if path_value.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {path_value}")

    fieldnames = [
        "label",
        "role",
        "frame_order",
        "timeseries_order",
        "source_path",
        "source_page",
        "time_s",
        "include_in_timeseries",
        "fit_sample",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    endpoint_path.write_text(
        json.dumps(ENDPOINT_POLICY, indent=2),
        encoding="utf-8",
    )
    role_counts: dict[str, int] = {}
    for row in rows:
        role = str(row["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
    summary = {
        "manifest_csv": str(manifest_path),
        "endpoint_policy_json": str(endpoint_path),
        "frame_count": len(rows),
        "roles": role_counts,
        "timeseries_frame_count": sum(
            int(row["include_in_timeseries"]) for row in rows
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"MANIFEST_DONE {manifest_path}")
    print(f"ENDPOINT_POLICY_DONE {endpoint_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--water-endpoint-dir", type=Path, default=WATER_ENDPOINT_DIR)
    parser.add_argument("--production-dir", type=Path, default=PRODUCTION_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    rows = build_rows(args.water_endpoint_dir, args.production_dir)
    write_manifest(rows, args.out_dir, args.force)


if __name__ == "__main__":
    main()
