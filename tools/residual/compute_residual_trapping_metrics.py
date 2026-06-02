from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PRIMARY = "S_NAPL_color_primary_A_realtime.csv"
DEFAULT_SENSITIVITY = "S_NAPL_color_sensitivity_B_realtime.csv"
DEFAULT_COMPARISON = "S_NAPL_color_A_B_sensitivity_comparison_realtime.csv"
DEFAULT_MASK = "red_mask_timeseries_realtime.csv"
DEFAULT_BLOB = "red_blob_summary_timeseries_realtime.csv"
DEFAULT_XZONE = "S_NAPL_color_xzones_primary_A_realtime.csv"

OUTPUT_SEMANTICS = (
    "operational residual trapping proxy from Branch C color-index and "
    "C2 red-mask morphology; not physical trapped saturation"
)


@dataclass(frozen=True)
class Inputs:
    primary_csv: Path
    mask_csv: Path
    out_dir: Path
    sensitivity_csv: Path | None = None
    comparison_csv: Path | None = None
    blob_csv: Path | None = None
    xzone_csv: Path | None = None
    full_role: str = "full_napl"
    residual_role: str = "residual"


def load_csv_rows(path_value: Path) -> list[dict[str, str]]:
    if not path_value.is_file():
        raise FileNotFoundError(f"Required CSV does not exist: {path_value}")
    with path_value.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_dict_rows(path_value: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    with path_value.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path_value: Path, payload: dict[str, object]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def one_row_by_label(rows: list[dict[str, str]], source_name: str) -> dict[str, dict[str, str]]:
    by_label: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    for row in rows:
        label = row.get("label", "")
        if not label:
            raise ValueError(f"{source_name} has a row without label.")
        if label in by_label:
            duplicates.append(label)
        by_label[label] = row
    if duplicates:
        sample = ", ".join(duplicates[:5])
        raise ValueError(f"{source_name} has duplicate labels: {sample}")
    return by_label


def optional_by_label(path_value: Path | None, source_name: str) -> dict[str, dict[str, str]]:
    if path_value is None:
        return {}
    return one_row_by_label(load_csv_rows(path_value), source_name)


def parse_float(value: object) -> float:
    try:
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


def parse_int(value: object) -> int | None:
    try:
        out = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return out


def fmt(value: float | int | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        return "NaN"
    return f"{value:.12g}"


def finite_values(rows: list[dict[str, object] | dict[str, str]], field: str) -> list[float]:
    values = [parse_float(row.get(field, "")) for row in rows]
    return [value for value in values if math.isfinite(value)]


def median(values: list[float]) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def percentile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[int(pos)]
    weight = pos - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def safe_ratio(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or abs(denominator) < 1e-12:
        return math.nan
    return numerator / denominator


def read_number(row: dict[str, str] | None, field: str) -> float:
    if row is None:
        return math.nan
    return parse_float(row.get(field, ""))


def read_text(row: dict[str, str] | None, field: str) -> str:
    if row is None:
        return ""
    return row.get(field, "")


def classify_structure_proxy(num_blobs: float, largest_component_fraction: float) -> tuple[str, int, int]:
    pool_score = 0
    pool_score += int(largest_component_fraction >= 0.50)
    pool_score += int(num_blobs <= 10)
    ganglia_score = 0
    ganglia_score += int(largest_component_fraction <= 0.30)
    ganglia_score += int(num_blobs >= 25)
    if pool_score >= 2 and ganglia_score == 0:
        return "pool-like", pool_score, ganglia_score
    if ganglia_score >= 2 and pool_score == 0:
        return "ganglia-rich", pool_score, ganglia_score
    return "mixed", pool_score, ganglia_score


def fill_default_paths(args: argparse.Namespace) -> Inputs:
    if args.timeline_dir is not None:
        timeline_dir = args.timeline_dir
        primary = args.primary_csv or timeline_dir / DEFAULT_PRIMARY
        sensitivity = args.sensitivity_csv
        if sensitivity is None and (timeline_dir / DEFAULT_SENSITIVITY).is_file():
            sensitivity = timeline_dir / DEFAULT_SENSITIVITY
        comparison = args.comparison_csv
        if comparison is None and (timeline_dir / DEFAULT_COMPARISON).is_file():
            comparison = timeline_dir / DEFAULT_COMPARISON
        mask = args.mask_csv or timeline_dir / DEFAULT_MASK
        blob = args.blob_csv
        if blob is None and (timeline_dir / DEFAULT_BLOB).is_file():
            blob = timeline_dir / DEFAULT_BLOB
        xzone = args.xzone_csv
        if xzone is None and (timeline_dir / DEFAULT_XZONE).is_file():
            xzone = timeline_dir / DEFAULT_XZONE
    else:
        primary = args.primary_csv
        mask = args.mask_csv
        sensitivity = args.sensitivity_csv
        comparison = args.comparison_csv
        blob = args.blob_csv
        xzone = args.xzone_csv

    if primary is None:
        raise ValueError("Provide --primary-csv or --timeline-dir.")
    if mask is None:
        raise ValueError("Provide --mask-csv or --timeline-dir.")

    return Inputs(
        primary_csv=primary,
        sensitivity_csv=sensitivity,
        comparison_csv=comparison,
        mask_csv=mask,
        blob_csv=blob,
        xzone_csv=xzone,
        out_dir=args.out_dir,
        full_role=args.full_role,
        residual_role=args.residual_role,
    )


def build_outputs(inputs: Inputs) -> dict[str, object]:
    primary_rows = load_csv_rows(inputs.primary_csv)
    if not primary_rows:
        raise ValueError(f"Primary CSV has no rows: {inputs.primary_csv}")
    mask_rows = load_csv_rows(inputs.mask_csv)
    if not mask_rows:
        raise ValueError(f"Mask CSV has no rows: {inputs.mask_csv}")

    sensitivity_by_label = optional_by_label(inputs.sensitivity_csv, "sensitivity_csv")
    comparison_by_label = optional_by_label(inputs.comparison_csv, "comparison_csv")
    mask_by_label = one_row_by_label(mask_rows, "mask_csv")
    blob_by_label = optional_by_label(inputs.blob_csv, "blob_csv")
    xzone_by_label = optional_by_label(inputs.xzone_csv, "xzone_csv")

    primary_full_rows = [row for row in primary_rows if row.get("role", "") == inputs.full_role]
    primary_residual_rows = [row for row in primary_rows if row.get("role", "") == inputs.residual_role]
    if not primary_full_rows:
        raise ValueError(f"Primary CSV has no full-role rows: {inputs.full_role}")
    if not primary_residual_rows:
        raise ValueError(f"Primary CSV has no residual-role rows: {inputs.residual_role}")

    full_labels = {row.get("label", "") for row in primary_full_rows}
    full_mask_rows = [row for label, row in mask_by_label.items() if label in full_labels]
    full_baseline_s_a = median(finite_values(primary_full_rows, "S_NAPL_color"))
    full_baseline_red = median(finite_values(full_mask_rows, "red_mask_area_fraction"))
    full_baseline_l_ow = median(finite_values(full_mask_rows, "dnapl_water_length_px"))
    full_s_b_values = [
        read_number(sensitivity_by_label.get(row.get("label", "")), "S_NAPL_color")
        for row in primary_full_rows
        if row.get("label", "") in sensitivity_by_label
    ]
    full_baseline_s_b = median([value for value in full_s_b_values if math.isfinite(value)])

    timeseries_rows, missing = residual_timeseries_rows(
        primary_rows=primary_rows,
        sensitivity_by_label=sensitivity_by_label,
        comparison_by_label=comparison_by_label,
        mask_by_label=mask_by_label,
        blob_by_label=blob_by_label,
        xzone_by_label=xzone_by_label,
        full_baseline_s_a=full_baseline_s_a,
        full_baseline_s_b=full_baseline_s_b,
        full_baseline_red=full_baseline_red,
        full_baseline_l_ow=full_baseline_l_ow,
        residual_role=inputs.residual_role,
    )

    out_dir = inputs.out_dir
    timeseries_path = out_dir / "residual_trapping_timeseries.csv"
    summary_csv_path = out_dir / "residual_trapping_summary.csv"
    summary_json_path = out_dir / "residual_trapping_summary.json"

    timeseries_fields = residual_timeseries_fields()
    write_dict_rows(timeseries_path, timeseries_rows, timeseries_fields)
    summary_rows = summary_table_rows(
        timeseries_rows,
        full_role=inputs.full_role,
        residual_role=inputs.residual_role,
    )
    write_dict_rows(summary_csv_path, summary_rows, ["section", "metric", "value", "units", "notes"])

    status = "pass" if all(count == 0 for count in missing.values()) else "review"
    summary = {
        "status": status,
        "output_semantics": OUTPUT_SEMANTICS,
        "inputs": {
            "primary_csv": str(inputs.primary_csv),
            "sensitivity_csv": str(inputs.sensitivity_csv) if inputs.sensitivity_csv else "",
            "comparison_csv": str(inputs.comparison_csv) if inputs.comparison_csv else "",
            "mask_csv": str(inputs.mask_csv),
            "blob_csv": str(inputs.blob_csv) if inputs.blob_csv else "",
            "xzone_csv": str(inputs.xzone_csv) if inputs.xzone_csv else "",
            "full_role": inputs.full_role,
            "residual_role": inputs.residual_role,
        },
        "outputs": {
            "timeseries_csv": str(timeseries_path),
            "summary_csv": str(summary_csv_path),
            "summary_json": str(summary_json_path),
        },
        "row_counts": {
            "primary_rows": len(primary_rows),
            "timeseries_rows": len(timeseries_rows),
            "full_role_rows": len(primary_full_rows),
            "residual_role_rows": len(primary_residual_rows),
        },
        "missing_label_counts": missing,
        "baselines": {
            "full_baseline_S_NAPL_color_A_median": full_baseline_s_a,
            "full_baseline_S_NAPL_color_B_median": full_baseline_s_b,
            "full_baseline_red_mask_area_fraction_median": full_baseline_red,
            "full_baseline_dnapl_water_length_px_median": full_baseline_l_ow,
            "baseline_definition": "median over full-role rows",
        },
        "definitions": {
            "S_color_retention_ratio_A": "S_NAPL_color_A / full_baseline_S_NAPL_color_A_median",
            "red_mask_retention_ratio": "red_mask_area_fraction / full_baseline_red_mask_area_fraction_median",
            "L_ow_retention_ratio": "dnapl_water_length_px / full_baseline_dnapl_water_length_px_median",
            "num_blobs_per_red_area_fraction": "num_blobs / red_mask_area_fraction",
            "InterfaceArea": "legacy alias of dnapl_water_length_px/L_ow, not area",
            "structure_proxy": (
                "pool-like if largest_component_fraction >= 0.50 and num_blobs <= 10; "
                "ganglia-rich if largest_component_fraction <= 0.30 and num_blobs >= 25; "
                "otherwise mixed; a_i_2D_proxy is reported separately when C2 interface "
                "columns are present"
            ),
        },
        "summary_metrics": summary_metrics_dict(summary_rows),
    }
    write_json(summary_json_path, summary)
    return summary


def residual_timeseries_rows(
    primary_rows: list[dict[str, str]],
    sensitivity_by_label: dict[str, dict[str, str]],
    comparison_by_label: dict[str, dict[str, str]],
    mask_by_label: dict[str, dict[str, str]],
    blob_by_label: dict[str, dict[str, str]],
    xzone_by_label: dict[str, dict[str, str]],
    full_baseline_s_a: float,
    full_baseline_s_b: float,
    full_baseline_red: float,
    full_baseline_l_ow: float,
    residual_role: str,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    output_rows: list[dict[str, object]] = []
    missing = {"mask": 0, "sensitivity": 0, "comparison": 0, "blob": 0, "xzone": 0}
    for row in primary_rows:
        label = row.get("label", "")
        sensitivity = sensitivity_by_label.get(label)
        comparison = comparison_by_label.get(label)
        mask = mask_by_label.get(label)
        blob = blob_by_label.get(label) or mask
        xzone = xzone_by_label.get(label)

        missing["mask"] += int(mask is None)
        missing["sensitivity"] += int(bool(sensitivity_by_label) and sensitivity is None)
        missing["comparison"] += int(bool(comparison_by_label) and comparison is None)
        missing["blob"] += int(bool(blob_by_label) and label not in blob_by_label)
        missing["xzone"] += int(bool(xzone_by_label) and xzone is None)

        s_a = read_number(row, "S_NAPL_color")
        s_b = read_number(sensitivity, "S_NAPL_color")
        red_area = read_number(mask, "red_mask_area_fraction")
        num_blobs = read_number(blob, "num_blobs")
        if not math.isfinite(num_blobs):
            num_blobs = read_number(blob, "component_count")
        largest = read_number(blob, "largest_component_fraction")
        if not math.isfinite(largest):
            largest = read_number(blob, "max_blob_frac")
        l_ow_px = read_number(mask, "dnapl_water_length_px")
        solid_px = read_number(mask, "dnapl_solid_length_px")
        interface_area = read_number(mask, "InterfaceArea")
        structure, pool_score, ganglia_score = classify_structure_proxy(num_blobs, largest)
        row_status = "ok" if mask is not None else "missing_mask_label"
        role = row.get("role", "")

        output_rows.append(
            {
                "frame_index": row.get("frame_index", ""),
                "label": label,
                "role": role,
                "RealTime_s": row.get("RealTime_s", ""),
                "Time_min": row.get("Time_min", ""),
                "Interval_s": row.get("Interval_s", ""),
                "S_NAPL_color_A": fmt(s_a),
                "S_NAPL_color_B": fmt(s_b),
                "S_color_retention_ratio_A": fmt(safe_ratio(s_a, full_baseline_s_a)),
                "S_color_retention_ratio_B": fmt(safe_ratio(s_b, full_baseline_s_b)),
                "S_NAPL_color_B_minus_A": fmt(read_number(comparison, "S_NAPL_color_B_minus_A")),
                "endpoint_sensitivity_abs": fmt(read_number(comparison, "abs_endpoint_sensitivity")),
                "red_mask_area_fraction": fmt(red_area),
                "red_mask_retention_ratio": fmt(safe_ratio(red_area, full_baseline_red)),
                "red_mask_area_px": read_text(mask, "red_mask_area_px"),
                "domain_area_px": read_text(mask, "domain_area_px"),
                "dnapl_water_length_px": fmt(l_ow_px),
                "dnapl_water_length_m": fmt(read_number(mask, "dnapl_water_length_m")),
                "dnapl_solid_length_px": fmt(solid_px),
                "dnapl_solid_length_m": fmt(read_number(mask, "dnapl_solid_length_m")),
                "InterfaceArea": fmt(interface_area),
                "L_ow_retention_ratio": fmt(safe_ratio(l_ow_px, full_baseline_l_ow)),
                "solid_contact_fraction": fmt(read_number(mask, "solid_contact_fraction")),
                "a_i_2D_proxy": fmt(read_number(mask, "a_i_2D_proxy")),
                "interface_semantics": read_text(mask, "interface_semantics"),
                "num_blobs": fmt(num_blobs),
                "component_count": read_text(blob, "component_count"),
                "mean_blob_size": fmt(read_number(blob, "mean_blob_size")),
                "largest_component_fraction": fmt(largest),
                "max_blob_frac": fmt(read_number(blob, "max_blob_frac")),
                "Req_median": fmt(read_number(blob, "Req_median")),
                "Req_mean": fmt(read_number(blob, "Req_mean")),
                "Req_std": fmt(read_number(blob, "Req_std")),
                "mean_circularity": fmt(read_number(blob, "mean_circularity")),
                "n_droplets": read_text(blob, "n_droplets"),
                "n_columns": read_text(blob, "n_columns"),
                "n_clusters": read_text(blob, "n_clusters"),
                "frac_droplets": fmt(read_number(blob, "frac_droplets")),
                "frac_columns": fmt(read_number(blob, "frac_columns")),
                "frac_clusters": fmt(read_number(blob, "frac_clusters")),
                "ganglia_area_fraction": fmt(
                    read_number(blob, "frac_droplets") + read_number(blob, "frac_columns")
                ),
                "cluster_area_fraction": fmt(read_number(blob, "frac_clusters")),
                "num_blobs_per_red_area_fraction": fmt(safe_ratio(num_blobs, red_area)),
                "structure_proxy": structure,
                "structure_proxy_pool_score": pool_score,
                "structure_proxy_ganglia_score": ganglia_score,
                "structure_proxy_scope": "residual_proxy" if role == residual_role else "non_residual_context",
                "S_x_inlet": fmt(read_number(xzone, "S_x_inlet")),
                "S_x_mid": fmt(read_number(xzone, "S_x_mid")),
                "S_x_outlet": fmt(read_number(xzone, "S_x_outlet")),
                "S_x_inlet_outlet_asymmetry": fmt(read_number(xzone, "S_x_inlet_outlet_asymmetry")),
                "active_bin_fraction_ge_0p2": fmt(read_number(xzone, "active_bin_fraction_ge_0p2")),
                "active_bin_fraction_ge_0p5": fmt(read_number(xzone, "active_bin_fraction_ge_0p5")),
                "napl_extent_fraction_ge_0p2": fmt(read_number(xzone, "napl_extent_fraction_ge_0p2")),
                "napl_extent_fraction_ge_0p5": fmt(read_number(xzone, "napl_extent_fraction_ge_0p5")),
                "residual_metric_status": row_status,
                "output_semantics": OUTPUT_SEMANTICS,
            }
        )
    return output_rows, missing


def residual_timeseries_fields() -> list[str]:
    return [
        "frame_index",
        "label",
        "role",
        "RealTime_s",
        "Time_min",
        "Interval_s",
        "S_NAPL_color_A",
        "S_NAPL_color_B",
        "S_color_retention_ratio_A",
        "S_color_retention_ratio_B",
        "S_NAPL_color_B_minus_A",
        "endpoint_sensitivity_abs",
        "red_mask_area_fraction",
        "red_mask_retention_ratio",
        "red_mask_area_px",
        "domain_area_px",
        "dnapl_water_length_px",
        "dnapl_water_length_m",
        "dnapl_solid_length_px",
        "dnapl_solid_length_m",
        "InterfaceArea",
        "L_ow_retention_ratio",
        "solid_contact_fraction",
        "a_i_2D_proxy",
        "interface_semantics",
        "num_blobs",
        "component_count",
        "mean_blob_size",
        "largest_component_fraction",
        "max_blob_frac",
        "Req_median",
        "Req_mean",
        "Req_std",
        "mean_circularity",
        "n_droplets",
        "n_columns",
        "n_clusters",
        "frac_droplets",
        "frac_columns",
        "frac_clusters",
        "ganglia_area_fraction",
        "cluster_area_fraction",
        "num_blobs_per_red_area_fraction",
        "structure_proxy",
        "structure_proxy_pool_score",
        "structure_proxy_ganglia_score",
        "structure_proxy_scope",
        "S_x_inlet",
        "S_x_mid",
        "S_x_outlet",
        "S_x_inlet_outlet_asymmetry",
        "active_bin_fraction_ge_0p2",
        "active_bin_fraction_ge_0p5",
        "napl_extent_fraction_ge_0p2",
        "napl_extent_fraction_ge_0p5",
        "residual_metric_status",
        "output_semantics",
    ]


def summary_table_rows(
    timeseries_rows: list[dict[str, object]],
    full_role: str,
    residual_role: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    full_rows = [row for row in timeseries_rows if row.get("role", "") == full_role]
    residual_rows = [row for row in timeseries_rows if row.get("role", "") == residual_role]

    add_summary(rows, "counts", "timeseries_rows", len(timeseries_rows), "rows", "")
    add_summary(rows, "counts", "full_role_rows", len(full_rows), "rows", full_role)
    add_summary(rows, "counts", "residual_role_rows", len(residual_rows), "rows", residual_role)
    for field in (
        "S_NAPL_color_A",
        "S_NAPL_color_B",
        "red_mask_area_fraction",
        "S_color_retention_ratio_A",
        "S_color_retention_ratio_B",
        "red_mask_retention_ratio",
        "dnapl_water_length_px",
        "dnapl_solid_length_px",
        "InterfaceArea",
        "L_ow_retention_ratio",
        "solid_contact_fraction",
        "a_i_2D_proxy",
        "endpoint_sensitivity_abs",
        "num_blobs",
        "largest_component_fraction",
        "num_blobs_per_red_area_fraction",
        "frac_droplets",
        "frac_columns",
        "frac_clusters",
        "ganglia_area_fraction",
        "S_x_inlet",
        "S_x_mid",
        "S_x_outlet",
    ):
        add_distribution(rows, "full", field, finite_values(full_rows, field), full_role)
        add_distribution(rows, "residual", field, finite_values(residual_rows, field), residual_role)

    final = residual_rows[-1] if residual_rows else None
    if final is not None:
        for field in (
            "label",
            "RealTime_s",
            "S_NAPL_color_A",
            "S_NAPL_color_B",
            "red_mask_area_fraction",
            "dnapl_water_length_px",
            "dnapl_solid_length_px",
            "S_color_retention_ratio_A",
            "red_mask_retention_ratio",
            "L_ow_retention_ratio",
            "solid_contact_fraction",
            "a_i_2D_proxy",
            "num_blobs",
            "largest_component_fraction",
            "structure_proxy",
            "S_x_inlet",
            "S_x_mid",
            "S_x_outlet",
        ):
            add_summary(rows, "final_residual", field, final.get(field, ""), "", "last residual-role row")

    structure_counts: dict[str, int] = {}
    for row in residual_rows:
        key = str(row.get("structure_proxy", ""))
        structure_counts[key] = structure_counts.get(key, 0) + 1
    for key, count in sorted(structure_counts.items()):
        add_summary(rows, "residual_structure_proxy_counts", key, count, "rows", "")
    return rows


def add_distribution(rows: list[dict[str, str]], section: str, metric: str, values: list[float], notes: str) -> None:
    if not values:
        for suffix in ("p05", "median", "p95"):
            add_summary(rows, section, f"{metric}_{suffix}", math.nan, "", notes)
        return
    add_summary(rows, section, f"{metric}_p05", percentile(values, 0.05), "", notes)
    add_summary(rows, section, f"{metric}_median", median(values), "", notes)
    add_summary(rows, section, f"{metric}_p95", percentile(values, 0.95), "", notes)


def add_summary(
    rows: list[dict[str, str]],
    section: str,
    metric: str,
    value: float | int | str | None,
    units: str,
    notes: str,
) -> None:
    rows.append(
        {
            "section": section,
            "metric": metric,
            "value": fmt(value),
            "units": units,
            "notes": notes,
        }
    )


def summary_metrics_dict(summary_rows: list[dict[str, str]]) -> dict[str, str]:
    return {f"{row['section']}.{row['metric']}": row["value"] for row in summary_rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute operational residual trapping proxy metrics from realtime "
            "Branch C S_NAPL_color and C2 red-mask morphology CSVs."
        )
    )
    parser.add_argument("--timeline-dir", type=Path, default=None)
    parser.add_argument("--primary-csv", type=Path, default=None)
    parser.add_argument("--sensitivity-csv", type=Path, default=None)
    parser.add_argument("--comparison-csv", type=Path, default=None)
    parser.add_argument("--mask-csv", type=Path, default=None)
    parser.add_argument("--blob-csv", type=Path, default=None)
    parser.add_argument("--xzone-csv", type=Path, default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--full-role", default="full_napl")
    parser.add_argument("--residual-role", default="residual")
    return parser.parse_args()


def main() -> None:
    inputs = fill_default_paths(parse_args())
    summary = build_outputs(inputs)
    print(f"RESIDUAL_TRAPPING_TIMESERIES {summary['outputs']['timeseries_csv']}")
    print(f"RESIDUAL_TRAPPING_SUMMARY {summary['outputs']['summary_json']}")


if __name__ == "__main__":
    main()
