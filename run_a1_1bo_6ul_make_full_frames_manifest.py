from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import tifffile


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


def endpoint_policy(
    expand_pages: bool,
    endpoint_policy_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    if endpoint_policy_path is None:
        policy = json.loads(json.dumps(ENDPOINT_POLICY))
    else:
        policy = json.loads(endpoint_policy_path.read_text(encoding="utf-8"))
    for key in ["primary", "sensitivity"]:
        if key not in policy:
            raise ValueError(f"Endpoint policy is missing required key: {key}")
        for field in ["id", "short_name", "water_label", "napl_label"]:
            if field not in policy[key]:
                raise ValueError(
                    f"Endpoint policy {key!r} is missing required field: {field}"
                )
    if expand_pages:
        for endpoint in policy.values():
            napl_label = str(endpoint["napl_label"])
            if not re.search(r"_p\d{3}$", napl_label):
                endpoint["napl_label"] = f"{napl_label}_p001"
    return policy


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


def page_label(base_label: str, page: int) -> str:
    return f"{base_label}_p{page:03d}"


def tif_page_count(path_value: Path) -> int:
    with tifffile.TiffFile(path_value) as tif:
        return len(tif.pages)


def select_page_indices(total_count: int, max_pages: int | None, mode: str) -> set[int]:
    if max_pages is None or max_pages >= total_count:
        return set(range(total_count))
    if max_pages <= 0:
        raise ValueError("--max-pages must be positive when provided.")
    if mode == "first":
        return set(range(max_pages))
    if mode != "uniform":
        raise ValueError(f"Unsupported page selection mode: {mode}")
    if max_pages == 1:
        return {0}
    selected = {
        round(index * (total_count - 1) / (max_pages - 1))
        for index in range(max_pages)
    }
    cursor = 0
    while len(selected) < max_pages:
        selected.add(cursor)
        cursor += 1
    return selected


def format_time_s(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".")


def require_file(path_value: Path) -> None:
    if not path_value.is_file():
        raise FileNotFoundError(f"Missing required file: {path_value}")


def build_rows(
    water_endpoint_dir: Path,
    production_dir: Path,
    expand_pages: bool,
    max_pages: int | None,
    page_selection: str,
    fit_sample_stride: int,
    endpoint_policy_path: Path | None = None,
    time_step_s: float | None = None,
    time_start_s: float = 0.0,
) -> tuple[list[dict[str, object]], dict[str, dict[str, str]]]:
    if fit_sample_stride < 1:
        raise ValueError("--fit-sample-stride must be >= 1.")
    if time_step_s is not None and time_step_s <= 0:
        raise ValueError("--time-step-s must be positive when provided.")

    policy = endpoint_policy(expand_pages, endpoint_policy_path)
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

    production_candidates: list[dict[str, object]] = []
    for path_value in tif_paths:
        base_label, role = label_for_production(path_value)
        page_count = tif_page_count(path_value) if expand_pages else 1
        for page in range(1, page_count + 1):
            label = page_label(base_label, page) if expand_pages else base_label
            production_candidates.append(
                {
                    "label": label,
                    "role": role,
                    "source_path": str(path_value),
                    "source_page": page,
                }
            )

    selected_indices = select_page_indices(
        len(production_candidates),
        max_pages,
        page_selection,
    )
    endpoint_labels = {
        policy["primary"]["napl_label"],
        policy["sensitivity"]["napl_label"],
    }
    for index, candidate in enumerate(production_candidates):
        if candidate["label"] in endpoint_labels:
            selected_indices.add(index)

    seen_labels = {row["label"] for row in rows}
    timeseries_order = 0
    for index, candidate in enumerate(production_candidates):
        label = str(candidate["label"])
        include = index in selected_indices
        if not include and label not in endpoint_labels:
            continue
        if label in seen_labels:
            raise ValueError(f"Duplicate generated label: {label}")
        seen_labels.add(label)
        if include:
            timeseries_order += 1
        time_s = ""
        if include and time_step_s is not None:
            time_s = format_time_s(time_start_s + (timeseries_order - 1) * time_step_s)
        is_endpoint = label in endpoint_labels
        fit_sample = int(
            is_endpoint
            or (include and ((max(timeseries_order, 1) - 1) % fit_sample_stride == 0))
        )
        rows.append(
            {
                "label": label,
                "role": candidate["role"],
                "frame_order": len(rows) + 1,
                "timeseries_order": timeseries_order if include else "",
                "source_path": candidate["source_path"],
                "source_page": int(candidate["source_page"]),
                "time_s": time_s,
                "include_in_timeseries": int(include),
                "fit_sample": fit_sample,
            }
        )

    endpoint_labels = {
        policy["primary"]["water_label"],
        policy["primary"]["napl_label"],
        policy["sensitivity"]["water_label"],
        policy["sensitivity"]["napl_label"],
    }
    missing = sorted(endpoint_labels - seen_labels)
    if missing:
        raise ValueError(f"Endpoint policy refers to missing labels: {missing}")
    return rows, policy


def write_manifest(
    rows: list[dict[str, object]],
    policy: dict[str, dict[str, str]],
    out_dir: Path,
    force: bool,
    time_step_s: float | None = None,
    time_start_s: float = 0.0,
) -> None:
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
        json.dumps(policy, indent=2),
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
        "fit_sample_frame_count": sum(int(row["fit_sample"]) for row in rows),
        "time_model": "sequence" if time_step_s is not None else "blank",
        "time_start_s": time_start_s if time_step_s is not None else "",
        "time_step_s": time_step_s if time_step_s is not None else "",
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"MANIFEST_DONE {manifest_path}")
    print(f"ENDPOINT_POLICY_DONE {endpoint_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--water-endpoint-dir", type=Path, default=WATER_ENDPOINT_DIR)
    parser.add_argument("--production-dir", type=Path, default=PRODUCTION_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--expand-pages", action="store_true")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument(
        "--page-selection",
        choices=["first", "uniform"],
        default="first",
    )
    parser.add_argument("--fit-sample-stride", type=int, default=1)
    parser.add_argument(
        "--time-step-s",
        type=float,
        default=None,
        help="Optional constant time increment for included timeseries rows.",
    )
    parser.add_argument(
        "--time-start-s",
        type=float,
        default=0.0,
        help="Start time used with --time-step-s.",
    )
    parser.add_argument(
        "--endpoint-policy",
        type=Path,
        default=None,
        help="Optional endpoint policy JSON. Production NAPL labels are suffixed with _p001 when --expand-pages is used.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    rows, policy = build_rows(
        args.water_endpoint_dir,
        args.production_dir,
        args.expand_pages,
        args.max_pages,
        args.page_selection,
        args.fit_sample_stride,
        args.endpoint_policy,
        args.time_step_s,
        args.time_start_s,
    )
    write_manifest(
        rows,
        policy,
        args.out_dir,
        args.force,
        args.time_step_s,
        args.time_start_s,
    )


if __name__ == "__main__":
    main()
