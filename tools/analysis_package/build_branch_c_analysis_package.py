"""Build a researcher-facing analysis package from Branch C/C2 CSV outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


WONG = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "bluish_green": "#009E73",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "gray": "#666666",
}

TIMELINE_FILES = {
    "primary": "S_NAPL_color_primary_A_realtime.csv",
    "sensitivity": "S_NAPL_color_sensitivity_B_realtime.csv",
    "comparison": "S_NAPL_color_A_B_sensitivity_comparison_realtime.csv",
    "xzone": "S_NAPL_color_xzones_primary_A_realtime.csv",
    "mask": "red_mask_timeseries_realtime.csv",
    "blob": "red_blob_summary_timeseries_realtime.csv",
}

RESIDUAL_FILES = {
    "timeseries": "residual_trapping_timeseries.csv",
    "summary_csv": "residual_trapping_summary.csv",
    "summary_json": "residual_trapping_summary.json",
}


@dataclass(frozen=True)
class PackageInputs:
    timeline_dir: Path
    residual_dir: Path
    out_dir: Path
    run_label: str


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV has no rows: {path}")
    return rows


def require_columns(rows: list[dict[str, str]], columns: list[str], source: str) -> None:
    available = set(rows[0])
    missing = [column for column in columns if column not in available]
    if missing:
        raise ValueError(f"{source} missing required columns: {', '.join(missing)}")


def number(row: dict[str, str], column: str) -> float:
    value = row.get(column, "")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def series(rows: list[dict[str, str]], column: str) -> list[float]:
    return [number(row, column) for row in rows]


def text_series(rows: list[dict[str, str]], column: str) -> list[str]:
    return [str(row.get(column, "")) for row in rows]


def finite_values(rows: list[dict[str, str]], column: str) -> list[float]:
    return [value for value in series(rows, column) if math.isfinite(value)]


def median(values: list[float]) -> float:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return math.nan
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return 0.5 * (values[mid - 1] + values[mid])


def rows_by_role(rows: list[dict[str, str]], role: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("role", "") == role]


def load_inputs(inputs: PackageInputs) -> dict[str, Any]:
    timeline = {
        key: read_csv_rows(inputs.timeline_dir / filename)
        for key, filename in TIMELINE_FILES.items()
    }
    residual = {
        key: read_csv_rows(inputs.residual_dir / filename)
        for key, filename in RESIDUAL_FILES.items()
        if filename.endswith(".csv")
    }
    summary_json_path = inputs.residual_dir / RESIDUAL_FILES["summary_json"]
    if not summary_json_path.is_file():
        raise FileNotFoundError(f"Missing required JSON: {summary_json_path}")
    summary_json = json.loads(summary_json_path.read_text(encoding="utf-8"))

    require_columns(timeline["primary"], ["label", "role", "Time_min", "S_NAPL_color"], "primary")
    require_columns(timeline["sensitivity"], ["label", "Time_min", "S_NAPL_color"], "sensitivity")
    require_columns(
        timeline["mask"],
        [
            "label",
            "role",
            "Time_min",
            "red_mask_area_fraction",
            "dnapl_water_length_px",
            "dnapl_solid_length_px",
            "solid_contact_fraction",
            "a_i_2D_proxy",
        ],
        "mask",
    )
    require_columns(
        timeline["blob"],
        ["label", "Time_min", "num_blobs", "largest_component_fraction"],
        "blob",
    )
    require_columns(timeline["xzone"], ["label", "Time_min", "S_x_inlet", "S_x_mid", "S_x_outlet"], "xzone")
    require_columns(
        residual["timeseries"],
        [
            "label",
            "role",
            "Time_min",
            "S_NAPL_color_A",
            "S_NAPL_color_B",
            "red_mask_retention_ratio",
            "L_ow_retention_ratio",
            "solid_contact_fraction",
            "a_i_2D_proxy",
            "structure_proxy",
        ],
        "residual timeseries",
    )
    return {"timeline": timeline, "residual": residual, "summary_json": summary_json}


def time_min(rows: list[dict[str, str]]) -> list[float]:
    return series(rows, "Time_min")


def save_figure(fig: plt.Figure, figures_dir: Path, stem: str) -> dict[str, str]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    png = figures_dir / f"{stem}.png"
    svg = figures_dir / f"{stem}.svg"
    fig.tight_layout()
    fig.savefig(png, dpi=220)
    fig.savefig(svg)
    plt.close(fig)
    return {"png": str(png), "svg": str(svg)}


def plot_s_color(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    primary = timeline["primary"]
    sensitivity = timeline["sensitivity"]
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    ax.plot(time_min(primary), series(primary, "S_NAPL_color"), color=WONG["blue"], lw=1.4, label="Endpoint A")
    ax.plot(
        time_min(sensitivity),
        series(sensitivity, "S_NAPL_color"),
        color=WONG["orange"],
        lw=1.2,
        alpha=0.9,
        label="Endpoint B",
    )
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("S_NAPL_color")
    ax.set_ylim(-0.03, 1.05)
    ax.grid(True, color="#dddddd", lw=0.6)
    ax.legend(frameon=False, ncols=2)
    return save_figure(fig, figures_dir, "01_S_NAPL_color_A_B_vs_realtime")


def plot_residual_zoom(residual_rows: list[dict[str, str]], figures_dir: Path) -> dict[str, str]:
    rows = rows_by_role(residual_rows, "residual")
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    ax.plot(time_min(rows), series(rows, "S_NAPL_color_A"), color=WONG["blue"], lw=1.2, label="S_NAPL_color A")
    ax.plot(time_min(rows), series(rows, "S_NAPL_color_B"), color=WONG["orange"], lw=1.2, label="S_NAPL_color B")
    ax2 = ax.twinx()
    ax2.plot(
        time_min(rows),
        series(rows, "red_mask_retention_ratio"),
        color=WONG["vermillion"],
        lw=1.0,
        alpha=0.75,
        label="red mask retention",
    )
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("S_NAPL_color")
    ax2.set_ylabel("red mask retention ratio")
    ax.grid(True, color="#dddddd", lw=0.6)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, ncols=3)
    return save_figure(fig, figures_dir, "02_residual_zoom")


def plot_mask_blob(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    mask = timeline["mask"]
    blob = timeline["blob"]
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    ax.plot(time_min(mask), series(mask, "red_mask_area_fraction"), color=WONG["vermillion"], lw=1.1, label="red mask area")
    ax.plot(
        time_min(blob),
        series(blob, "largest_component_fraction"),
        color=WONG["blue"],
        lw=1.0,
        label="largest component fraction",
    )
    ax2 = ax.twinx()
    ax2.plot(time_min(blob), series(blob, "num_blobs"), color=WONG["black"], lw=0.9, alpha=0.7, label="num blobs")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("fraction")
    ax2.set_ylabel("blob count")
    ax.grid(True, color="#dddddd", lw=0.6)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, ncols=3)
    return save_figure(fig, figures_dir, "03_red_mask_area_and_blob_morphology")


def plot_xzones(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    rows = timeline["xzone"]
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    ax.plot(time_min(rows), series(rows, "S_x_inlet"), color=WONG["blue"], lw=1.1, label="inlet")
    ax.plot(time_min(rows), series(rows, "S_x_mid"), color=WONG["bluish_green"], lw=1.1, label="mid")
    ax.plot(time_min(rows), series(rows, "S_x_outlet"), color=WONG["orange"], lw=1.1, label="outlet")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("regional S_NAPL_color")
    ax.set_ylim(-0.03, 1.05)
    ax.grid(True, color="#dddddd", lw=0.6)
    ax.legend(frameon=False, ncols=3)
    return save_figure(fig, figures_dir, "04_xzone_S_NAPL_color")


def metric_from_summary(summary_json: dict[str, Any], key: str) -> float:
    value = summary_json.get("summary_metrics", {}).get(key, math.nan)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def plot_residual_summary(summary_json: dict[str, Any], figures_dir: Path) -> dict[str, str]:
    labels = ["S color A", "red mask", "L_ow", "ganglia area"]
    values = [
        metric_from_summary(summary_json, "residual.S_color_retention_ratio_A_median"),
        metric_from_summary(summary_json, "residual.red_mask_retention_ratio_median"),
        metric_from_summary(summary_json, "residual.L_ow_retention_ratio_median"),
        metric_from_summary(summary_json, "residual.ganglia_area_fraction_median"),
    ]
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    ax.bar(labels, values, color=[WONG["blue"], WONG["vermillion"], WONG["orange"], WONG["bluish_green"]])
    ax.set_ylabel("median residual proxy")
    ax.set_ylim(0, max(1.0, max([v for v in values if math.isfinite(v)] + [0]) * 1.15))
    ax.grid(axis="y", color="#dddddd", lw=0.6)
    return save_figure(fig, figures_dir, "05_residual_trapping_summary")


def plot_interface_metrics(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    mask = timeline["mask"]
    fig, axes = plt.subplots(3, 1, figsize=(8.8, 7.0), sharex=True)
    axes[0].plot(time_min(mask), series(mask, "dnapl_water_length_px"), color=WONG["orange"], lw=1.0)
    axes[0].set_ylabel("L_ow (px)")
    axes[1].plot(time_min(mask), series(mask, "solid_contact_fraction"), color=WONG["gray"], lw=1.0)
    axes[1].set_ylabel("solid contact fraction")
    axes[2].plot(time_min(mask), series(mask, "a_i_2D_proxy"), color=WONG["bluish_green"], lw=1.0)
    axes[2].set_ylabel("a_i_2D proxy")
    axes[2].set_xlabel("Time (min)")
    for ax in axes:
        ax.grid(True, color="#dddddd", lw=0.6)
    return save_figure(fig, figures_dir, "06_interface_contact_metrics")


def create_figures(data: dict[str, Any], out_dir: Path) -> dict[str, dict[str, str]]:
    figures_dir = out_dir / "figures"
    timeline = data["timeline"]
    residual_rows = data["residual"]["timeseries"]
    summary_json = data["summary_json"]
    return {
        "S_NAPL_color_A_B": plot_s_color(timeline, figures_dir),
        "residual_zoom": plot_residual_zoom(residual_rows, figures_dir),
        "red_mask_blob_morphology": plot_mask_blob(timeline, figures_dir),
        "xzone_S_NAPL_color": plot_xzones(timeline, figures_dir),
        "residual_trapping_summary": plot_residual_summary(summary_json, figures_dir),
        "interface_contact_metrics": plot_interface_metrics(timeline, figures_dir),
    }


def git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_run_commands(inputs: PackageInputs, path: Path) -> None:
    command = (
        "python tools\\analysis_package\\build_branch_c_analysis_package.py "
        f"--timeline-dir \"{inputs.timeline_dir}\" "
        f"--residual-dir \"{inputs.residual_dir}\" "
        f"--out-dir \"{inputs.out_dir}\" "
        f"--run-label \"{inputs.run_label}\""
    )
    text = "\n".join(
        [
            "# Analysis Package Run Commands",
            "",
            "```powershell",
            command,
            "```",
            "",
            "Source CSVs are not modified. Re-run the command after regenerating the",
            "timeline or residual postprocess directories.",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def summary_line(summary_json: dict[str, Any], key: str, label: str) -> str:
    value = summary_json.get("summary_metrics", {}).get(key, "")
    return f"- {label}: `{value}`"


def write_report(inputs: PackageInputs, data: dict[str, Any], figures: dict[str, dict[str, str]], path: Path) -> None:
    summary_json = data["summary_json"]
    row_counts = summary_json.get("row_counts", {})
    lines = [
        f"# {inputs.run_label} Analysis Package",
        "",
        "This package summarizes operational Branch C color-index saturation and C2",
        "red-mask morphology/interface metrics. It is not endpoint-validated physical Sn.",
        "",
        "## Inputs",
        "",
        f"- timeline_dir: `{inputs.timeline_dir}`",
        f"- residual_dir: `{inputs.residual_dir}`",
        "",
        "## Row Counts",
        "",
        f"- primary rows: `{row_counts.get('primary_rows', '')}`",
        f"- full-role rows: `{row_counts.get('full_role_rows', '')}`",
        f"- residual-role rows: `{row_counts.get('residual_role_rows', '')}`",
        "",
        "## Key Metrics",
        "",
        summary_line(summary_json, "residual.S_NAPL_color_A_median", "Residual median S_NAPL_color A"),
        summary_line(summary_json, "residual.red_mask_area_fraction_median", "Residual median red-mask area fraction"),
        summary_line(summary_json, "residual.L_ow_retention_ratio_median", "Residual median L_ow retention ratio"),
        summary_line(summary_json, "residual.solid_contact_fraction_median", "Residual median solid contact fraction"),
        summary_line(summary_json, "residual.a_i_2D_proxy_median", "Residual median a_i_2D proxy"),
        summary_line(summary_json, "final_residual.label", "Final residual label"),
        summary_line(summary_json, "final_residual.RealTime_s", "Final residual RealTime_s"),
        "",
        "## Figures",
        "",
    ]
    for name, outputs in figures.items():
        lines.append(f"- {name}: `{outputs['png']}` / `{outputs['svg']}`")
    lines.extend(
        [
            "",
            "## Semantics",
            "",
            "- `S_NAPL_color` is an operational color-index saturation proxy.",
            "- `dnapl_water_length_px` is DNAPL-water projected interface length, L_ow.",
            "- `InterfaceArea` is a legacy alias of `dnapl_water_length_px`; it is not area.",
            "- `a_i_2D_proxy` is a 2D mask-derived proxy, not calibrated interfacial area.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_package(inputs: PackageInputs) -> dict[str, Any]:
    inputs.out_dir.mkdir(parents=True, exist_ok=True)
    data = load_inputs(inputs)
    figures = create_figures(data, inputs.out_dir)
    report_path = inputs.out_dir / "analysis_report.md"
    commands_path = inputs.out_dir / "run_commands.md"
    provenance_path = inputs.out_dir / "analysis_package_provenance.json"
    write_report(inputs, data, figures, report_path)
    write_run_commands(inputs, commands_path)

    summary_json = data["summary_json"]
    provenance = {
        "status": "pass",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_label": inputs.run_label,
        "git_head": git_head(Path(__file__).resolve().parents[2]),
        "input_paths": {
            "timeline_dir": str(inputs.timeline_dir),
            "residual_dir": str(inputs.residual_dir),
        },
        "outputs": {
            "report_md": str(report_path),
            "run_commands_md": str(commands_path),
            "figures": figures,
        },
        "row_counts": summary_json.get("row_counts", {}),
        "missing_label_counts": summary_json.get("missing_label_counts", {}),
        "summary_metrics": summary_json.get("summary_metrics", {}),
        "semantics": {
            "S_NAPL_color": "operational color-index saturation proxy; not endpoint-validated physical Sn",
            "InterfaceArea": "legacy alias of dnapl_water_length_px/L_ow, not area",
            "a_i_2D_proxy": "2D mask-derived interface-length-per-red-area proxy",
        },
    }
    write_json(provenance_path, provenance)
    provenance["outputs"]["provenance_json"] = str(provenance_path)
    write_json(provenance_path, provenance)
    return provenance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline-dir", type=Path, required=True)
    parser.add_argument("--residual-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-label", default="DNAPL Branch C full3585")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provenance = build_package(
        PackageInputs(
            timeline_dir=args.timeline_dir,
            residual_dir=args.residual_dir,
            out_dir=args.out_dir,
            run_label=args.run_label,
        )
    )
    print(f"ANALYSIS_PACKAGE {provenance['outputs']['provenance_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
