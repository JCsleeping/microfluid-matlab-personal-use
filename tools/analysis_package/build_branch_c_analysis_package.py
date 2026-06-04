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
ANALYSIS_POLICY_VERSION = "branch_c_proxy_alignment_v3_recovered_metadata_gate"
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

MASK_ANALYSIS_FILES = {
    "timeseries": "mask_stack_analysis_timeseries.csv",
    "phase_timeseries": "phase_mask_timeseries.csv",
    "blob_morphology": "blob_morphology_timeseries.csv",
    "toa_x": "toa_x_summary.csv",
    "summary_json": "mask_stack_analysis_summary.json",
}


@dataclass(frozen=True)
class PackageInputs:
    timeline_dir: Path
    residual_dir: Path
    out_dir: Path
    run_label: str
    physical_metadata_path: Path | None = None
    mask_analysis_dir: Path | None = None


POSITIVE_METADATA_FIELDS = {
    "pixel_size_um",
    "native_pixel_size_um",
    "processing_pixel_size_um",
    "processing_scale_factor",
    "flow_rate_ul_min",
    "pore_volume_ul",
    "channel_depth_um",
    "channel_width_um",
    "viscosity_Pa_s",
    "IFT_mN_m",
    "temperature_C",
    "diffusion_coefficient_m2_s",
}


def positive_number(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) and result > 0 else math.nan


def metadata_is_trusted(raw: dict[str, Any]) -> bool:
    status = str(raw.get("metadata_status", raw.get("status", ""))).strip().lower()
    return bool(raw.get("trusted", False)) or status in {
        "trusted",
        "calibrated",
        "validated",
        "physical_metadata_validated",
    }


def normalize_physical_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "status": "not_provided",
            "trusted": False,
            "path": "",
            "raw": {},
            "values": {},
            "derived": {},
            "warnings": [],
        }
    if not path.is_file():
        raise FileNotFoundError(f"Missing physical metadata manifest: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if "physical_metadata" in raw and isinstance(raw["physical_metadata"], dict):
        raw = raw["physical_metadata"]
    if not isinstance(raw, dict):
        raise ValueError(f"Physical metadata manifest must be a JSON object: {path}")

    trusted = metadata_is_trusted(raw)
    values = {key: positive_number(raw.get(key)) for key in POSITIVE_METADATA_FIELDS}
    warnings: list[str] = []

    scale = values["processing_scale_factor"]
    if not math.isfinite(scale):
        scale = positive_number(raw.get("upscale_factor"))
        values["processing_scale_factor"] = scale
    if math.isfinite(scale) and abs(scale - round(scale)) > 1.0e-9:
        warnings.append("processing_scale_factor should be an integer processing-grid scale.")

    pixel_size_um = values["pixel_size_um"]
    if not math.isfinite(pixel_size_um):
        pixel_size_um = values["native_pixel_size_um"]
    if (
        not math.isfinite(pixel_size_um)
        and math.isfinite(values["processing_pixel_size_um"])
        and math.isfinite(scale)
    ):
        pixel_size_um = values["processing_pixel_size_um"] * scale
    values["pixel_size_um"] = pixel_size_um
    values["native_pixel_size_um"] = pixel_size_um
    if not math.isfinite(values["processing_pixel_size_um"]) and math.isfinite(pixel_size_um) and math.isfinite(scale):
        values["processing_pixel_size_um"] = pixel_size_um / scale

    flow_rate = values["flow_rate_ul_min"]
    pore_volume = values["pore_volume_ul"]
    width_um = values["channel_width_um"]
    depth_um = values["channel_depth_um"]
    viscosity = values["viscosity_Pa_s"]
    ift_mn_m = values["IFT_mN_m"]

    velocity = math.nan
    if math.isfinite(flow_rate) and math.isfinite(width_um) and math.isfinite(depth_um):
        flow_m3_s = flow_rate * 1.0e-9 / 60.0
        area_m2 = width_um * 1.0e-6 * depth_um * 1.0e-6
        velocity = flow_m3_s / area_m2 if area_m2 > 0 else math.nan

    capillary_number = math.nan
    if math.isfinite(velocity) and math.isfinite(viscosity) and math.isfinite(ift_mn_m):
        gamma_n_m = ift_mn_m * 1.0e-3
        capillary_number = viscosity * velocity / gamma_n_m if gamma_n_m > 0 else math.nan

    processing_pixel_size_um = values["processing_pixel_size_um"]
    derived = {
        "pixel_size_m": pixel_size_um * 1.0e-6 if trusted and math.isfinite(pixel_size_um) else math.nan,
        "processing_pixel_size_m": processing_pixel_size_um * 1.0e-6
        if trusted and math.isfinite(processing_pixel_size_um)
        else math.nan,
        "pv_ready": bool(trusted and math.isfinite(flow_rate) and math.isfinite(pore_volume)),
        "velocity_m_per_s": velocity if trusted else math.nan,
        "capillary_number": capillary_number if trusted else math.nan,
    }
    return {
        "status": "trusted" if trusted else "provided_untrusted",
        "trusted": trusted,
        "path": str(path),
        "raw": raw,
        "values": {
            key: (value if math.isfinite(value) else None)
            for key, value in values.items()
        },
        "derived": {
            key: (value if isinstance(value, bool) or math.isfinite(value) else None)
            for key, value in derived.items()
        },
        "strings": {
            "surfactant_name": str(raw.get("surfactant_name", "")),
            "surfactant_concentration": str(raw.get("surfactant_concentration", "")),
            "notes": str(raw.get("notes", "")),
        },
        "warnings": warnings,
    }


def metadata_number(metadata: dict[str, Any], section: str, key: str) -> float:
    value = metadata.get(section, {}).get(key)
    return positive_number(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV has no rows: {path}")
    return rows


def read_optional_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    return read_csv_rows(path)


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
    if isinstance(value, bool):
        return "true" if value else "false"
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


def load_mask_analysis(mask_analysis_dir: Path | None) -> dict[str, Any]:
    if mask_analysis_dir is None:
        return {
            "dir": "",
            "timeseries": [],
            "blob_morphology": [],
            "toa_x": [],
            "summary_json": {},
        }
    return {
        "dir": str(mask_analysis_dir),
        "timeseries": read_optional_csv_rows(mask_analysis_dir / MASK_ANALYSIS_FILES["timeseries"]),
        "phase_timeseries": read_optional_csv_rows(mask_analysis_dir / MASK_ANALYSIS_FILES["phase_timeseries"]),
        "blob_morphology": read_optional_csv_rows(mask_analysis_dir / MASK_ANALYSIS_FILES["blob_morphology"]),
        "toa_x": read_optional_csv_rows(mask_analysis_dir / MASK_ANALYSIS_FILES["toa_x"]),
        "summary_json": read_optional_json(mask_analysis_dir / MASK_ANALYSIS_FILES["summary_json"]),
    }


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
    physical_metadata = normalize_physical_metadata(inputs.physical_metadata_path)
    return {
        "timeline": timeline,
        "residual": residual,
        "summary_json": summary_json,
        "physical_metadata": physical_metadata,
        "mask_analysis": load_mask_analysis(inputs.mask_analysis_dir),
    }


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


def derived_series(rows: list[dict[str, object]], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            value = float(row.get(column, math.nan))
        except (TypeError, ValueError):
            value = math.nan
        values.append(value if math.isfinite(value) else math.nan)
    return values


def plot_s_norm_rate(derived_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    x = derived_series(derived_rows, "Time_min")
    ax.plot(
        x,
        derived_series(derived_rows, "S_color_norm"),
        color=WONG["blue"],
        linewidth=LINEWIDTH,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=WONG["blue"],
        markevery=markevery([{} for _ in derived_rows]),
        label=r"$S_{\mathrm{color,norm}}$",
    )
    ax2 = ax.twinx()
    ax2.plot(
        x,
        derived_series(derived_rows, "DissolutionRate_time_lr_per_min"),
        color=WONG["vermillion"],
        linewidth=1.2,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=WONG["vermillion"],
        markevery=markevery([{} for _ in derived_rows]),
        label=r"$-dS_{\mathrm{color,norm}}/dt$",
    )
    ax.set_xlabel("Time (min)")
    ax.set_ylabel(r"$S_{\mathrm{color,norm}}$")
    ax2.set_ylabel("proxy removal rate (min$^{-1}$)")
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, ncols=2)
    style_axes(ax)
    style_axes(ax2, keep_right=True, grid_axis="y")
    return save_figure(fig, figures_dir, "08_S_color_norm_and_rate")


def plot_legacy_morphology(derived_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    fig, axes = plt.subplots(3, 1, figsize=TALL_SIZE, sharex=True)
    x = derived_series(derived_rows, "Time_min")
    specs = [
        (axes[0], "NumBlobs", "number of blobs", WONG["bluish_green"]),
        (axes[1], "ReqMedian", "median equivalent radius (px)", WONG["orange"]),
        (axes[2], "MaxBlobFrac", "largest blob fraction", WONG["reddish_purple"]),
    ]
    for ax, column, ylabel, color in specs:
        ax.plot(
            x,
            derived_series(derived_rows, column),
            color=color,
            linewidth=1.2,
            marker=MARKER,
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=color,
            markevery=markevery([{} for _ in derived_rows]),
        )
        ax.set_ylabel(ylabel)
        style_axes(ax)
    axes[-1].set_xlabel("Time (min)")
    return save_figure(fig, figures_dir, "09_legacy_morphology_metrics")


def plot_proxy_architecture_stage(derived_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    fig, axes = plt.subplots(2, 1, figsize=(180 / MM_PER_INCH, 104 / MM_PER_INCH), sharex=True)
    x = derived_series(derived_rows, "Time_min")
    stage_codes = {"near_depleted": 0, "tail": 1, "active_removal": 2, "induction_or_stable": 3}
    arch_codes = {"pool-like": 0, "mixed": 1, "ganglia-rich": 2}
    axes[0].plot(
        x,
        [stage_codes.get(str(row.get("Stage", "")), math.nan) for row in derived_rows],
        color=WONG["blue"],
        linewidth=1.2,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=WONG["blue"],
        markevery=markevery([{} for _ in derived_rows]),
    )
    axes[0].set_yticks(list(stage_codes.values()), list(stage_codes.keys()))
    axes[0].set_ylabel("proxy stage")
    axes[1].plot(
        x,
        [arch_codes.get(str(row.get("ArchitectureType_proxy", "")), math.nan) for row in derived_rows],
        color=WONG["orange"],
        linewidth=1.2,
        marker=MARKER,
        markersize=MARKER_SIZE,
        markerfacecolor="white",
        markeredgecolor=WONG["orange"],
        markevery=markevery([{} for _ in derived_rows]),
    )
    axes[1].set_yticks(list(arch_codes.values()), list(arch_codes.keys()))
    axes[1].set_ylabel("architecture proxy")
    axes[1].set_xlabel("Time (min)")
    for ax in axes:
        style_axes(ax)
    return save_figure(fig, figures_dir, "10_proxy_architecture_stage")


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def plot_qc_alignment_summary(qc_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    readiness = [
        row
        for row in qc_rows
        if str(row.get("metric", "")).endswith("_ready")
        or row.get("metric") in {"legacy_plot_timeseries_ready", "rate_correlations_ready", "multi_experiment_ready", "architecture_ready"}
    ]
    labels = [str(row["metric"]).replace("_ready", "") for row in readiness]
    values = [1.0 if truthy(row.get("value")) else 0.0 for row in readiness]
    colors = [WONG["bluish_green"] if value else WONG["gray"] for value in values]
    fig, ax = plt.subplots(figsize=(180 / MM_PER_INCH, 70 / MM_PER_INCH))
    ax.bar(range(len(labels)), values, color=colors)
    ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    ax.set_ylabel("ready")
    ax.set_ylim(0, 1.15)
    style_axes(ax, grid_axis="y")
    return save_figure(fig, figures_dir, "11_qc_alignment_summary")


def plot_mask_stack_toa_fingering(derived_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    fig, axes = plt.subplots(3, 1, figsize=TALL_SIZE, sharex=True)
    x = derived_series(derived_rows, "Time_min")
    specs = [
        (axes[0], "mask_stack_leading_front_fraction", "leading front", WONG["blue"], "front fraction"),
        (axes[1], "mask_stack_front_roughness_px", "front roughness", WONG["orange"], "roughness (px)"),
        (axes[2], "mask_stack_finger_count_proxy", "finger count proxy", WONG["bluish_green"], "count"),
    ]
    for ax, column, label, color, ylabel in specs:
        ax.plot(
            x,
            derived_series(derived_rows, column),
            color=color,
            linewidth=1.2,
            marker=MARKER,
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=color,
            markevery=markevery([{} for _ in derived_rows]),
            label=label,
        )
        ax.set_ylabel(ylabel)
        style_axes(ax)
    axes[-1].set_xlabel("Time (min)")
    return save_figure(fig, figures_dir, "12_mask_stack_toa_fingering")


def plot_phase_aware_retention(derived_rows: list[dict[str, object]], figures_dir: Path) -> dict[str, str]:
    fig, ax = plt.subplots(figsize=WIDE_SIZE)
    x = derived_series(derived_rows, "Time_min")
    for column, label, color in (
        ("phase_retained_from_full_fraction", "retained from full", WONG["blue"]),
        ("phase_depleted_from_full_fraction", "depleted from full", WONG["vermillion"]),
        ("phase_residual_cumulative_union_fraction_of_full", "residual cumulative union", WONG["bluish_green"]),
    ):
        ax.plot(
            x,
            derived_series(derived_rows, column),
            color=color,
            linewidth=1.2,
            marker=MARKER,
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=color,
            markevery=markevery([{} for _ in derived_rows]),
            label=label,
        )
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("fraction of full-NAPL baseline")
    ax.set_ylim(-0.03, 1.05)
    ax.legend(frameon=False, ncols=3)
    style_axes(ax)
    return save_figure(fig, figures_dir, "13_phase_aware_retention")


def create_figures(
    data: dict[str, Any],
    out_dir: Path,
    derived_rows: list[dict[str, object]],
    qc_rows: list[dict[str, object]],
) -> dict[str, dict[str, str]]:
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
        "S_color_norm_and_rate": plot_s_norm_rate(derived_rows, figures_dir),
        "legacy_morphology_metrics": plot_legacy_morphology(derived_rows, figures_dir),
        "proxy_architecture_stage": plot_proxy_architecture_stage(derived_rows, figures_dir),
        "qc_alignment_summary": plot_qc_alignment_summary(qc_rows, figures_dir),
        "mask_stack_toa_fingering": plot_mask_stack_toa_fingering(derived_rows, figures_dir),
        "phase_aware_retention": plot_phase_aware_retention(derived_rows, figures_dir),
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


def first_time_truthy(rows: list[dict[str, str]], column: str) -> float:
    candidates = []
    for row in rows:
        time_value = number(row, "Time_min")
        if truthy(row.get(column, "")) and math.isfinite(time_value):
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
    physical_metadata = data.get("physical_metadata", {})
    mask_analysis = data.get("mask_analysis", {})
    mask_analysis_summary = mask_analysis.get("summary_json", {})
    phase_aware = mask_analysis_summary.get("phase_aware", {}) if isinstance(mask_analysis_summary, dict) else {}
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
    mask_stack_rows = mask_analysis.get("timeseries", [])
    phase_mask_rows = mask_analysis.get("phase_timeseries", [])
    blob_morphology_rows = mask_analysis.get("blob_morphology", [])
    residual_mask_stack = rows_by_role(mask_stack_rows, "residual")
    residual_phase_mask = rows_by_role(phase_mask_rows, "residual")
    residual_blob_morphology = rows_by_role(blob_morphology_rows, "residual")

    rows: list[dict[str, str]] = []
    start_min, end_min, duration_min = time_range(primary)
    residual_start_min, _residual_end_min, _residual_duration_min = time_range(residual_primary)
    add_parameter(rows, "run", "total_rows", len(primary), "frames", "primary Branch C rows")
    add_parameter(rows, "run", "time_start_min", start_min, "min")
    add_parameter(rows, "run", "time_end_min", end_min, "min")
    add_parameter(rows, "run", "duration_min", duration_min, "min")
    add_parameter(rows, "metadata", "physical_metadata_status", physical_metadata.get("status", "not_provided"))
    add_parameter(rows, "metadata", "physical_metadata_trusted", bool(physical_metadata.get("trusted", False)))
    add_parameter(rows, "metadata", "processing_scale_factor", metadata_number(physical_metadata, "values", "processing_scale_factor"), "scale", "A1 current segmentation/morphology processing uses 3X upscale.")
    add_parameter(rows, "metadata", "pixel_size_um", metadata_number(physical_metadata, "values", "pixel_size_um"), "um/native-px")
    add_parameter(rows, "metadata", "processing_pixel_size_um", metadata_number(physical_metadata, "values", "processing_pixel_size_um"), "um/processing-px")
    add_parameter(rows, "metadata", "flow_rate_ul_min", metadata_number(physical_metadata, "values", "flow_rate_ul_min"), "uL/min")
    add_parameter(rows, "metadata", "pore_volume_ul", metadata_number(physical_metadata, "values", "pore_volume_ul"), "uL")
    add_parameter(rows, "metadata", "channel_width_um", metadata_number(physical_metadata, "values", "channel_width_um"), "um")
    add_parameter(rows, "metadata", "channel_depth_um", metadata_number(physical_metadata, "values", "channel_depth_um"), "um")
    add_parameter(rows, "metadata", "viscosity_Pa_s", metadata_number(physical_metadata, "values", "viscosity_Pa_s"), "Pa*s")
    add_parameter(rows, "metadata", "IFT_mN_m", metadata_number(physical_metadata, "values", "IFT_mN_m"), "mN/m")
    add_parameter(rows, "metadata", "velocity_m_per_s", metadata_number(physical_metadata, "derived", "velocity_m_per_s"), "m/s")
    add_parameter(rows, "metadata", "capillary_number", metadata_number(physical_metadata, "derived", "capillary_number"), "unitless")
    add_parameter(rows, "metadata", "temperature_C", metadata_number(physical_metadata, "values", "temperature_C"), "degC")
    add_parameter(rows, "metadata", "diffusion_coefficient_m2_s", metadata_number(physical_metadata, "values", "diffusion_coefficient_m2_s"), "m2/s")

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

    add_parameter(rows, "mask_stack", "mask_stack_analysis_rows", len(mask_stack_rows), "frames")
    add_parameter(rows, "mask_stack", "residual_leading_front_fraction_median", median_column(residual_mask_stack, "leading_front_fraction"), "fraction")
    add_parameter(rows, "mask_stack", "residual_front_roughness_median_px", median_column(residual_mask_stack, "front_roughness_px"), "px")
    add_parameter(rows, "mask_stack", "residual_finger_count_proxy_median", median_column(residual_mask_stack, "finger_count_proxy"), "count")
    add_parameter(rows, "mask_stack", "final_toa_cumulative_arrived_fraction", final_column(mask_stack_rows, "toa_cumulative_arrived_fraction"), "fraction")
    add_parameter(rows, "mask_stack", "first_outlet_band_breakthrough_time_min", first_time_truthy(mask_stack_rows, "outlet_band_breakthrough"), "min", "first C2 mask-stack outlet-band breakthrough")

    add_parameter(rows, "phase_aware", "phase_mask_timeseries_rows", len(phase_mask_rows), "frames")
    add_parameter(rows, "phase_aware", "full_baseline_area_px", phase_aware.get("full_baseline_area_px", math.nan), "px")
    add_parameter(rows, "phase_aware", "final_residual_retained_from_full_fraction", phase_aware.get("final_residual_retained_from_full_fraction", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "transient_residual_from_full_fraction", phase_aware.get("transient_residual_from_full_fraction", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "depleted_before_residual_fraction", phase_aware.get("depleted_before_residual_fraction", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "new_outside_full_fraction_of_full", phase_aware.get("new_outside_full_fraction_of_full", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "residual_persistence_frequency_p50", phase_aware.get("residual_persistence_frequency_p50", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "residual_persistence_frequency_p90", phase_aware.get("residual_persistence_frequency_p90", math.nan), "fraction")
    add_parameter(rows, "phase_aware", "residual_retained_from_full_fraction_median", median_column(residual_phase_mask, "retained_from_full_fraction"), "fraction")
    add_parameter(rows, "phase_aware", "residual_depleted_from_full_fraction_median", median_column(residual_phase_mask, "depleted_from_full_fraction"), "fraction")

    add_parameter(rows, "blob_detail", "blob_morphology_rows", len(blob_morphology_rows), "frames")
    add_parameter(rows, "blob_detail", "residual_AreaGini_median", median_column(residual_blob_morphology, "AreaGini"), "unitless")
    add_parameter(rows, "blob_detail", "residual_ShapeEntropy_area_median", median_column(residual_blob_morphology, "ShapeEntropy_area"), "unitless")
    add_parameter(rows, "blob_detail", "residual_AspectRatio_median", median_column(residual_blob_morphology, "AspectRatio_median"), "unitless")
    add_parameter(rows, "blob_detail", "residual_Solidity_median", median_column(residual_blob_morphology, "Solidity_median"), "unitless")
    add_parameter(rows, "blob_detail", "residual_EulerNumber_median", median_column(residual_blob_morphology, "EulerNumber_median"), "unitless")

    add_parameter(rows, "semantics", "figure_style", FIGURE_STYLE, "", "matched to visualization/plot_timeseries.py Nature-style defaults")
    return rows


def write_parameter_summary(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "parameter", "value", "units", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def parameter_rows_to_dict(rows: list[dict[str, str]]) -> dict[str, str]:
    return {f"{row['section']}.{row['parameter']}": row["value"] for row in rows}


def row_by_label(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("label", ""): row for row in rows if row.get("label", "")}


def first_finite_positive(rows: list[dict[str, str]], column: str) -> float:
    for row in rows:
        value = number(row, column)
        if math.isfinite(value) and value > 0:
            return value
    return math.nan


def normalization_baseline(rows: list[dict[str, str]], column: str) -> float:
    full_rows = rows_by_role(rows, "full_napl")
    full_values = finite_values(full_rows, column)
    positive_full = [value for value in full_values if value > 0]
    if positive_full:
        return median(positive_full)
    return first_finite_positive(rows, column)


def nearest_rate(x_values: list[float], y_values: list[float]) -> list[float]:
    rates: list[float] = []
    n = len(y_values)
    for idx in range(n):
        x0 = x_values[idx]
        y0 = y_values[idx]
        if not math.isfinite(x0) or not math.isfinite(y0):
            rates.append(math.nan)
            continue
        left = next(
            (
                j
                for j in range(idx - 1, -1, -1)
                if math.isfinite(x_values[j]) and math.isfinite(y_values[j]) and x_values[j] != x0
            ),
            None,
        )
        right = next(
            (
                j
                for j in range(idx + 1, n)
                if math.isfinite(x_values[j]) and math.isfinite(y_values[j]) and x_values[j] != x0
            ),
            None,
        )
        if left is not None and right is not None:
            dx = x_values[right] - x_values[left]
            dy = y_values[right] - y_values[left]
        elif right is not None:
            dx = x_values[right] - x0
            dy = y_values[right] - y0
        elif left is not None:
            dx = x0 - x_values[left]
            dy = y0 - y_values[left]
        else:
            rates.append(math.nan)
            continue
        rates.append(max(-(dy / dx), 0.0) if dx else math.nan)
    return rates


def cumulative_min(values: list[float]) -> list[float]:
    out: list[float] = []
    current = math.inf
    for value in values:
        if math.isfinite(value):
            current = min(current, value)
            out.append(current)
        else:
            out.append(math.nan)
    return out


def stage_proxy(sn_norm: float) -> str:
    if not math.isfinite(sn_norm) or sn_norm < 0.05:
        return "near_depleted"
    if sn_norm < 0.10:
        return "tail"
    if sn_norm < 0.95:
        return "active_removal"
    return "induction_or_stable"


def text_value(row: dict[str, str], column: str, default: str = "") -> str:
    value = row.get(column, default)
    if value is None:
        return default
    text = str(value)
    return default if text.lower() in {"", "nan", "none"} else text


def finite_or_nan(row: dict[str, str], column: str) -> float:
    return number(row, column)


def finite_or_zero(row: dict[str, str], column: str) -> float:
    value = number(row, column)
    return value if math.isfinite(value) else 0.0


def compute_derived_timeseries(data: dict[str, Any]) -> list[dict[str, object]]:
    timeline = data["timeline"]
    physical_metadata = data.get("physical_metadata", {})
    primary = timeline["primary"]
    sensitivity_by_label = row_by_label(timeline["sensitivity"])
    comparison_by_label = row_by_label(timeline["comparison"])
    xzone_by_label = row_by_label(timeline["xzone"])
    mask_by_label = row_by_label(timeline["mask"])
    blob_by_label = row_by_label(timeline["blob"])
    residual_by_label = row_by_label(data["residual"]["timeseries"])
    mask_stack_by_label = row_by_label(data.get("mask_analysis", {}).get("timeseries", []))
    phase_mask_by_label = row_by_label(data.get("mask_analysis", {}).get("phase_timeseries", []))
    blob_morphology_by_label = row_by_label(data.get("mask_analysis", {}).get("blob_morphology", []))
    baseline = normalization_baseline(primary, "S_NAPL_color")
    if not math.isfinite(baseline) or baseline == 0:
        baseline = 1.0
    metadata_trusted = bool(physical_metadata.get("trusted", False))
    processing_pixel_size_m = metadata_number(physical_metadata, "derived", "processing_pixel_size_m")
    processing_scale_factor = metadata_number(physical_metadata, "values", "processing_scale_factor")
    flow_rate_ul_min = metadata_number(physical_metadata, "values", "flow_rate_ul_min")
    pore_volume_ul = metadata_number(physical_metadata, "values", "pore_volume_ul")
    pixel_size_um = metadata_number(physical_metadata, "values", "pixel_size_um")
    processing_pixel_size_um = metadata_number(physical_metadata, "values", "processing_pixel_size_um")
    capillary_number = metadata_number(physical_metadata, "derived", "capillary_number")
    pv_ready = bool(physical_metadata.get("derived", {}).get("pv_ready", False))

    rows: list[dict[str, object]] = []
    for index, primary_row in enumerate(primary, start=1):
        label = text_value(primary_row, "label")
        sensitivity = sensitivity_by_label.get(label, {})
        comparison = comparison_by_label.get(label, {})
        xzone = xzone_by_label.get(label, {})
        mask = mask_by_label.get(label, {})
        blob = blob_by_label.get(label, {})
        residual = residual_by_label.get(label, {})
        mask_stack = mask_stack_by_label.get(label, {})
        phase_mask = phase_mask_by_label.get(label, {})
        blob_morphology = blob_morphology_by_label.get(label, {})

        s_a = number(comparison, "S_NAPL_color_A")
        if not math.isfinite(s_a):
            s_a = number(primary_row, "S_NAPL_color")
        s_b = number(comparison, "S_NAPL_color_B")
        if not math.isfinite(s_b):
            s_b = number(sensitivity, "S_NAPL_color")
        s_norm = s_a / baseline if math.isfinite(s_a) else math.nan
        num_blobs = finite_or_nan(blob, "num_blobs")
        red_area = finite_or_nan(mask, "red_mask_area_fraction")
        largest_component = finite_or_nan(blob, "largest_component_fraction")
        max_blob_frac = number(blob, "max_blob_frac")
        if not math.isfinite(max_blob_frac):
            max_blob_frac = largest_component
        valid_structure = (
            math.isfinite(s_norm)
            and s_norm >= 0.05
            and math.isfinite(num_blobs)
            and num_blobs >= 20
            and math.isfinite(red_area)
            and red_area > 0
        )
        stage = stage_proxy(s_norm)
        pool_score = int(math.isfinite(max_blob_frac) and max_blob_frac >= 0.5) + int(math.isfinite(num_blobs) and num_blobs <= 10)
        ganglia_score = int(math.isfinite(max_blob_frac) and max_blob_frac <= 0.3) + int(math.isfinite(num_blobs) and num_blobs >= 20)
        if pool_score >= 2 and ganglia_score == 0:
            architecture_type = "pool-like"
        elif ganglia_score >= 2 and pool_score == 0:
            architecture_type = "ganglia-rich"
        else:
            architecture_type = "mixed"
        water_length_m = finite_or_nan(mask, "dnapl_water_length_m")
        if not math.isfinite(water_length_m) and metadata_trusted and math.isfinite(processing_pixel_size_m):
            water_length_px = finite_or_nan(mask, "dnapl_water_length_px")
            water_length_m = (
                water_length_px * processing_pixel_size_m
                if math.isfinite(water_length_px)
                else math.nan
            )
        solid_length_m = finite_or_nan(mask, "dnapl_solid_length_m")
        if not math.isfinite(solid_length_m) and metadata_trusted and math.isfinite(processing_pixel_size_m):
            solid_length_px = finite_or_nan(mask, "dnapl_solid_length_px")
            solid_length_m = (
                solid_length_px * processing_pixel_size_m
                if math.isfinite(solid_length_px)
                else math.nan
            )
        real_time_s = finite_or_nan(primary_row, "RealTime_s")
        pv_value = (
            flow_rate_ul_min * real_time_s / 60.0 / pore_volume_ul
            if pv_ready and math.isfinite(real_time_s)
            else math.nan
        )
        row = {
            "FrameIndex": number(primary_row, "frame_index") or index,
            "frame_index": number(primary_row, "frame_index") or index,
            "label": label,
            "role": text_value(primary_row, "role"),
            "RealTime_s": real_time_s,
            "Time_min": finite_or_nan(primary_row, "Time_min"),
            "PV": pv_value,
            "Interval_s": finite_or_nan(primary_row, "Interval_s"),
            "TifFile": text_value(primary_row, "TifFile"),
            "PageInTif": finite_or_nan(primary_row, "PageInTif"),
            "S_NAPL_color_A": s_a,
            "S_NAPL_color_B": s_b,
            "S_NAPL_color_B_minus_A": number(comparison, "S_NAPL_color_B_minus_A"),
            "abs_endpoint_sensitivity": number(comparison, "abs_endpoint_sensitivity"),
            "Sn": s_a,
            "SnNorm": s_norm,
            "S_color_norm": s_norm,
            "RemovalFraction_proxy": 1.0 - s_norm if math.isfinite(s_norm) else math.nan,
            "RemovalFraction": 1.0 - s_norm if math.isfinite(s_norm) else math.nan,
            "red_mask_area_px": finite_or_nan(mask, "red_mask_area_px"),
            "domain_area_px": finite_or_nan(mask, "domain_area_px"),
            "TotalArea": finite_or_nan(mask, "red_mask_area_px"),
            "red_mask_area_fraction": red_area,
            "red_mask_retention_ratio": number(residual, "red_mask_retention_ratio"),
            "NumBlobs": num_blobs,
            "MeanBlobSize": finite_or_nan(blob, "mean_blob_size"),
            "MaxBlobFrac": max_blob_frac,
            "MaxBlobFlowFrac_proxy": red_area * max_blob_frac if math.isfinite(red_area) and math.isfinite(max_blob_frac) else math.nan,
            "ReqMedian": finite_or_nan(blob, "Req_median"),
            "ReqMean": finite_or_nan(blob, "Req_mean"),
            "ReqStd": finite_or_nan(blob, "Req_std"),
            "MeanCircularity": finite_or_nan(blob, "mean_circularity"),
            "fracDroplets": finite_or_nan(blob, "frac_droplets"),
            "fracColumns": finite_or_nan(blob, "frac_columns"),
            "fracClusters": finite_or_nan(blob, "frac_clusters"),
            "areaFracDroplets": finite_or_nan(blob, "frac_droplets"),
            "areaFracColumns": finite_or_nan(blob, "frac_columns"),
            "areaFracClusters": finite_or_nan(blob, "frac_clusters"),
            "areaFracDropletsValid": finite_or_nan(blob, "frac_droplets") if valid_structure else math.nan,
            "areaFracColumnsValid": finite_or_nan(blob, "frac_columns") if valid_structure else math.nan,
            "areaFracClustersValid": finite_or_nan(blob, "frac_clusters") if valid_structure else math.nan,
            "countFracDroplets": finite_or_nan(blob, "frac_droplets"),
            "countFracColumns": finite_or_nan(blob, "frac_columns"),
            "countFracClusters": finite_or_nan(blob, "frac_clusters"),
            "countFracDropletsValid": finite_or_nan(blob, "frac_droplets") if valid_structure else math.nan,
            "countFracColumnsValid": finite_or_nan(blob, "frac_columns") if valid_structure else math.nan,
            "countFracClustersValid": finite_or_nan(blob, "frac_clusters") if valid_structure else math.nan,
            "areaFracDroplets_proxy": finite_or_nan(blob, "frac_droplets"),
            "areaFracColumns_proxy": finite_or_nan(blob, "frac_columns"),
            "areaFracClusters_proxy": finite_or_nan(blob, "frac_clusters"),
            "dnapl_water_length_px": finite_or_nan(mask, "dnapl_water_length_px"),
            "dnapl_solid_length_px": finite_or_nan(mask, "dnapl_solid_length_px"),
            "dnapl_water_length_m": water_length_m,
            "dnapl_solid_length_m": solid_length_m,
            "InterfaceArea": finite_or_nan(mask, "InterfaceArea"),
            "solid_contact_fraction": finite_or_nan(mask, "solid_contact_fraction"),
            "a_i_2D_proxy": finite_or_nan(mask, "a_i_2D_proxy"),
            "mask_stack_leading_front_x_px": finite_or_nan(mask_stack, "leading_front_x_px"),
            "mask_stack_leading_front_fraction": finite_or_nan(mask_stack, "leading_front_fraction"),
            "mask_stack_front_roughness_px": finite_or_nan(mask_stack, "front_roughness_px"),
            "mask_stack_active_row_fraction": finite_or_nan(mask_stack, "active_row_fraction"),
            "mask_stack_outlet_band_active_fraction": finite_or_nan(mask_stack, "outlet_band_active_fraction"),
            "mask_stack_outlet_band_breakthrough": truthy(mask_stack.get("outlet_band_breakthrough", "")),
            "mask_stack_finger_count_proxy": finite_or_nan(mask_stack, "finger_count_proxy"),
            "mask_stack_toa_new_pixel_count": finite_or_nan(mask_stack, "toa_new_pixel_count"),
            "mask_stack_toa_cumulative_arrived_fraction": finite_or_nan(mask_stack, "toa_cumulative_arrived_fraction"),
            "mask_stack_area_delta_px": finite_or_nan(mask_stack, "mask_stack_area_delta_px"),
            "phase_full_baseline_area_px": finite_or_nan(phase_mask, "full_baseline_area_px"),
            "phase_retained_from_full_px": finite_or_nan(phase_mask, "retained_from_full_px"),
            "phase_retained_from_full_fraction": finite_or_nan(phase_mask, "retained_from_full_fraction"),
            "phase_depleted_from_full_px": finite_or_nan(phase_mask, "depleted_from_full_px"),
            "phase_depleted_from_full_fraction": finite_or_nan(phase_mask, "depleted_from_full_fraction"),
            "phase_new_outside_full_px": finite_or_nan(phase_mask, "new_outside_full_px"),
            "phase_new_outside_full_fraction": finite_or_nan(phase_mask, "new_outside_full_fraction"),
            "phase_residual_cumulative_union_px": finite_or_nan(phase_mask, "residual_cumulative_union_px"),
            "phase_residual_cumulative_union_fraction_of_full": finite_or_nan(phase_mask, "residual_cumulative_union_fraction_of_full"),
            "AreaGini": finite_or_nan(blob_morphology, "AreaGini"),
            "AreaEntropy": finite_or_nan(blob_morphology, "AreaEntropy"),
            "ShapeEntropy_count": finite_or_nan(blob_morphology, "ShapeEntropy_count"),
            "ShapeEntropy_area": finite_or_nan(blob_morphology, "ShapeEntropy_area"),
            "AspectRatio_median": finite_or_nan(blob_morphology, "AspectRatio_median"),
            "AspectRatio_p90": finite_or_nan(blob_morphology, "AspectRatio_p90"),
            "AspectRatio_area_weighted_mean": finite_or_nan(blob_morphology, "AspectRatio_area_weighted_mean"),
            "Solidity_median": finite_or_nan(blob_morphology, "Solidity_median"),
            "Solidity_p10": finite_or_nan(blob_morphology, "Solidity_p10"),
            "Solidity_area_weighted_mean": finite_or_nan(blob_morphology, "Solidity_area_weighted_mean"),
            "EulerNumber_median": finite_or_nan(blob_morphology, "EulerNumber_median"),
            "EulerNumber_mean": finite_or_nan(blob_morphology, "EulerNumber_mean"),
            "EulerNumber_min": finite_or_nan(blob_morphology, "EulerNumber_min"),
            "EulerHoleCount_sum": finite_or_nan(blob_morphology, "EulerHoleCount_sum"),
            "TopologyType_droplet_area_fraction": finite_or_nan(blob_morphology, "TopologyType_droplet_area_fraction"),
            "TopologyType_column_area_fraction": finite_or_nan(blob_morphology, "TopologyType_column_area_fraction"),
            "TopologyType_cluster_area_fraction": finite_or_nan(blob_morphology, "TopologyType_cluster_area_fraction"),
            "TopologyType_other_area_fraction": finite_or_nan(blob_morphology, "TopologyType_other_area_fraction"),
            "S_x_inlet": finite_or_nan(xzone, "S_x_inlet"),
            "S_x_mid": finite_or_nan(xzone, "S_x_mid"),
            "S_x_outlet": finite_or_nan(xzone, "S_x_outlet"),
            "active_bin_fraction_ge_0p2": finite_or_nan(xzone, "active_bin_fraction_ge_0p2"),
            "active_bin_fraction_ge_0p5": finite_or_nan(xzone, "active_bin_fraction_ge_0p5"),
            "napl_extent_fraction_ge_0p2": finite_or_nan(xzone, "napl_extent_fraction_ge_0p2"),
            "napl_extent_fraction_ge_0p5": finite_or_nan(xzone, "napl_extent_fraction_ge_0p5"),
            "qc_status": text_value(primary_row, "qc_status"),
            "TimelineStatus": text_value(primary_row, "TimelineStatus"),
            "endpoint_status": text_value(primary_row, "endpoint_policy", text_value(primary_row, "reference_transfer_status")),
            "endpoint_delta_A": finite_or_nan(primary_row, "endpoint_delta"),
            "endpoint_delta_B": finite_or_nan(sensitivity, "endpoint_delta"),
            "score_frame_A": finite_or_nan(primary_row, "score_frame"),
            "score_frame_B": finite_or_nan(sensitivity, "score_frame"),
            "score_water_ref_A": finite_or_nan(primary_row, "score_water_ref"),
            "score_water_ref_B": finite_or_nan(sensitivity, "score_water_ref"),
            "score_napl_ref_A": finite_or_nan(primary_row, "score_napl_ref"),
            "score_napl_ref_B": finite_or_nan(sensitivity, "score_napl_ref"),
            "pixel_size_um": pixel_size_um if metadata_trusted else math.nan,
            "processing_pixel_size_um": processing_pixel_size_um if metadata_trusted else math.nan,
            "processing_scale_factor": processing_scale_factor,
            "flow_rate_ul_min": flow_rate_ul_min if metadata_trusted else math.nan,
            "pore_volume_ul": pore_volume_ul if metadata_trusted else math.nan,
            "capillary_number": capillary_number if metadata_trusted else math.nan,
            "DissolutionStage_proxy": stage,
            "DissolutionStage": stage,
            "Stage": stage,
            "ValidStructure_proxy": valid_structure,
            "ValidStructure": valid_structure,
            "NearDepleted_proxy": stage == "near_depleted",
            "NearDepleted": stage == "near_depleted",
            "ValidArchitecture": valid_structure,
            "ArchitectureType_proxy": architecture_type,
            "PoolScore_proxy": pool_score,
            "GangliaScore_proxy": ganglia_score,
            "Sn_semantics": "operational_S_NAPL_color_proxy",
        }
        rows.append(row)

    s_norm_values = [float(row["S_color_norm"]) for row in rows]
    time_values = [float(row["Time_min"]) for row in rows]
    pv_values = [float(row["PV"]) for row in rows]
    s_mono = cumulative_min(s_norm_values)
    raw_rate = nearest_rate(time_values, s_norm_values)
    lr_rate = nearest_rate(time_values, s_mono)
    pv_lr_rate = nearest_rate(pv_values, s_mono)
    for row, mono, raw, lr, pv_lr in zip(rows, s_mono, raw_rate, lr_rate, pv_lr_rate):
        row["S_color_mono"] = mono
        row["Sn_rate_input"] = mono
        row["DissolutionRate_raw_per_min"] = raw
        row["DissolutionRate_time_lr_per_min"] = lr
        row["DissolutionRate_per_min"] = lr
        row["DissolutionRate_Sn_time_lr"] = lr
        row["DissolutionRate_Sn_movmed"] = raw
        row["DissolutionRate_Sn_lr"] = lr
        s_norm = float(row["S_color_norm"])
        normalized_rate = lr / max(s_norm, 1.0e-12) if math.isfinite(lr) and math.isfinite(s_norm) else math.nan
        row["NormalizedDissolutionRate_time_lr"] = normalized_rate
        row["NormalizedDissolutionRate_Sn_time_lr"] = normalized_rate
        row["NormalizedDissolutionRate_Sn_movmed"] = raw / max(s_norm, 1.0e-12) if math.isfinite(raw) and math.isfinite(s_norm) else math.nan
        row["NormalizedDissolutionRate_Sn_lr"] = normalized_rate
        row["DissolutionRate_pv_lr_per_PV"] = pv_lr
        row["dS_dPV"] = pv_lr
    return rows


DERIVED_FIELDNAMES = [
    "FrameIndex",
    "frame_index",
    "label",
    "role",
    "RealTime_s",
    "Time_min",
    "PV",
    "Interval_s",
    "TifFile",
    "PageInTif",
    "S_NAPL_color_A",
    "S_NAPL_color_B",
    "S_NAPL_color_B_minus_A",
    "abs_endpoint_sensitivity",
    "Sn",
    "SnNorm",
    "S_color_norm",
    "S_color_mono",
    "Sn_rate_input",
    "RemovalFraction_proxy",
    "RemovalFraction",
    "DissolutionRate_raw_per_min",
    "DissolutionRate_time_lr_per_min",
    "DissolutionRate_per_min",
    "DissolutionRate_Sn_time_lr",
    "DissolutionRate_Sn_movmed",
    "DissolutionRate_Sn_lr",
    "DissolutionRate_pv_lr_per_PV",
    "dS_dPV",
    "NormalizedDissolutionRate_time_lr",
    "NormalizedDissolutionRate_Sn_time_lr",
    "NormalizedDissolutionRate_Sn_movmed",
    "NormalizedDissolutionRate_Sn_lr",
    "DissolutionStage_proxy",
    "DissolutionStage",
    "Stage",
    "ValidStructure_proxy",
    "ValidStructure",
    "NearDepleted_proxy",
    "NearDepleted",
    "ValidArchitecture",
    "ArchitectureType_proxy",
    "PoolScore_proxy",
    "GangliaScore_proxy",
    "red_mask_area_px",
    "domain_area_px",
    "TotalArea",
    "red_mask_area_fraction",
    "red_mask_retention_ratio",
    "NumBlobs",
    "MeanBlobSize",
    "MaxBlobFrac",
    "MaxBlobFlowFrac_proxy",
    "ReqMedian",
    "ReqMean",
    "ReqStd",
    "MeanCircularity",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "areaFracDropletsValid",
    "areaFracColumnsValid",
    "areaFracClustersValid",
    "countFracDroplets",
    "countFracColumns",
    "countFracClusters",
    "countFracDropletsValid",
    "countFracColumnsValid",
    "countFracClustersValid",
    "areaFracDroplets_proxy",
    "areaFracColumns_proxy",
    "areaFracClusters_proxy",
    "dnapl_water_length_px",
    "dnapl_solid_length_px",
    "dnapl_water_length_m",
    "dnapl_solid_length_m",
    "InterfaceArea",
    "solid_contact_fraction",
    "a_i_2D_proxy",
    "mask_stack_leading_front_x_px",
    "mask_stack_leading_front_fraction",
    "mask_stack_front_roughness_px",
    "mask_stack_active_row_fraction",
    "mask_stack_outlet_band_active_fraction",
    "mask_stack_outlet_band_breakthrough",
    "mask_stack_finger_count_proxy",
    "mask_stack_toa_new_pixel_count",
    "mask_stack_toa_cumulative_arrived_fraction",
    "mask_stack_area_delta_px",
    "phase_full_baseline_area_px",
    "phase_retained_from_full_px",
    "phase_retained_from_full_fraction",
    "phase_depleted_from_full_px",
    "phase_depleted_from_full_fraction",
    "phase_new_outside_full_px",
    "phase_new_outside_full_fraction",
    "phase_residual_cumulative_union_px",
    "phase_residual_cumulative_union_fraction_of_full",
    "AreaGini",
    "AreaEntropy",
    "ShapeEntropy_count",
    "ShapeEntropy_area",
    "AspectRatio_median",
    "AspectRatio_p90",
    "AspectRatio_area_weighted_mean",
    "Solidity_median",
    "Solidity_p10",
    "Solidity_area_weighted_mean",
    "EulerNumber_median",
    "EulerNumber_mean",
    "EulerNumber_min",
    "EulerHoleCount_sum",
    "TopologyType_droplet_area_fraction",
    "TopologyType_column_area_fraction",
    "TopologyType_cluster_area_fraction",
    "TopologyType_other_area_fraction",
    "S_x_inlet",
    "S_x_mid",
    "S_x_outlet",
    "active_bin_fraction_ge_0p2",
    "active_bin_fraction_ge_0p5",
    "napl_extent_fraction_ge_0p2",
    "napl_extent_fraction_ge_0p5",
    "qc_status",
    "TimelineStatus",
    "endpoint_status",
    "endpoint_delta_A",
    "endpoint_delta_B",
    "score_frame_A",
    "score_frame_B",
    "score_water_ref_A",
    "score_water_ref_B",
    "score_napl_ref_A",
    "score_napl_ref_B",
    "pixel_size_um",
    "processing_pixel_size_um",
    "processing_scale_factor",
    "flow_rate_ul_min",
    "pore_volume_ul",
    "capillary_number",
    "Sn_semantics",
]


def write_rows_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field, "")) for field in fieldnames})


LEGACY_REQUIRED_COLUMNS = [
    "RealTime_s",
    "Sn",
    "NumBlobs",
    "MaxBlobFrac",
    "ReqMedian",
    "ReqMean",
    "ReqStd",
    "InterfaceArea",
    "MeanCircularity",
    "a_i_2D",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
]


def make_legacy_rows(derived_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
    nonfinite_required_count = 0
    numeric_fields = {
        "RealTime_s",
        "Time_min",
        "FrameIndex",
        "Sn",
        "SnNorm",
        "NumBlobs",
        "MeanBlobSize",
        "MaxBlobFrac",
        "ReqMedian",
        "ReqMean",
        "ReqStd",
        "InterfaceArea",
        "MeanCircularity",
        "a_i_2D",
        "fracDroplets",
        "fracColumns",
        "fracClusters",
        "DissolutionRate_per_min",
        "DissolutionRate_raw_per_min",
        "DissolutionRate_Sn_time_lr",
        "DissolutionRate_Sn_movmed",
        "DissolutionRate_Sn_lr",
        "NormalizedDissolutionRate_Sn_time_lr",
        "NormalizedDissolutionRate_Sn_movmed",
        "NormalizedDissolutionRate_Sn_lr",
        "MaxBlobFlowFrac",
        "MeanCircularity_raw",
        "MeanCircularity_valid",
        "areaFracDroplets",
        "areaFracColumns",
        "areaFracClusters",
        "areaFracDropletsValid",
        "areaFracColumnsValid",
        "areaFracClustersValid",
        "countFracDroplets",
        "countFracColumns",
        "countFracClusters",
        "countFracDropletsValid",
        "countFracColumnsValid",
        "countFracClustersValid",
    }
    for row in derived_rows:
        legacy = {
            "RealTime_s": row.get("RealTime_s", math.nan),
            "Time_min": row.get("Time_min", math.nan),
            "FrameIndex": row.get("FrameIndex", math.nan),
            "Sn": row.get("S_NAPL_color_A", math.nan),
            "SnNorm": row.get("S_color_norm", math.nan),
            "NumBlobs": row.get("NumBlobs", math.nan),
            "MeanBlobSize": row.get("MeanBlobSize", math.nan),
            "MaxBlobFrac": row.get("MaxBlobFrac", math.nan),
            "ReqMedian": row.get("ReqMedian", math.nan),
            "ReqMean": row.get("ReqMean", math.nan),
            "ReqStd": row.get("ReqStd", math.nan),
            "InterfaceArea": row.get("InterfaceArea", math.nan),
            "MeanCircularity": row.get("MeanCircularity", math.nan),
            "a_i_2D": row.get("a_i_2D_proxy", math.nan),
            "fracDroplets": row.get("fracDroplets", math.nan),
            "fracColumns": row.get("fracColumns", math.nan),
            "fracClusters": row.get("fracClusters", math.nan),
            "DissolutionRate_per_min": row.get("DissolutionRate_time_lr_per_min", math.nan),
            "DissolutionRate_raw_per_min": row.get("DissolutionRate_raw_per_min", math.nan),
            "DissolutionRate_Sn_time_lr": row.get("DissolutionRate_Sn_time_lr", math.nan),
            "DissolutionRate_Sn_movmed": row.get("DissolutionRate_Sn_movmed", math.nan),
            "DissolutionRate_Sn_lr": row.get("DissolutionRate_Sn_lr", math.nan),
            "NormalizedDissolutionRate_Sn_time_lr": row.get("NormalizedDissolutionRate_Sn_time_lr", math.nan),
            "NormalizedDissolutionRate_Sn_movmed": row.get("NormalizedDissolutionRate_Sn_movmed", math.nan),
            "NormalizedDissolutionRate_Sn_lr": row.get("NormalizedDissolutionRate_Sn_lr", math.nan),
            "ValidStructure": row.get("ValidStructure_proxy", False),
            "DissolutionStage": row.get("DissolutionStage_proxy", ""),
            "Stage": row.get("Stage", ""),
            "NearDepleted": row.get("NearDepleted", False),
            "MaxBlobFlowFrac": row.get("MaxBlobFlowFrac_proxy", math.nan),
            "MeanCircularity_raw": row.get("MeanCircularity", math.nan),
            "MeanCircularity_valid": row.get("MeanCircularity", math.nan) if row.get("ValidStructure_proxy", False) else math.nan,
            "areaFracDroplets": row.get("areaFracDroplets", math.nan),
            "areaFracColumns": row.get("areaFracColumns", math.nan),
            "areaFracClusters": row.get("areaFracClusters", math.nan),
            "areaFracDropletsValid": row.get("areaFracDropletsValid", math.nan),
            "areaFracColumnsValid": row.get("areaFracColumnsValid", math.nan),
            "areaFracClustersValid": row.get("areaFracClustersValid", math.nan),
            "countFracDroplets": row.get("countFracDroplets", math.nan),
            "countFracColumns": row.get("countFracColumns", math.nan),
            "countFracClusters": row.get("countFracClusters", math.nan),
            "countFracDropletsValid": row.get("countFracDropletsValid", math.nan),
            "countFracColumnsValid": row.get("countFracColumnsValid", math.nan),
            "countFracClustersValid": row.get("countFracClustersValid", math.nan),
            "Sn_semantics": "operational_S_NAPL_color_proxy",
            "InterfaceArea_semantics": "legacy_alias_of_dnapl_water_length_px",
            "AdapterWarning": "not_endpoint_validated_physical_Sn",
        }
        for field in numeric_fields:
            value = legacy.get(field, math.nan)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = math.nan
            if field in LEGACY_REQUIRED_COLUMNS and not math.isfinite(numeric):
                nonfinite_required_count += 1
        rows.append(legacy)
    return rows, nonfinite_required_count


LEGACY_FIELDNAMES = [
    "RealTime_s",
    "Time_min",
    "FrameIndex",
    "Sn",
    "SnNorm",
    "NumBlobs",
    "MeanBlobSize",
    "MaxBlobFrac",
    "ReqMedian",
    "ReqMean",
    "ReqStd",
    "InterfaceArea",
    "MeanCircularity",
    "a_i_2D",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "DissolutionRate_per_min",
    "DissolutionRate_raw_per_min",
    "DissolutionRate_Sn_time_lr",
    "DissolutionRate_Sn_movmed",
    "DissolutionRate_Sn_lr",
    "NormalizedDissolutionRate_Sn_time_lr",
    "NormalizedDissolutionRate_Sn_movmed",
    "NormalizedDissolutionRate_Sn_lr",
    "ValidStructure",
    "DissolutionStage",
    "Stage",
    "NearDepleted",
    "MaxBlobFlowFrac",
    "MeanCircularity_raw",
    "MeanCircularity_valid",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "areaFracDropletsValid",
    "areaFracColumnsValid",
    "areaFracClustersValid",
    "countFracDroplets",
    "countFracColumns",
    "countFracClusters",
    "countFracDropletsValid",
    "countFracColumnsValid",
    "countFracClustersValid",
    "Sn_semantics",
    "InterfaceArea_semantics",
    "AdapterWarning",
]


def count_values(rows: list[dict[str, object]], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(column, ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def nonfinite_count(rows: list[dict[str, object]], column: str) -> int:
    count = 0
    for row in rows:
        try:
            value = float(row.get(column, math.nan))
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value):
            count += 1
    return count


def compute_qc_summary(
    data: dict[str, Any],
    derived_rows: list[dict[str, object]],
    legacy_rows: list[dict[str, object]],
    legacy_nonfinite_count: int,
) -> list[dict[str, object]]:
    summary_json = data["summary_json"]
    physical_metadata = data.get("physical_metadata", {})
    mask_analysis = data.get("mask_analysis", {})
    mask_analysis_summary = mask_analysis.get("summary_json", {})
    mask_readiness = mask_analysis_summary.get("readiness", {}) if isinstance(mask_analysis_summary, dict) else {}
    rows: list[dict[str, object]] = []

    def add(metric: str, value: object, units: str = "", notes: str = "") -> None:
        rows.append({"metric": metric, "value": value, "units": units, "notes": notes})

    add("primary_rows", len(data["timeline"]["primary"]), "rows")
    add("derived_rows", len(derived_rows), "rows")
    add("legacy_rows", len(legacy_rows), "rows")
    for key, value in summary_json.get("missing_label_counts", {}).items():
        add(f"missing_label.{key}", value, "rows")
    for status, count in count_values(derived_rows, "TimelineStatus").items():
        add(f"TimelineStatus.{status or 'blank'}", count, "rows")
    for status, count in count_values(derived_rows, "qc_status").items():
        add(f"qc_status.{status or 'blank'}", count, "rows")
    for column in [
        "S_NAPL_color_A",
        "S_color_norm",
        "DissolutionRate_time_lr_per_min",
        "DissolutionRate_pv_lr_per_PV",
        "PV",
        "InterfaceArea",
        "a_i_2D_proxy",
    ]:
        add(f"nonfinite.{column}", nonfinite_count(derived_rows, column), "rows")
    legacy_schema_ready = all(column in legacy_rows[0] for column in LEGACY_REQUIRED_COLUMNS) if legacy_rows else False
    legacy_plot_ready = legacy_schema_ready and legacy_nonfinite_count == 0
    add("legacy_adapter_schema_ready", legacy_schema_ready, "", "Required legacy columns are present.")
    add("legacy_plot_timeseries_ready", legacy_plot_ready, "", "Required legacy columns are present and finite.")
    add("legacy_adapter_nonfinite_required_value_count", legacy_nonfinite_count, "cells", "Nonfinite legacy numeric values are preserved as NaN, not filled.")
    metadata_trusted = bool(physical_metadata.get("trusted", False))
    processing_pixel_size_um = metadata_number(physical_metadata, "values", "processing_pixel_size_um")
    processing_scale_factor = metadata_number(physical_metadata, "values", "processing_scale_factor")
    capillary_number = metadata_number(physical_metadata, "derived", "capillary_number")
    meter_values = []
    for row in derived_rows:
        try:
            meter_value = float(row.get("dnapl_water_length_m", math.nan))
        except (TypeError, ValueError):
            meter_value = math.nan
        if math.isfinite(meter_value):
            meter_values.append(meter_value)
    meter_ready = (
        metadata_trusted
        and math.isfinite(processing_pixel_size_um)
        and bool(meter_values)
        and all(value > 0 for value in meter_values)
    )
    pv_ready = bool(physical_metadata.get("derived", {}).get("pv_ready", False))
    capillary_number_ready = metadata_trusted and math.isfinite(capillary_number)
    add("physical_metadata_status", physical_metadata.get("status", "not_provided"), "", "Trusted metadata is required before proxy fields are promoted to physical quantities.")
    add("physical_metadata_trusted", metadata_trusted, "", "True only when the metadata manifest has trusted=true or a trusted/calibrated status.")
    add("processing_scale_factor", processing_scale_factor, "scale", "Processing-grid upscale factor recorded in metadata/provenance; current A1 branch uses 3X.")
    add("pixel_size_ready", meter_ready, "", "True only when metre interface fields are finite positive.")
    add("pv_ready", pv_ready, "", "Requires trusted flow_rate_ul_min and pore_volume_ul.")
    add("capillary_number_ready", capillary_number_ready, "", "Requires trusted flow rate, channel width/depth, viscosity, and IFT.")
    add("mass_ready", False, "", "Missing mass calibration / MassDissolvedKg.")
    add("mask_stack_ready", bool(mask_readiness.get("mask_stack_ready", False)), "", "True when C2 red_mask_stack.h5 has been analyzed.")
    add("toa_ready", bool(mask_readiness.get("toa_ready", False)), "", "True when pixel-level TOA map and x-summary are available.")
    add("mask_front_fingering_ready", bool(mask_readiness.get("mask_front_fingering_ready", False)), "", "True when mask-stack front roughness/finger proxy metrics are available.")
    add("phase_aware_mask_ready", bool(mask_readiness.get("phase_aware_mask_ready", False)), "", "True when full-NAPL baseline and residual persistence/depletion metrics are available.")
    add("true_fingering_ready", bool(mask_readiness.get("mask_front_fingering_ready", False)), "", "Mask-stack fingering proxy is available; pore-graph fingering remains a separate validation step.")
    add("blob_detail_distribution_ready", bool(mask_readiness.get("blob_detail_distribution_ready", False)), "", "True when per-blob C2 detail has been summarized by frame.")
    add("pore_graph_fingering_ready", False, "", "Requires a pore graph or solid/core graph definition.")
    add("mask_stack_analysis_status", mask_analysis_summary.get("status", "not_provided") if isinstance(mask_analysis_summary, dict) else "not_provided")
    add("rate_correlations_ready", legacy_plot_ready, "", "Proxy rate/structure columns are available and required plot fields are finite.")
    add("multi_experiment_ready", legacy_plot_ready, "", "Legacy adapter exposes finite standard comparison columns.")
    add("architecture_ready", True, "", "Only proxy architecture labels are available.")
    add("InterfaceArea_unit", "px_length", "", "Legacy name; projected interface length L_ow, not area.")
    add("Req_unit", "um" if meter_ready else "px", "", "Uses physical units only when trusted pixel-size metadata is applied.")
    add("a_i_2D_unit", "px_per_px2_proxy", "", "2D mask-derived proxy.")
    return rows


QC_FIELDNAMES = ["metric", "value", "units", "notes"]


def make_alignment_rows(
    physical_metadata: dict[str, Any] | None = None,
    mask_analysis: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    physical_metadata = physical_metadata or {}
    mask_analysis = mask_analysis or {}
    mask_summary = mask_analysis.get("summary_json", {})
    mask_readiness = mask_summary.get("readiness", {}) if isinstance(mask_summary, dict) else {}
    mask_stack_ready = bool(mask_readiness.get("mask_stack_ready", False))
    toa_ready = bool(mask_readiness.get("toa_ready", False))
    mask_fingering_ready = bool(mask_readiness.get("mask_front_fingering_ready", False))
    phase_aware_ready = bool(mask_readiness.get("phase_aware_mask_ready", False))
    blob_distribution_ready = bool(mask_readiness.get("blob_detail_distribution_ready", False))
    metadata_trusted = bool(physical_metadata.get("trusted", False))
    pixel_size_ready = metadata_trusted and math.isfinite(
        metadata_number(physical_metadata, "values", "processing_pixel_size_um")
    )
    pv_ready = bool(physical_metadata.get("derived", {}).get("pv_ready", False))
    ca_ready = metadata_trusted and math.isfinite(
        metadata_number(physical_metadata, "derived", "capillary_number")
    )
    scale_recorded = math.isfinite(
        metadata_number(physical_metadata, "values", "processing_scale_factor")
    )
    rows: list[dict[str, object]] = []

    def add(parameter: str, legacy: str, source: str, status: str, semantics: str, missing: str = "", requirement: str = "") -> None:
        rows.append(
            {
                "parameter": parameter,
                "legacy_source": legacy,
                "branch_c_source": source,
                "status": status,
                "semantics": semantics,
                "missing_reason": missing,
                "next_requirement": requirement,
            }
        )

    add("Sn", "plot_timeseries.py", "S_NAPL_color_A", "aligned_proxy", "operational color-index saturation proxy", "not endpoint-validated physical Sn", "masked endpoint audit pass")
    add("SnNorm", "plot_timeseries.py", "S_color_norm", "aligned_proxy", "S_NAPL_color_A normalized to full-role baseline", "", "physical Sn endpoint calibration for strict Sn/Sn0")
    add("S_NAPL_color_raw", "utilities/build_solubilization_timeseries_table.m", "score_frame_A / score_water_ref_A / score_napl_ref_A", "aligned_proxy", "raw endpoint-normalized color-index components", "not endpoint-validated physical Sn", "masked endpoint audit pass")
    add("Sn_mask_secondary", "utilities/build_solubilization_timeseries_table.m", "red_mask_area_fraction", "aligned_proxy", "2D red-mask occupancy proxy", "not volumetric saturation", "pixel-size/depth/pore-volume calibration")
    add("mask_color_abs_difference", "utilities/build_solubilization_timeseries_table.m", "abs(S_color_norm - red_mask_retention_ratio)", "derived_proxy", "agreement diagnostic between color-index and mask occupancy proxies", "not yet written as a dedicated time-series column", "add dedicated column if needed by downstream scripts")
    add("endpoint_source/mask/rgb fields", "utilities/build_solubilization_timeseries_table.m", "endpoint_status and source CSV provenance", "partial_proxy", "endpoint policy and input paths recorded in provenance", "not full legacy manifest schema", "export endpoint/mask/rgb provenance columns if legacy importer needs them")
    add("Sn_lower/Sn_mid/Sn_upper", "utilities/build_solubilization_timeseries_table.m", "S_NAPL_color_A/B sensitivity envelope", "partial_proxy", "endpoint A/B sensitivity can bound proxy Sn", "not statistical confidence interval", "define uncertainty model after endpoint audit")
    add("Sn_uncertainty", "utilities/build_solubilization_timeseries_table.m", "abs_endpoint_sensitivity", "aligned_proxy", "endpoint A/B absolute sensitivity")
    add("validation_status/processing_branch", "utilities/build_solubilization_timeseries_table.m", "TimelineStatus/qc_status/analysis_policy_version", "partial_proxy", "QC and policy status are recorded", "legacy names not fully replicated", "add exact legacy columns if importing back into MATLAB result table")
    add(
        "processing_scale_factor",
        "utilities/build_solubilization_timeseries_table.m",
        "physical_metadata.processing_scale_factor",
        "metadata_recorded" if scale_recorded else "missing_metadata",
        "image processing scale; A1 current Branch C/C2 processing uses 3X upscale",
        "" if scale_recorded else "not present in aggregate CSV inputs",
        "record in manifest/provenance during Branch C/C2 generation",
    )
    add("regional_bin_columns", "visualization/plot_timeseries_pv_common.py", "S_x_inlet/S_x_mid/S_x_outlet and x-zone extent fields", "aligned_proxy", "flow-direction x-zone color-index proxies", "not geometric core/edge", "provide solid/core mask for geometric core/edge")
    add("RemovalFraction", "plot_timeseries.py", "RemovalFraction", "aligned_proxy", "1 - S_color_norm", "not physical removal fraction", "physical Sn endpoint calibration")
    add("DissolutionRate_per_min", "plot_timeseries.py; plot_rate_correlations.py", "DissolutionRate_time_lr_per_min", "aligned_proxy", "-dS_color_norm/dt", "not physical dissolution rate", "physical Sn or mass calibration")
    add("DissolutionRate_Sn_*", "plot_rate_correlations.py", "DissolutionRate_Sn_time_lr/movmed/lr", "aligned_proxy", "proxy rate variants for legacy scripts", "not physical rate", "physical Sn calibration")
    add("NormalizedDissolutionRate_Sn_*", "plot_rate_correlations.py", "NormalizedDissolutionRate_Sn_*", "aligned_proxy", "proxy rate divided by S_color_norm", "not physical normalized rate", "physical Sn calibration")
    add("RateLR_*", "compute_dissolution_rate_windows.py", "DissolutionRate_time_lr_per_min", "partial_proxy", "global nearest-neighbor/cumulative-min proxy rate", "not windowed legacy LR suite", "define window lengths and PV/time axis")
    add("RateRawCentral_*", "compute_dissolution_rate_windows.py", "DissolutionRate_raw_per_min", "partial_proxy", "global nearest-neighbor raw proxy rate", "not exact legacy central-window rate", "define window lengths and edge handling")
    add("NumBlobs", "plot_timeseries.py", "num_blobs", "aligned", "red-mask connected components")
    add("MeanBlobSize", "utilities/build_solubilization_timeseries_table.m", "mean_blob_size", "aligned", "mean red-mask component size")
    add("MaxBlobFrac", "plot_timeseries.py", "max_blob_frac", "aligned", "largest red-mask component fraction")
    add("MaxBlobFlowFrac", "plot_timeseries.py", "MaxBlobFlowFrac_proxy", "aligned_proxy", "red_mask_area_fraction * MaxBlobFrac")
    add("ReqMedian/Mean/Std", "plot_timeseries.py", "Req_median/mean/std", "aligned", "equivalent-radius summary in pixels")
    add("MeanCircularity*", "compute_area_weighted_circularity.py", "mean_circularity and valid proxy", "partial_proxy", "frame-level circularity summary; no per-blob area-weighted recomputation", "missing per-blob detail for strict valid area-weighting", "provide blob_detail_all_frames.csv")
    add("Area*", "analyze_blob_population_morphology.py", "red_mask_area_px/MeanBlobSize + blob_morphology_timeseries.csv", "aligned_blob_detail" if blob_distribution_ready else "partial_proxy", "frame-level area and per-blob area distribution summaries", "" if blob_distribution_ready else "missing per-blob area distribution", "run maskanalysis")
    add("EquivRadius*", "analyze_blob_population_morphology.py", "ReqMedian/Mean/Std", "aligned", "equivalent-radius summary in pixels")
    add("Circularity2D*", "analyze_blob_population_morphology.py", "MeanCircularity", "partial_proxy", "frame-level mean circularity only", "missing strict circularity distribution", "extend maskanalysis to summarize per-blob Circularity if needed")
    add("AspectRatio*", "analyze_blob_population_morphology.py", "blob_morphology_timeseries.AspectRatio_*", "aligned_blob_detail" if blob_distribution_ready else "not_computable", "aspect-ratio distribution from C2 per-blob detail", "" if blob_distribution_ready else "requires per-blob major/minor axes", "run maskanalysis")
    add("Solidity*", "analyze_blob_population_morphology.py", "blob_morphology_timeseries.Solidity_*", "aligned_blob_detail" if blob_distribution_ready else "not_computable", "solidity distribution from C2 per-blob detail", "" if blob_distribution_ready else "requires per-blob convex area", "run maskanalysis")
    add("EulerNumber*", "analyze_blob_population_morphology.py", "blob_morphology_timeseries.EulerNumber_*", "aligned_blob_detail" if blob_distribution_ready else "not_computable", "per-blob topology summary", "" if blob_distribution_ready else "requires per-blob hole/topology detail", "run maskanalysis")
    add("AreaGini", "analyze_blob_population_morphology.py", "blob_morphology_timeseries.AreaGini", "aligned_blob_detail" if blob_distribution_ready else "not_computable", "blob area inequality", "" if blob_distribution_ready else "requires per-blob area distribution", "run maskanalysis")
    add("size_distribution_slope", "analyze_blob_population_morphology.py", "", "not_computable", "blob size-distribution slope", "not implemented in maskanalysis v1", "add log-log distribution fit")
    add("shape_entropy", "analyze_blob_population_morphology.py", "blob_morphology_timeseries.ShapeEntropy_*", "aligned_blob_detail" if blob_distribution_ready else "not_computable", "shape/topology-distribution entropy", "" if blob_distribution_ready else "requires per-blob shape distribution", "run maskanalysis")
    add("fracDroplets/Columns/Clusters", "plot_timeseries.py", "frac_droplets/columns/clusters", "aligned_proxy", "classification fractions copied from C2 summary")
    add("areaFrac*/countFrac*Valid", "plot_timeseries.py; analyze_blob_population_morphology.py", "area/count proxy copies", "partial_proxy", "valid variants masked by ValidStructure_proxy", "no per-blob area/count recomputation", "provide blob_detail_all_frames.csv")
    add("InterfaceArea", "utilities/build_solubilization_timeseries_table.m", "dnapl_water_length_px", "aligned_proxy", "legacy alias of L_ow projected length, not area", "", "processing_pixel_size_um for metre units")
    add(
        "dnapl_water_length_m",
        "new Branch C/C2 contract",
        "dnapl_water_length_m",
        "aligned" if pixel_size_ready else "missing_metadata",
        "metre L_ow",
        "" if pixel_size_ready else "missing trusted processing_pixel_size_um",
        "provide trusted native pixel size plus processing scale, or processing pixel size",
    )
    add("dnapl_solid_length_px", "new Branch C/C2 contract", "dnapl_solid_length_px", "aligned", "DNAPL-solid projected contact length")
    add(
        "dnapl_solid_length_m",
        "new Branch C/C2 contract",
        "dnapl_solid_length_m",
        "aligned" if pixel_size_ready else "missing_metadata",
        "metre DNAPL-solid contact length",
        "" if pixel_size_ready else "missing trusted processing_pixel_size_um",
        "provide trusted native pixel size plus processing scale, or processing pixel size",
    )
    add("a_i_2D", "plot_timeseries.py", "a_i_2D_proxy", "aligned_proxy", "2D mask-derived L_ow/red-area proxy")
    add("ArchitectureType/PoolScore/GangliaScore", "analyze_architecture_vs_time.py", "ArchitectureType_proxy/PoolScore_proxy/GangliaScore_proxy", "partial_proxy", "Level-A proxy from blob count and largest-component fraction", "not legacy threshold-calibrated architecture", "run architecture classifier on physical Sn + full morphology")
    add(
        "pixel_size_um",
        "visualization/recover_experiment_metadata.py",
        "physical_metadata.pixel_size_um",
        "metadata_ready" if pixel_size_ready else "missing_metadata",
        "pixel-to-length calibration",
        "" if pixel_size_ready else "not present as trusted metadata",
        "provide trusted calibration or processing manifest",
    )
    add(
        "processing_pixel_size_um",
        "visualization/recover_experiment_metadata.py + Branch C adapter",
        "physical_metadata.processing_pixel_size_um",
        "metadata_ready" if pixel_size_ready else "missing_metadata",
        "processing-grid pixel-to-length calibration",
        "" if pixel_size_ready else "not present as trusted metadata",
        "provide trusted calibration and processing_scale_factor",
    )
    add(
        "pore_volume_ul",
        "visualization/recover_experiment_metadata.py",
        "physical_metadata.pore_volume_ul",
        "metadata_ready" if pv_ready else "missing_metadata",
        "pore volume",
        "" if pv_ready else "not present as trusted metadata",
        "provide pore-volume metadata",
    )
    add("pore_area_px", "visualization/recover_experiment_metadata.py", "domain_area_px", "partial_proxy", "2D ROI/domain pixel area", "not physical pore area unless ROI/domain mask is calibrated", "provide calibrated pore mask and pixel size")
    add("channel_depth_um/channel_width_um", "visualization/recover_experiment_metadata.py", "", "missing_metadata", "chip geometry", "not present in aggregate CSV inputs", "provide experiment metadata")
    add("flow_rate_ul_min", "visualization/recover_experiment_metadata.py", "physical_metadata.flow_rate_ul_min", "metadata_ready" if pv_ready else "missing_metadata", "flow rate", "" if pv_ready else "not present as trusted metadata", "provide pump/experiment metadata")
    add("velocity_m_per_s", "visualization/recover_experiment_metadata.py", "physical_metadata derived velocity_m_per_s", "metadata_ready" if ca_ready else "missing_metadata", "Darcy/interstitial velocity", "" if ca_ready else "requires flow rate and pore geometry", "provide flow rate, pore area, and porosity/depth")
    add("viscosity_Pa_s", "visualization/recover_experiment_metadata.py", "physical_metadata.viscosity_Pa_s", "metadata_ready" if ca_ready else "missing_metadata", "fluid viscosity", "" if ca_ready else "not present as trusted metadata", "provide fluid metadata")
    add("IFT_mN_m", "visualization/recover_experiment_metadata.py", "physical_metadata.IFT_mN_m", "metadata_ready" if ca_ready else "missing_metadata", "interfacial tension", "" if ca_ready else "not present as trusted metadata", "provide fluid metadata")
    add("capillary_number", "visualization/recover_experiment_metadata.py", "physical_metadata derived capillary_number", "metadata_ready" if ca_ready else "missing_metadata", "Ca = mu*v/gamma", "" if ca_ready else "requires viscosity, velocity, and IFT", "provide physical metadata")
    add("temperature_C", "visualization/recover_experiment_metadata.py", "", "missing_metadata", "temperature", "not present in aggregate CSV inputs", "provide experiment metadata")
    add("diffusion_coefficient_m2_s", "visualization/recover_experiment_metadata.py", "", "missing_metadata", "diffusion coefficient", "not present in aggregate CSV inputs", "provide solute/fluid metadata")
    add("surfactant_name/concentration", "visualization/recover_experiment_metadata.py", "", "missing_metadata", "surfactant condition", "not present in aggregate CSV inputs", "provide experiment metadata")
    add("PV", "plot_timeseries_pv_common.py", "PV", "aligned_proxy" if pv_ready else "missing_metadata", "pore-volume axis", "" if pv_ready else "missing trusted flow_rate_ul_min and pore_volume_ul", "provide flow rate and pore volume metadata")
    add("dS/dPV", "compute_dissolution_rate_windows.py", "dS_dPV", "aligned_proxy" if pv_ready else "missing_metadata", "PV-normalized proxy rate", "" if pv_ready else "missing PV axis", "provide flow rate and pore volume metadata")
    add("MassDissolvedKg", "plot_rate_correlations.py", "", "missing_metadata", "mass-based dissolution", "missing mass calibration", "provide mass calibration")
    add("DissolutionRate_mass_kg_per_s", "plot_rate_correlations.py", "", "missing_metadata", "mass dissolution rate", "missing mass calibration", "provide mass calibration and time/PV basis")
    add("projected_interface_mass_flux", "plot_rate_correlations.py", "", "missing_metadata", "mass flux normalized by projected L_ow or area convention", "missing mass calibration and physical interface units", "provide mass calibration and pixel size/depth convention")
    add("MassTransferProxy_*", "plot_rate_correlations.py", "DissolutionRate_* with InterfaceArea/a_i_2D_proxy", "partial_proxy", "possible proxy correlations only", "not physical mass-transfer coefficient", "provide mass calibration, physical interface units, and flow metadata")
    add("TOA", "utilities/generate_toa_map.m", "toa_frame_index.npy + toa_x_summary.csv", "aligned_mask_stack" if toa_ready else "not_computable", "pixel-level time of arrival from C2 red-mask stack", "" if toa_ready else "requires frame-level mask stack", "run maskanalysis")
    add("full_NAPL_baseline_mask", "new Branch C/C2 contract", "full_baseline_union_mask.npy", "aligned_phase_mask" if phase_aware_ready else "not_computable", "union of full-NAPL role C2 masks used as phase baseline", "" if phase_aware_ready else "requires full_napl and residual roles in mask stack", "run phase-aware maskanalysis")
    add("residual_persistence_map", "new Branch C/C2 contract", "residual_frequency.npy / residual_persistence_count.npy", "aligned_phase_mask" if phase_aware_ready else "not_computable", "per-pixel residual retention frequency relative to residual frames", "" if phase_aware_ready else "requires residual-role mask stack", "run phase-aware maskanalysis")
    add("depletion/last_seen_map", "new Branch C/C2 contract", "last_seen_frame_index.npy / phase_retention_class.npy", "aligned_phase_mask" if phase_aware_ready else "not_computable", "last frame seen and retained/depleted/transient residual classes", "" if phase_aware_ready else "requires full/residual phase-aware pass", "run phase-aware maskanalysis")
    add("xzone_front_extent_proxy", "analysis/fingering", "x-zone extent proxy", "partial_proxy", "thresholded x-zone color-index front/extent proxy", "not graph fingering", "run maskanalysis for strict mask front")
    add("mask_stack_front", "analysis/fingering", "mask_stack_analysis_timeseries.leading_front_fraction/front_roughness_px", "aligned_mask_stack" if mask_stack_ready else "not_computable", "strict C2 mask-stack leading front and roughness", "" if mask_stack_ready else "requires frame-level mask stack", "run maskanalysis")
    add("true_fingering", "analysis/fingering", "mask_stack_analysis_timeseries.finger_count_proxy", "aligned_mask_stack_proxy" if mask_fingering_ready else "not_computable", "mask-stack front-band finger-count proxy; pore-graph fingering remains separate", "" if mask_fingering_ready else "requires frame-level connected masks", "add pore graph for graph fingering")
    add("num_fingers/tau/branch_density/x_lead/front_width/A_invaded", "analysis/fingering", "finger_count_proxy/leading_front_fraction/front_roughness_px", "partial_mask_stack" if mask_fingering_ready else "not_computable", "front and finger-count proxies only; tortuosity/branch density need graph analysis", "missing pore graph skeleton metrics", "add pore graph/skeleton fingering postprocess")
    return rows


ALIGNMENT_FIELDNAMES = ["parameter", "legacy_source", "branch_c_source", "status", "semantics", "missing_reason", "next_requirement"]


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
    if inputs.mask_analysis_dir is not None:
        command += f" --mask-analysis-dir \"{inputs.mask_analysis_dir}\""
    if inputs.physical_metadata_path is not None:
        command += f" --physical-metadata \"{inputs.physical_metadata_path}\""
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
    derived_timeseries_path: Path,
    legacy_plot_path: Path,
    qc_summary_path: Path,
    alignment_path: Path,
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
        f"- mask_analysis_dir: `{inputs.mask_analysis_dir or ''}`",
        f"- physical_metadata: `{inputs.physical_metadata_path or ''}`",
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
        f"Frame-level derived table: `{derived_timeseries_path}`",
        f"Legacy plot-timeseries adapter: `{legacy_plot_path}`",
        f"QC summary: `{qc_summary_path}`",
        f"Research parameter alignment table: `{alignment_path}`",
        "",
        "| section | parameter | value | units |",
        "|---|---|---:|---|",
    ]
    report_sections = {
        "run",
        "metadata",
        "phase",
        "saturation",
        "endpoint_sensitivity",
        "segmentation",
        "interface",
        "morphology",
        "xzone",
        "front_proxy",
        "mask_stack",
        "phase_aware",
        "blob_detail",
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
            "- `TOA` and front/fingering proxy fields come from C2 `red_mask_stack.h5`, not x-zone color-index curves.",
            "- Phase-aware metrics use the full-NAPL role mask union as the baseline for residual retention/depletion.",
            "- `AreaGini`, `ShapeEntropy_*`, `AspectRatio_*`, `Solidity_*`, and `EulerNumber_*` come from C2 per-blob detail.",
            "- Physical-unit fields are emitted only when a trusted physical metadata manifest is supplied.",
            "- Current A1 Branch C/C2 processing records `processing_scale_factor = 3`; historical 2X preview notes are not the active processing-grid contract.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_package(inputs: PackageInputs) -> dict[str, Any]:
    inputs.out_dir.mkdir(parents=True, exist_ok=True)
    data = load_inputs(inputs)
    derived_rows = compute_derived_timeseries(data)
    legacy_rows, legacy_nonfinite_count = make_legacy_rows(derived_rows)
    qc_rows = compute_qc_summary(data, derived_rows, legacy_rows, legacy_nonfinite_count)
    alignment_rows = make_alignment_rows(
        data.get("physical_metadata", {}),
        data.get("mask_analysis", {}),
    )
    figures = create_figures(data, inputs.out_dir, derived_rows, qc_rows)
    parameter_rows = compute_parameter_summary(data)
    report_path = inputs.out_dir / "analysis_report.md"
    commands_path = inputs.out_dir / "run_commands.md"
    parameter_summary_path = inputs.out_dir / "analysis_parameter_summary.csv"
    derived_timeseries_path = inputs.out_dir / "analysis_timeseries_derived.csv"
    legacy_plot_path = inputs.out_dir / "branch_c_legacy_plot_timeseries.csv"
    qc_summary_path = inputs.out_dir / "analysis_qc_summary.csv"
    alignment_path = inputs.out_dir / "research_parameter_alignment.csv"
    provenance_path = inputs.out_dir / "analysis_package_provenance.json"
    write_parameter_summary(parameter_summary_path, parameter_rows)
    write_rows_csv(derived_timeseries_path, derived_rows, DERIVED_FIELDNAMES)
    write_rows_csv(legacy_plot_path, legacy_rows, LEGACY_FIELDNAMES)
    write_rows_csv(qc_summary_path, qc_rows, QC_FIELDNAMES)
    write_rows_csv(alignment_path, alignment_rows, ALIGNMENT_FIELDNAMES)
    write_report(
        inputs,
        data,
        figures,
        parameter_rows,
        parameter_summary_path,
        derived_timeseries_path,
        legacy_plot_path,
        qc_summary_path,
        alignment_path,
        report_path,
    )
    write_run_commands(inputs, commands_path)

    summary_json = data["summary_json"]
    physical_metadata = data.get("physical_metadata", {})
    figure_counts = {
        "figure_count": len(figures),
        "png_count": sum(1 for outputs in figures.values() if outputs.get("png")),
        "svg_count": sum(1 for outputs in figures.values() if outputs.get("svg")),
        "figure_names": sorted(figures.keys()),
    }
    provenance = {
        "status": "pass",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_label": inputs.run_label,
        "git_head": git_head(Path(__file__).resolve().parents[2]),
        "figure_style": FIGURE_STYLE,
        "analysis_policy_version": ANALYSIS_POLICY_VERSION,
        "figure_counts": figure_counts,
        "input_paths": {
            "timeline_dir": str(inputs.timeline_dir),
            "residual_dir": str(inputs.residual_dir),
            "mask_analysis_dir": str(inputs.mask_analysis_dir or ""),
            "physical_metadata": str(inputs.physical_metadata_path or ""),
        },
        "outputs": {
            "report_md": str(report_path),
            "run_commands_md": str(commands_path),
            "parameter_summary_csv": str(parameter_summary_path),
            "derived_timeseries_csv": str(derived_timeseries_path),
            "legacy_plot_timeseries_csv": str(legacy_plot_path),
            "qc_summary_csv": str(qc_summary_path),
            "research_parameter_alignment_csv": str(alignment_path),
            "figures": figures,
        },
        "row_counts": summary_json.get("row_counts", {}),
        "missing_label_counts": summary_json.get("missing_label_counts", {}),
        "summary_metrics": summary_json.get("summary_metrics", {}),
        "physical_metadata": physical_metadata,
        "mask_analysis": data.get("mask_analysis", {}).get("summary_json", {}),
        "derived_parameters": parameter_rows_to_dict(parameter_rows),
        "qc_summary": parameter_rows_to_dict(
            [{"section": "qc", "parameter": row["metric"], "value": format_value(row["value"])} for row in qc_rows]
        ),
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
    parser.add_argument("--mask-analysis-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-label", default="DNAPL Branch C full3585")
    parser.add_argument("--physical-metadata", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provenance = build_package(
        PackageInputs(
            timeline_dir=args.timeline_dir,
            residual_dir=args.residual_dir,
            out_dir=args.out_dir,
            run_label=args.run_label,
            physical_metadata_path=args.physical_metadata,
            mask_analysis_dir=args.mask_analysis_dir,
        )
    )
    print(f"ANALYSIS_PACKAGE {provenance['outputs']['provenance_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
