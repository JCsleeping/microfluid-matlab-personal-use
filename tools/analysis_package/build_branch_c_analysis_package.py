"""Build a researcher-facing analysis package from Branch C/C2 CSV outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import warnings
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
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "gray": "#666666",
}

FIGURE_STYLE = "nature_timeseries_v1"
MM_PER_INCH = 25.4
WIDE_SIZE = (180 / MM_PER_INCH, 82 / MM_PER_INCH)
TALL_SIZE = (180 / MM_PER_INCH, 132 / MM_PER_INCH)
BAR_SIZE = (89 / MM_PER_INCH, 68 / MM_PER_INCH)
LINEWIDTH = 1.5
MARKER = "o"
MARKER_SIZE = 3.6

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


def percentile(values: list[float], q: float) -> float:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return math.nan
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * float(q)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


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


def format_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number_value):
        return "NaN"
    return f"{number_value:.12g}"


def time_range(rows: list[dict[str, str]]) -> tuple[float, float, float]:
    values = finite_values(rows, "Time_min")
    if not values:
        return math.nan, math.nan, math.nan
    return min(values), max(values), max(values) - min(values)


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


def configure_nature_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.labelsize": 9.5,
            "axes.titlesize": 8.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.0,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
            "lines.solid_capstyle": "round",
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.size": 1.8,
            "ytick.minor.size": 1.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "xtick.minor.width": 0.6,
            "ytick.minor.width": 0.6,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def style_axes(ax: plt.Axes, *, keep_right: bool = False, grid_axis: str = "both") -> plt.Axes:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(keep_right)
    for side in ("bottom", "left"):
        ax.spines[side].set_linewidth(0.9)
        ax.spines[side].set_color("#2B2B2B")
    if keep_right:
        ax.spines["right"].set_linewidth(0.9)
        ax.spines["right"].set_color("#2B2B2B")
    ax.tick_params(axis="both", which="major", direction="out", colors="#2B2B2B", length=4.0, width=0.9)
    ax.tick_params(axis="both", which="minor", direction="out", colors="#2B2B2B", length=2.2, width=0.6)
    ax.minorticks_on()
    ax.grid(True, which="major", axis=grid_axis, color="#E4E4E4", linewidth=0.55, alpha=0.7)
    ax.set_axisbelow(True)
    return ax


def markevery(rows: list[dict[str, str]]) -> int:
    return max(1, len(rows) // 24)


def plot_line(
    ax: plt.Axes,
    rows: list[dict[str, str]],
    column: str,
    label: str,
    color: str,
    *,
    linewidth: float = LINEWIDTH,
    alpha: float = 1.0,
) -> None:
    ax.plot(
        time_min(rows),
        series(rows, column),
        color=color,
        linewidth=linewidth,
        alpha=alpha,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=color,
        markeredgewidth=0.9,
        markevery=markevery(rows),
        label=label,
    )


def tight_layout(fig: plt.Figure) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Tight layout not applied.*", category=UserWarning)
        fig.tight_layout()


def save_figure(fig: plt.Figure, figures_dir: Path, stem: str) -> dict[str, str]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    png = figures_dir / f"{stem}.png"
    svg = figures_dir / f"{stem}.svg"
    tight_layout(fig)
    fig.savefig(png, dpi=600, facecolor="white")
    fig.savefig(svg, facecolor="white")
    plt.close(fig)
    return {"png": str(png), "svg": str(svg)}


def plot_s_color(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    primary = timeline["primary"]
    sensitivity = timeline["sensitivity"]
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    plot_line(ax, primary, "S_NAPL_color", "Endpoint A", WONG["blue"])
    plot_line(ax, sensitivity, "S_NAPL_color", "Endpoint B", WONG["orange"], linewidth=1.3, alpha=0.9)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel(r"$S_{\mathrm{NAPL,color}}$")
    ax.set_ylim(-0.03, 1.05)
    ax.legend(frameon=False, ncols=2)
    style_axes(ax)
    return save_figure(fig, figures_dir, "01_S_NAPL_color_A_B_vs_realtime")


def plot_residual_zoom(residual_rows: list[dict[str, str]], figures_dir: Path) -> dict[str, str]:
    rows = rows_by_role(residual_rows, "residual")
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    plot_line(ax, rows, "S_NAPL_color_A", "S_NAPL_color A", WONG["blue"], linewidth=1.3)
    plot_line(ax, rows, "S_NAPL_color_B", "S_NAPL_color B", WONG["orange"], linewidth=1.3)
    ax2 = ax.twinx()
    plot_line(ax2, rows, "red_mask_retention_ratio", "red mask retention", WONG["vermillion"], linewidth=1.1, alpha=0.8)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel(r"$S_{\mathrm{NAPL,color}}$")
    ax2.set_ylabel("red mask retention ratio")
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, ncols=3)
    style_axes(ax)
    style_axes(ax2, keep_right=True, grid_axis="y")
    return save_figure(fig, figures_dir, "02_residual_zoom")


def plot_mask_blob(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    mask = timeline["mask"]
    blob = timeline["blob"]
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    plot_line(ax, mask, "red_mask_area_fraction", "red mask area", WONG["vermillion"], linewidth=1.2)
    plot_line(ax, blob, "largest_component_fraction", "largest component fraction", WONG["blue"], linewidth=1.2)
    ax2 = ax.twinx()
    plot_line(ax2, blob, "num_blobs", "num blobs", WONG["black"], linewidth=1.0, alpha=0.75)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("fraction")
    ax2.set_ylabel("blob count")
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, ncols=3)
    style_axes(ax)
    style_axes(ax2, keep_right=True, grid_axis="y")
    return save_figure(fig, figures_dir, "03_red_mask_area_and_blob_morphology")


def plot_xzones(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    rows = timeline["xzone"]
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    plot_line(ax, rows, "S_x_inlet", "inlet", WONG["blue"], linewidth=1.2)
    plot_line(ax, rows, "S_x_mid", "mid", WONG["bluish_green"], linewidth=1.2)
    plot_line(ax, rows, "S_x_outlet", "outlet", WONG["orange"], linewidth=1.2)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel(r"regional $S_{\mathrm{NAPL,color}}$")
    ax.set_ylim(-0.03, 1.05)
    ax.legend(frameon=False, ncols=3)
    style_axes(ax)
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
    fig, ax = plt.subplots(figsize=BAR_SIZE)
    ax.bar(labels, values, color=[WONG["blue"], WONG["vermillion"], WONG["orange"], WONG["bluish_green"]])
    ax.set_ylabel("median residual proxy")
    ax.set_ylim(0, max(1.0, max([v for v in values if math.isfinite(v)] + [0]) * 1.15))
    style_axes(ax, grid_axis="y")
    return save_figure(fig, figures_dir, "05_residual_trapping_summary")


def plot_interface_metrics(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    mask = timeline["mask"]
    fig, axes = plt.subplots(3, 1, figsize=TALL_SIZE, sharex=True)
    plot_line(axes[0], mask, "dnapl_water_length_px", r"$L_{ow}$", WONG["orange"], linewidth=1.1)
    axes[0].set_ylabel(r"$L_{ow}$ (px)")
    plot_line(axes[1], mask, "solid_contact_fraction", "solid contact", WONG["gray"], linewidth=1.1)
    axes[1].set_ylabel("solid contact fraction")
    plot_line(axes[2], mask, "a_i_2D_proxy", r"$a_i^{2D}$ proxy", WONG["bluish_green"], linewidth=1.1)
    axes[2].set_ylabel(r"$a_i^{2D}$ proxy")
    axes[2].set_xlabel("Time (min)")
    for ax in axes:
        style_axes(ax)
    return save_figure(fig, figures_dir, "06_interface_contact_metrics")


def plot_sensitivity_extent(timeline: dict[str, list[dict[str, str]]], figures_dir: Path) -> dict[str, str]:
    comparison = timeline["comparison"]
    xzone = timeline["xzone"]
    fig, axes = plt.subplots(2, 1, figsize=(180 / MM_PER_INCH, 106 / MM_PER_INCH), sharex=True)
    plot_line(axes[0], comparison, "abs_endpoint_sensitivity", "|B - A|", WONG["reddish_purple"], linewidth=1.2)
    axes[0].set_ylabel("endpoint sensitivity")
    for column, label, color in (
        ("active_bin_fraction_ge_0p2", "active bins >= 0.2", WONG["blue"]),
        ("active_bin_fraction_ge_0p5", "active bins >= 0.5", WONG["orange"]),
        ("napl_extent_fraction_ge_0p2", "extent >= 0.2", WONG["bluish_green"]),
        ("napl_extent_fraction_ge_0p5", "extent >= 0.5", WONG["vermillion"]),
    ):
        if column in xzone[0]:
            plot_line(axes[1], xzone, column, label, color, linewidth=1.1)
    axes[1].set_xlabel("Time (min)")
    axes[1].set_ylabel("x-bin fraction")
    for ax in axes:
        ax.legend(frameon=False, ncols=2)
        style_axes(ax)
    return save_figure(fig, figures_dir, "07_endpoint_sensitivity_and_x_extent")


def create_figures(data: dict[str, Any], out_dir: Path) -> dict[str, dict[str, str]]:
    configure_nature_style()
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
        "endpoint_sensitivity_and_x_extent": plot_sensitivity_extent(timeline, figures_dir),
    }


def add_parameter(
    rows: list[dict[str, str]],
    section: str,
    parameter: str,
    value: object,
    units: str = "",
    notes: str = "",
) -> None:
    rows.append(
        {
            "section": section,
            "parameter": parameter,
            "value": format_value(value),
            "units": units,
            "notes": notes,
        }
    )


def median_column(rows: list[dict[str, str]], column: str) -> float:
    return median(finite_values(rows, column))


def max_column(rows: list[dict[str, str]], column: str) -> float:
    values = finite_values(rows, column)
    return max(values) if values else math.nan


def first_time_where(rows: list[dict[str, str]], column: str, threshold: float) -> float:
    candidates = []
    for row in rows:
        value = number(row, column)
        time_value = number(row, "Time_min")
        if math.isfinite(value) and math.isfinite(time_value) and value >= threshold:
            candidates.append(time_value)
    return min(candidates) if candidates else math.nan


def final_column(rows: list[dict[str, str]], column: str) -> float:
    finite_rows = [row for row in rows if math.isfinite(number(row, "Time_min"))]
    if not finite_rows:
        return math.nan
    final_row = max(finite_rows, key=lambda row: number(row, "Time_min"))
    return number(final_row, column)


def retention_ratio(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator == 0:
        return math.nan
    return numerator / denominator


def summary_raw(summary_json: dict[str, Any], key: str) -> object:
    return summary_json.get("summary_metrics", {}).get(key, "")


def compute_parameter_summary(data: dict[str, Any]) -> list[dict[str, str]]:
    timeline = data["timeline"]
    summary_json = data["summary_json"]
    primary = timeline["primary"]
    comparison = timeline["comparison"]
    xzone = timeline["xzone"]
    mask = timeline["mask"]
    blob = timeline["blob"]

    full_primary = rows_by_role(primary, "full_napl")
    residual_primary = rows_by_role(primary, "residual")
    full_comparison = rows_by_role(comparison, "full_napl")
    residual_comparison = rows_by_role(comparison, "residual")
    full_xzone = rows_by_role(xzone, "full_napl")
    residual_xzone = rows_by_role(xzone, "residual")
    full_mask = rows_by_role(mask, "full_napl")
    residual_mask = rows_by_role(mask, "residual")
    full_blob = rows_by_role(blob, "full_napl")
    residual_blob = rows_by_role(blob, "residual")

    rows: list[dict[str, str]] = []
    start_min, end_min, duration_min = time_range(primary)
    residual_start_min, _residual_end_min, _residual_duration_min = time_range(residual_primary)
    add_parameter(rows, "run", "total_rows", len(primary), "frames", "primary Branch C rows")
    add_parameter(rows, "run", "time_start_min", start_min, "min")
    add_parameter(rows, "run", "time_end_min", end_min, "min")
    add_parameter(rows, "run", "duration_min", duration_min, "min")

    for role, role_rows in (("full_napl", full_primary), ("residual", residual_primary)):
        role_start, role_end, role_duration = time_range(role_rows)
        add_parameter(rows, "phase", f"{role}_rows", len(role_rows), "frames")
        add_parameter(rows, "phase", f"{role}_start_min", role_start, "min")
        add_parameter(rows, "phase", f"{role}_end_min", role_end, "min")
        add_parameter(rows, "phase", f"{role}_duration_min", role_duration, "min")

    full_s = median_column(full_primary, "S_NAPL_color")
    residual_s = median_column(residual_primary, "S_NAPL_color")
    add_parameter(rows, "saturation", "full_S_NAPL_color_A_median", full_s, "unitless")
    add_parameter(rows, "saturation", "residual_S_NAPL_color_A_median", residual_s, "unitless")
    add_parameter(rows, "saturation", "residual_to_full_S_color_ratio", retention_ratio(residual_s, full_s), "unitless")
    add_parameter(rows, "saturation", "final_residual_S_NAPL_color_A", summary_raw(summary_json, "final_residual.S_NAPL_color_A"), "unitless")

    for name, role_rows in (("all", comparison), ("full", full_comparison), ("residual", residual_comparison)):
        values = finite_values(role_rows, "abs_endpoint_sensitivity")
        add_parameter(rows, "endpoint_sensitivity", f"{name}_median_abs_B_minus_A", median(values), "unitless")
        add_parameter(rows, "endpoint_sensitivity", f"{name}_p95_abs_B_minus_A", percentile(values, 0.95), "unitless")
        add_parameter(rows, "endpoint_sensitivity", f"{name}_max_abs_B_minus_A", max(values) if values else math.nan, "unitless")

    full_red = median_column(full_mask, "red_mask_area_fraction")
    residual_red = median_column(residual_mask, "red_mask_area_fraction")
    add_parameter(rows, "segmentation", "full_red_mask_area_fraction_median", full_red, "fraction")
    add_parameter(rows, "segmentation", "residual_red_mask_area_fraction_median", residual_red, "fraction")
    add_parameter(rows, "segmentation", "residual_to_full_red_mask_area_ratio", retention_ratio(residual_red, full_red), "unitless")
    add_parameter(rows, "segmentation", "final_residual_red_mask_area_fraction", summary_raw(summary_json, "final_residual.red_mask_area_fraction"), "fraction")

    full_low = median_column(full_mask, "dnapl_water_length_px")
    residual_low = median_column(residual_mask, "dnapl_water_length_px")
    full_solid_fraction = median_column(full_mask, "solid_contact_fraction")
    residual_solid_fraction = median_column(residual_mask, "solid_contact_fraction")
    add_parameter(rows, "interface", "full_L_ow_median_px", full_low, "px")
    add_parameter(rows, "interface", "residual_L_ow_median_px", residual_low, "px")
    add_parameter(rows, "interface", "residual_to_full_L_ow_ratio", retention_ratio(residual_low, full_low), "unitless")
    add_parameter(rows, "interface", "residual_L_ow_retention_ratio_median", summary_raw(summary_json, "residual.L_ow_retention_ratio_median"), "unitless")
    add_parameter(rows, "interface", "full_solid_contact_fraction_median", full_solid_fraction, "fraction")
    add_parameter(rows, "interface", "residual_solid_contact_fraction_median", residual_solid_fraction, "fraction")
    add_parameter(rows, "interface", "residual_minus_full_solid_contact_fraction", residual_solid_fraction - full_solid_fraction, "fraction")
    add_parameter(rows, "interface", "residual_a_i_2D_proxy_median", median_column(residual_mask, "a_i_2D_proxy"), "px_per_px2")

    add_parameter(rows, "morphology", "full_num_blobs_median", median_column(full_blob, "num_blobs"), "count")
    add_parameter(rows, "morphology", "residual_num_blobs_median", median_column(residual_blob, "num_blobs"), "count")
    add_parameter(rows, "morphology", "residual_largest_component_fraction_median", median_column(residual_blob, "largest_component_fraction"), "fraction")
    add_parameter(rows, "morphology", "residual_frac_droplets_median", median_column(residual_blob, "frac_droplets"), "fraction")
    add_parameter(rows, "morphology", "residual_frac_columns_median", median_column(residual_blob, "frac_columns"), "fraction")
    add_parameter(rows, "morphology", "residual_frac_clusters_median", median_column(residual_blob, "frac_clusters"), "fraction")

    add_parameter(rows, "xzone", "residual_S_x_inlet_median", median_column(residual_xzone, "S_x_inlet"), "unitless")
    add_parameter(rows, "xzone", "residual_S_x_mid_median", median_column(residual_xzone, "S_x_mid"), "unitless")
    add_parameter(rows, "xzone", "residual_S_x_outlet_median", median_column(residual_xzone, "S_x_outlet"), "unitless")
    add_parameter(rows, "xzone", "residual_extent_fraction_ge_0p2_median", median_column(residual_xzone, "napl_extent_fraction_ge_0p2"), "fraction")
    add_parameter(rows, "xzone", "residual_active_bin_fraction_ge_0p2_median", median_column(residual_xzone, "active_bin_fraction_ge_0p2"), "fraction")
    add_parameter(rows, "xzone", "final_napl_extent_fraction_ge_0p2", final_column(xzone, "napl_extent_fraction_ge_0p2"), "fraction")
    add_parameter(rows, "front_proxy", "first_outlet_zone_ge_0p2_time_min", first_time_where(xzone, "outlet_zone_ge_0p2", 1.0), "min", "first frame with outlet-zone proxy active")
    add_parameter(rows, "front_proxy", "first_outlet_zone_ge_0p5_time_min", first_time_where(xzone, "outlet_zone_ge_0p5", 1.0), "min", "first frame with high outlet-zone proxy active")
    residual_first_02 = first_time_where(residual_xzone, "outlet_zone_ge_0p2", 1.0)
    residual_first_05 = first_time_where(residual_xzone, "outlet_zone_ge_0p5", 1.0)
    add_parameter(rows, "front_proxy", "residual_first_outlet_zone_ge_0p2_time_min", residual_first_02, "min", "first residual-role frame with outlet-zone proxy active")
    add_parameter(rows, "front_proxy", "residual_first_outlet_zone_ge_0p5_time_min", residual_first_05, "min", "first residual-role frame with high outlet-zone proxy active")
    add_parameter(rows, "front_proxy", "residual_first_outlet_zone_ge_0p2_since_residual_start_min", residual_first_02 - residual_start_min, "min")
    add_parameter(rows, "front_proxy", "residual_first_outlet_zone_ge_0p5_since_residual_start_min", residual_first_05 - residual_start_min, "min")
    add_parameter(rows, "front_proxy", "max_napl_extent_fraction_ge_0p2", max_column(xzone, "napl_extent_fraction_ge_0p2"), "fraction")

    add_parameter(rows, "semantics", "figure_style", FIGURE_STYLE, "", "matched to visualization/plot_timeseries.py Nature-style defaults")
    return rows


def write_parameter_summary(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "parameter", "value", "units", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def parameter_rows_to_dict(rows: list[dict[str, str]]) -> dict[str, str]:
    return {f"{row['section']}.{row['parameter']}": row["value"] for row in rows}


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


def write_report(
    inputs: PackageInputs,
    data: dict[str, Any],
    figures: dict[str, dict[str, str]],
    parameter_rows: list[dict[str, str]],
    parameter_summary_path: Path,
    path: Path,
) -> None:
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
        "## Derived Parameters",
        "",
        f"Full parameter table: `{parameter_summary_path}`",
        "",
        "| section | parameter | value | units |",
        "|---|---|---:|---|",
    ]
    report_sections = {
        "run",
        "phase",
        "saturation",
        "endpoint_sensitivity",
        "segmentation",
        "interface",
        "morphology",
        "xzone",
        "front_proxy",
    }
    for row in parameter_rows:
        if row["section"] in report_sections:
            lines.append(
                f"| {row['section']} | {row['parameter']} | `{row['value']}` | {row['units']} |"
            )
    lines.extend(
        [
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
    )
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
    parameter_rows = compute_parameter_summary(data)
    report_path = inputs.out_dir / "analysis_report.md"
    commands_path = inputs.out_dir / "run_commands.md"
    parameter_summary_path = inputs.out_dir / "analysis_parameter_summary.csv"
    provenance_path = inputs.out_dir / "analysis_package_provenance.json"
    write_parameter_summary(parameter_summary_path, parameter_rows)
    write_report(inputs, data, figures, parameter_rows, parameter_summary_path, report_path)
    write_run_commands(inputs, commands_path)

    summary_json = data["summary_json"]
    provenance = {
        "status": "pass",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_label": inputs.run_label,
        "git_head": git_head(Path(__file__).resolve().parents[2]),
        "figure_style": FIGURE_STYLE,
        "input_paths": {
            "timeline_dir": str(inputs.timeline_dir),
            "residual_dir": str(inputs.residual_dir),
        },
        "outputs": {
            "report_md": str(report_path),
            "run_commands_md": str(commands_path),
            "parameter_summary_csv": str(parameter_summary_path),
            "figures": figures,
        },
        "row_counts": summary_json.get("row_counts", {}),
        "missing_label_counts": summary_json.get("missing_label_counts", {}),
        "summary_metrics": summary_json.get("summary_metrics", {}),
        "derived_parameters": parameter_rows_to_dict(parameter_rows),
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
