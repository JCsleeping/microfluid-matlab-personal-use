"""Summarize Branch C endpoint consistency across expanded frame roles.

This postprocess is a lightweight guard after the masked reference audit has
selected endpoint policies. It does not re-estimate illumination correction or
regenerate masks. It checks whether frames labeled as full-NAPL/residual in the
accepted-frame manifest behave consistently in endpoint-normalized Branch C
outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path, PureWindowsPath
from typing import Any


PRIMARY_CSV = "S_NAPL_color_primary_A.csv"
SENSITIVITY_CSV = "S_NAPL_color_sensitivity_B.csv"
COMPARISON_CSV = "S_NAPL_color_A_B_sensitivity_comparison.csv"

TIMESERIES_FIELDS = (
    "frame_index",
    "label",
    "role",
    "source_stem",
    "source_page",
    "source_path",
    "S_NAPL_color_A",
    "S_NAPL_color_B",
    "S_NAPL_color_B_minus_A",
    "abs_endpoint_sensitivity",
    "is_policy_napl_endpoint",
    "endpoint_consistency_status",
    "endpoint_consistency_reason",
)
SOURCE_SUMMARY_FIELDS = (
    "role",
    "source_stem",
    "row_count",
    "source_page_min",
    "source_page_max",
    "S_A_min",
    "S_A_median",
    "S_A_max",
    "S_B_min",
    "S_B_median",
    "S_B_max",
    "flag_count",
    "full_below_threshold_count",
    "residual_above_threshold_count",
    "policy_napl_endpoint_count",
)


def read_csv_rows(path_value: Path) -> list[dict[str, str]]:
    if not path_value.is_file():
        raise FileNotFoundError(f"Missing CSV input: {path_value}")
    with path_value.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path_value: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    with path_value.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def finite_int(value: Any) -> int | None:
    number = finite_float(value)
    if number is None:
        return None
    return int(number)


def median_or_nan(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return float("nan")
    return float(statistics.median(finite))


def min_or_nan(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return float("nan")
    return float(min(finite))


def max_or_nan(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return float("nan")
    return float(max(finite))


def path_stem(path_text: str, fallback_label: str) -> str:
    if not path_text:
        return fallback_label.rsplit("_p", 1)[0]
    if "\\" in path_text:
        return PureWindowsPath(path_text).stem
    return Path(path_text).stem


def read_policy_napl_labels(path_value: Path | None) -> set[str]:
    if path_value is None or not path_value.is_file():
        return set()
    payload = json.loads(path_value.read_text(encoding="utf-8"))
    labels: set[str] = set()
    if not isinstance(payload, dict):
        return labels
    for value in payload.values():
        if isinstance(value, dict) and value.get("napl_label"):
            labels.add(str(value["napl_label"]))
    return labels


def indexed_by_label(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        label = row.get("label", "")
        if label:
            indexed[label] = row
    return indexed


def endpoint_status(
    role: str,
    s_a: float | None,
    s_b: float | None,
    *,
    full_pass_threshold: float,
    residual_max_threshold: float,
) -> tuple[str, str]:
    values = [value for value in (s_a, s_b) if value is not None]
    if role == "full_napl":
        if not values:
            return "review", "missing_full_score"
        if any(value < full_pass_threshold for value in values):
            return "review", "full_napl_below_threshold"
        return "pass", "full_napl_near_endpoint"
    if role == "residual":
        if not values:
            return "review", "missing_residual_score"
        if any(value > residual_max_threshold for value in values):
            return "review", "residual_above_threshold"
        return "pass", "residual_below_threshold"
    return "informational", "role_not_endpoint_audited"


def build_endpoint_consistency_rows(
    *,
    manifest_rows: list[dict[str, str]],
    primary_rows: list[dict[str, str]],
    sensitivity_rows: list[dict[str, str]],
    comparison_rows: list[dict[str, str]],
    policy_napl_labels: set[str],
    full_pass_threshold: float,
    residual_max_threshold: float,
) -> list[dict[str, Any]]:
    manifest_by_label = indexed_by_label(manifest_rows)
    sensitivity_by_label = indexed_by_label(sensitivity_rows)
    comparison_by_label = indexed_by_label(comparison_rows)
    out_rows: list[dict[str, Any]] = []
    for primary in primary_rows:
        label = primary.get("label", "")
        manifest = manifest_by_label.get(label, {})
        sensitivity = sensitivity_by_label.get(label, {})
        comparison = comparison_by_label.get(label, {})
        role = primary.get("role") or manifest.get("role", "")
        s_a = finite_float(primary.get("S_NAPL_color", ""))
        s_b = finite_float(sensitivity.get("S_NAPL_color", ""))
        status, reason = endpoint_status(
            role,
            s_a,
            s_b,
            full_pass_threshold=full_pass_threshold,
            residual_max_threshold=residual_max_threshold,
        )
        source_path = manifest.get("source_path", "")
        out_rows.append(
            {
                "frame_index": finite_int(primary.get("frame_index", "")),
                "label": label,
                "role": role,
                "source_stem": path_stem(source_path, label),
                "source_page": finite_int(manifest.get("source_page", "")),
                "source_path": source_path,
                "S_NAPL_color_A": s_a if s_a is not None else float("nan"),
                "S_NAPL_color_B": s_b if s_b is not None else float("nan"),
                "S_NAPL_color_B_minus_A": finite_float(
                    comparison.get("S_NAPL_color_B_minus_A", "")
                )
                if comparison
                else float("nan"),
                "abs_endpoint_sensitivity": finite_float(
                    comparison.get("abs_endpoint_sensitivity", "")
                )
                if comparison
                else float("nan"),
                "is_policy_napl_endpoint": int(label in policy_napl_labels),
                "endpoint_consistency_status": status,
                "endpoint_consistency_reason": reason,
            }
        )
    return out_rows


def build_source_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["role"]), str(row["source_stem"])), []).append(row)

    summaries: list[dict[str, Any]] = []
    for (role, stem), group in sorted(groups.items()):
        pages = [
            int(row["source_page"])
            for row in group
            if isinstance(row.get("source_page"), int)
        ]
        s_a_values = [
            float(row["S_NAPL_color_A"])
            for row in group
            if isinstance(row.get("S_NAPL_color_A"), (int, float))
        ]
        s_b_values = [
            float(row["S_NAPL_color_B"])
            for row in group
            if isinstance(row.get("S_NAPL_color_B"), (int, float))
        ]
        flag_count = sum(
            1
            for row in group
            if row.get("endpoint_consistency_status") == "review"
        )
        summaries.append(
            {
                "role": role,
                "source_stem": stem,
                "row_count": len(group),
                "source_page_min": min(pages) if pages else "",
                "source_page_max": max(pages) if pages else "",
                "S_A_min": min_or_nan(s_a_values),
                "S_A_median": median_or_nan(s_a_values),
                "S_A_max": max_or_nan(s_a_values),
                "S_B_min": min_or_nan(s_b_values),
                "S_B_median": median_or_nan(s_b_values),
                "S_B_max": max_or_nan(s_b_values),
                "flag_count": flag_count,
                "full_below_threshold_count": sum(
                    1
                    for row in group
                    if row.get("endpoint_consistency_reason")
                    == "full_napl_below_threshold"
                ),
                "residual_above_threshold_count": sum(
                    1
                    for row in group
                    if row.get("endpoint_consistency_reason")
                    == "residual_above_threshold"
                ),
                "policy_napl_endpoint_count": sum(
                    int(row.get("is_policy_napl_endpoint", 0)) for row in group
                ),
            }
        )
    return summaries


def build_summary_json(
    *,
    rows: list[dict[str, Any]],
    flags: list[dict[str, Any]],
    source_summary: list[dict[str, Any]],
    full_pass_threshold: float,
    residual_max_threshold: float,
    policy_napl_labels: set[str],
    paths: dict[str, Path],
) -> dict[str, Any]:
    full_flags = [
        row
        for row in flags
        if row.get("endpoint_consistency_reason") == "full_napl_below_threshold"
    ]
    residual_flags = [
        row
        for row in flags
        if row.get("endpoint_consistency_reason") == "residual_above_threshold"
    ]
    return {
        "status": "review" if flags else "pass",
        "row_count": len(rows),
        "flag_count": len(flags),
        "full_napl_below_threshold_count": len(full_flags),
        "residual_above_threshold_count": len(residual_flags),
        "full_pass_threshold": full_pass_threshold,
        "residual_max_threshold": residual_max_threshold,
        "policy_napl_labels": sorted(policy_napl_labels),
        "flag_sample_labels": [str(row.get("label", "")) for row in flags[:20]],
        "source_summary_count": len(source_summary),
        "files": {key: str(value) for key, value in paths.items()},
        "semantics": (
            "Endpoint consistency postprocess over endpoint-normalized Branch C "
            "outputs; flags expanded full/residual role pages that do not match "
            "masked-audit endpoint expectations. This is not a new RGB audit."
        ),
    }


def run_endpoint_consistency(
    *,
    manifest: Path,
    branch_c_dir: Path,
    out_dir: Path,
    endpoint_policy: Path | None,
    full_pass_threshold: float,
    residual_max_threshold: float,
) -> dict[str, Any]:
    manifest_rows = read_csv_rows(manifest)
    primary_rows = read_csv_rows(branch_c_dir / PRIMARY_CSV)
    sensitivity_rows = read_csv_rows(branch_c_dir / SENSITIVITY_CSV)
    comparison_rows = read_csv_rows(branch_c_dir / COMPARISON_CSV)
    policy_napl_labels = read_policy_napl_labels(endpoint_policy)

    rows = build_endpoint_consistency_rows(
        manifest_rows=manifest_rows,
        primary_rows=primary_rows,
        sensitivity_rows=sensitivity_rows,
        comparison_rows=comparison_rows,
        policy_napl_labels=policy_napl_labels,
        full_pass_threshold=full_pass_threshold,
        residual_max_threshold=residual_max_threshold,
    )
    flags = [
        row for row in rows if row["endpoint_consistency_status"] == "review"
    ]
    source_summary = build_source_summary(rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": manifest,
        "branch_c_dir": branch_c_dir,
        "endpoint_policy": endpoint_policy or Path(""),
        "timeseries_csv": out_dir / "endpoint_consistency_timeseries.csv",
        "flags_csv": out_dir / "endpoint_consistency_flags.csv",
        "source_summary_csv": out_dir / "endpoint_consistency_source_summary.csv",
        "summary_json": out_dir / "endpoint_consistency_summary.json",
    }
    write_csv(paths["timeseries_csv"], rows, TIMESERIES_FIELDS)
    write_csv(paths["flags_csv"], flags, TIMESERIES_FIELDS)
    write_csv(paths["source_summary_csv"], source_summary, SOURCE_SUMMARY_FIELDS)
    summary = build_summary_json(
        rows=rows,
        flags=flags,
        source_summary=source_summary,
        full_pass_threshold=full_pass_threshold,
        residual_max_threshold=residual_max_threshold,
        policy_napl_labels=policy_napl_labels,
        paths=paths,
    )
    paths["summary_json"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--branch-c-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--endpoint-policy", type=Path, default=None)
    parser.add_argument("--full-pass-threshold", type=float, default=0.9)
    parser.add_argument("--residual-max-threshold", type=float, default=0.35)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_endpoint_consistency(
        manifest=args.manifest,
        branch_c_dir=args.branch_c_dir,
        out_dir=args.out_dir,
        endpoint_policy=args.endpoint_policy,
        full_pass_threshold=args.full_pass_threshold,
        residual_max_threshold=args.residual_max_threshold,
    )
    print(
        "ENDPOINT_CONSISTENCY_DONE "
        f"status={summary['status']} flags={summary['flag_count']} "
        f"summary={summary['files']['summary_json']}"
    )


if __name__ == "__main__":
    main()
