"""Redraw one figure stem across multiple experiments from per-plot workbooks."""

from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


WONG_COLORS = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "bluish_green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
}

MM_PER_INCH = 25.4
INDIVIDUAL_SIZE = (89 / MM_PER_INCH, 68 / MM_PER_INCH)
LINEWIDTH = 1.8
MARKER_SIZE = 4.0
COLOR_CYCLE = [
    WONG_COLORS["blue"],
    WONG_COLORS["vermillion"],
    WONG_COLORS["bluish_green"],
    WONG_COLORS["orange"],
    WONG_COLORS["reddish_purple"],
    WONG_COLORS["sky_blue"],
    WONG_COLORS["black"],
]
MARKER_CYCLE = ["o", "s", "^", "D", "v", "P", "X"]
LINESTYLE_CYCLE = ["-", "--", "-.", ":"]
STAGE_MARKERS = {
    "early": "o",
    "middle": "s",
    "late": "^",
    "near-depleted": "x",
    "near_depleted": "x",
    "induction_or_stable": "D",
    "active_removal": "o",
    "tail": "^",
    "excluded_context": "x",
}

META_COLUMNS = {
    "FrameIndex",
    "RealTime_s",
    "Time_min",
    "Stage",
    "DissolutionStage",
    "ValidStructure",
    "NearDepleted",
    "SourceWorkbook",
    "SourceSheet",
    "ExperimentLabel",
    "SeriesName",
    "X",
    "Y",
}

PRIMARY_Y_BY_STEM = {
    "01_saturation_decay": ("SnNorm", "Sn"),
    "02_dissolution_rate": ("DissolutionRate_per_min",),
    "03_blob_count": ("NumBlobs",),
    "04_largest_blob_fraction": ("MaxBlobFrac_valid", "MaxBlobFrac"),
    "05_equivalent_radius_stats": ("ReqMedian",),
    "06_interface_area": ("InterfaceArea",),
    "07_largest_blob_flow_fraction": ("MaxBlobFlowFrac_valid", "MaxBlobFlowFrac"),
    "08_a_i_2D": ("a_i_2D_valid", "a_i_2D"),
    "09_mean_circularity": ("MeanCircularity_valid", "MeanCircularity"),
    "10_fraction_droplets": ("areaFracDropletsValid", "fracDroplets"),
    "11_fraction_columns": ("areaFracColumnsValid", "fracColumns"),
    "12_fraction_clusters": ("areaFracClustersValid", "fracClusters"),
    "13_sn_norm_ai_2D_overlay": ("SnNorm",),
    "14_rate_vs_ai_2D_stage": ("DissolutionRate_per_min",),
    "S01_rate_vs_ai_2D_stage": ("DissolutionRate_per_min",),
    "14_rate_vs_interface_area_stage": ("DissolutionRate_per_min",),
    "15_rate_vs_num_blobs_stage": ("DissolutionRate_per_min",),
    "16_rate_vs_max_blob_frac_stage": ("DissolutionRate_per_min",),
    "17_rate_vs_req_median_stage": ("DissolutionRate_per_min",),
}

PRIMARY_X_BY_STEM = {
    "14_rate_vs_ai_2D_stage": ("a_i_2D_valid", "a_i_2D"),
    "S01_rate_vs_ai_2D_stage": ("a_i_2D_valid", "a_i_2D"),
    "14_rate_vs_interface_area_stage": ("InterfaceArea",),
    "15_rate_vs_num_blobs_stage": ("NumBlobs",),
    "16_rate_vs_max_blob_frac_stage": ("MaxBlobFrac_valid", "MaxBlobFrac"),
    "17_rate_vs_req_median_stage": ("ReqMedian",),
}

Y_LABELS = {
    "SnNorm": "Sn/Sn0",
    "Sn": "Saturation, Sn",
    "DissolutionRate_per_min": "Dissolution rate (min$^{-1}$)",
    "NumBlobs": "Number of blobs",
    "MaxBlobFrac": "Largest blob fraction",
    "MaxBlobFrac_valid": "Largest blob fraction",
    "ReqMedian": "Median equivalent radius",
    "InterfaceArea": "Interface area",
    "MaxBlobFlowFrac": "Amax / Aflow",
    "MaxBlobFlowFrac_valid": "Amax / Aflow",
    "a_i_2D": r"$a_i^{2D}$",
    "a_i_2D_valid": r"$a_i^{2D}$",
    "MeanCircularity": "Mean circularity",
    "MeanCircularity_valid": "Mean circularity",
    "areaFracDropletsValid": "Droplet fraction",
    "areaFracColumnsValid": "Column fraction",
    "areaFracClustersValid": "Cluster fraction",
    "fracDroplets": "Droplet fraction",
    "fracColumns": "Column fraction",
    "fracClusters": "Cluster fraction",
}


@dataclass
class ExperimentSpec:
    label: str
    figures_dir: Path | None
    workbook: Path | None
    color: str
    marker: str
    linestyle: str


@dataclass
class WorkbookData:
    experiment: ExperimentSpec
    path: Path
    sheet_name: str
    data: pd.DataFrame


def configure_nature_style():
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


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_linewidth(0.9)
        ax.spines[side].set_color("#2B2B2B")
    ax.tick_params(
        axis="both",
        which="major",
        direction="out",
        colors="#2B2B2B",
        length=4.0,
        width=0.9,
    )
    ax.tick_params(
        axis="both",
        which="minor",
        direction="out",
        colors="#2B2B2B",
        length=2.2,
        width=0.6,
    )
    ax.minorticks_on()
    ax.grid(True, which="major", color="#E4E4E4", linewidth=0.55, alpha=0.7)
    ax.set_axisbelow(True)
    return ax


def legend_above(ax, handles=None, labels=None, ncol=None, fontsize=None):
    if handles is None or labels is None:
        handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return
    if ncol is None:
        ncol = len(handles)
    ax.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=max(1, ncol),
        frameon=False,
        handlelength=1.2,
        handletextpad=0.4,
        columnspacing=1.0,
        borderaxespad=0.0,
        fontsize=fontsize,
    )


def parse_csv_list(values):
    out = []
    for value in values or []:
        out.extend(item.strip() for item in str(value).split(",") if item.strip())
    return out


def _optional_string(row, name, default):
    value = row.get(name, default)
    if pd.isna(value) or str(value).strip() == "":
        return default
    return str(value).strip()


def load_manifest(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        msg = f"Manifest not found: {manifest_path}"
        parent = manifest_path.parent
        if parent.is_dir():
            candidates = sorted(parent.glob("compare_manifest*.csv"))
            if candidates:
                shown = [p.name for p in candidates[:15]]
                msg += (
                    "\nFound these manifest CSV files in the same output folder:\n  "
                    + "\n  ".join(shown)
                )
                if len(candidates) > 15:
                    msg += f"\n  ... ({len(candidates)} total)"
            else:
                msg += (
                    "\nParent directory exists but contains no 'compare_manifest*.csv' files."
                )
        else:
            msg += (
                "\nParent directory does not exist. Under G:\\微流控, experiment folders "
                "often use '4UL' / '8UL' (no space before UL), not '4 UL' / '8 UL'."
            )
        raise FileNotFoundError(msg)
    df = pd.read_csv(manifest_path, encoding="utf-8-sig")
    required = {"label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Manifest missing required column(s): {', '.join(sorted(missing))}")
    if "figures_dir" not in df.columns and "workbook" not in df.columns:
        raise ValueError("Manifest must contain either 'figures_dir' or 'workbook'")

    if "order" in df.columns:
        sort_key = pd.to_numeric(df["order"], errors="coerce")
        df = df.assign(_order=sort_key).sort_values(["_order"], na_position="last")

    experiments = []
    for idx, (_, row) in enumerate(df.iterrows()):
        label = str(row["label"]).strip()
        if not label:
            raise ValueError("Manifest contains an empty label")
        workbook_value = row.get("workbook", "")
        figures_dir_value = row.get("figures_dir", "")
        workbook = None
        figures_dir = None
        if not pd.isna(workbook_value) and str(workbook_value).strip():
            workbook = Path(str(workbook_value).strip())
            if not workbook.exists():
                raise FileNotFoundError(f"workbook does not exist for {label}: {workbook}")
        if not pd.isna(figures_dir_value) and str(figures_dir_value).strip():
            figures_dir = Path(str(figures_dir_value).strip())
            if not figures_dir.exists():
                raise FileNotFoundError(f"figures_dir does not exist for {label}: {figures_dir}")
        if workbook is None and figures_dir is None:
            raise ValueError(f"Manifest row for {label} must provide 'figures_dir' or 'workbook'")
        experiments.append(
            ExperimentSpec(
                label=label,
                figures_dir=figures_dir,
                workbook=workbook,
                color=_optional_string(row, "color", COLOR_CYCLE[idx % len(COLOR_CYCLE)]),
                marker=_optional_string(row, "marker", MARKER_CYCLE[idx % len(MARKER_CYCLE)]),
                linestyle=_optional_string(row, "linestyle", LINESTYLE_CYCLE[idx % len(LINESTYLE_CYCLE)]),
            )
        )
    if not experiments:
        raise ValueError("Manifest contains no experiments")
    return experiments


def workbook_path(figures_dir, stem):
    if isinstance(figures_dir, ExperimentSpec):
        if figures_dir.workbook is not None:
            return figures_dir.workbook
        if figures_dir.figures_dir is None:
            raise ValueError(f"No figures_dir or workbook configured for {figures_dir.label}")
        return figures_dir.figures_dir / f"{stem}_data.xlsx"
    return Path(figures_dir) / f"{stem}_data.xlsx"


def choose_sheet(path, requested="auto"):
    with pd.ExcelFile(path) as xl:
        sheet_names = list(xl.sheet_names)
    if requested != "auto":
        if requested not in sheet_names:
            raise ValueError(f"{path.name} does not contain sheet '{requested}'")
        return requested
    if "data_plotted" in sheet_names:
        return "data_plotted"
    if "data" in sheet_names:
        return "data"
    if "data_all" in sheet_names:
        return "data_all"
    return sheet_names[0]


def load_workbooks(experiments, stem, sheet="auto", allow_missing=False):
    loaded = []
    missing = []
    for experiment in experiments:
        path = workbook_path(experiment, stem)
        if not path.exists():
            missing.append(f"{experiment.label}: {path}")
            continue
        sheet_name = choose_sheet(path, sheet)
        df = pd.read_excel(path, sheet_name=sheet_name)
        loaded.append(WorkbookData(experiment, path, sheet_name, df))
    if missing and not allow_missing:
        raise FileNotFoundError(
            "Missing requested workbook(s):\n" + "\n".join(missing)
        )
    for item in missing:
        warnings.warn(f"Skipping missing workbook: {item}", RuntimeWarning)
    if not loaded:
        raise FileNotFoundError(f"No workbooks found for stem '{stem}'")
    return loaded


def _first_existing(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _metric_from_rate_stem(stem):
    text = stem
    if "_vs_" not in text:
        return None
    metric = text.split("_vs_", 1)[1]
    for suffix in (
        "_stage_scatter",
        "_trajectory_timecolored",
        "_binned_active",
        "_stage",
    ):
        if metric.endswith(suffix):
            metric = metric[: -len(suffix)]
    aliases = {
        "projected_interface_length": ("InterfaceArea", "InterfaceArea_plot"),
        "interface_area": ("InterfaceArea", "InterfaceArea_plot"),
        "a_i_2D": ("a_i_2D_plot", "a_i_2D_valid", "a_i_2D"),
        "max_blob_fraction": ("MaxBlobFrac_valid", "MaxBlobFrac", "MaxBlobFrac_plot"),
        "num_blobs": ("NumBlobs", "NumBlobs_plot"),
        "req_median": ("ReqMedian", "ReqMedian_plot"),
        "frac_droplets": ("fracDroplets", "fracDroplets_plot", "areaFracDropletsValid"),
        "frac_columns": ("fracColumns", "fracColumns_plot", "areaFracColumnsValid"),
        "frac_clusters": ("fracClusters", "fracClusters_plot", "areaFracClustersValid"),
    }
    return aliases.get(metric)


def is_binned_table(df):
    return {"x_bin_median", "rate_median"}.issubset(df.columns)


def is_rate_like(stem, df):
    if "rate_vs" in stem or "_vs_" in stem:
        return True
    if is_binned_table(df):
        return True
    return any(str(col).startswith(("DissolutionRate_", "NormalizedDissolutionRate_")) for col in df.columns)


def select_x_column(stem, df, requested="auto"):
    columns = set(df.columns)
    if requested != "auto":
        if requested not in columns:
            raise ValueError(f"Requested x column '{requested}' not found")
        return requested
    if is_binned_table(df):
        return "x_bin_median"
    mapped = _first_existing(columns, PRIMARY_X_BY_STEM.get(stem, ()))
    if mapped is not None:
        return mapped
    inferred = _metric_from_rate_stem(stem)
    if inferred:
        mapped = _first_existing(columns, inferred)
        if mapped is not None:
            return mapped
    plot_cols = [col for col in df.columns if str(col).endswith("_plot")]
    if len(plot_cols) == 1:
        return plot_cols[0]
    if "Time_min" in columns and not is_rate_like(stem, df):
        return "Time_min"
    if "Time_min" in columns:
        return "Time_min"
    raise ValueError(f"Could not infer x column for stem '{stem}'")


def select_y_columns(stem, df, requested="auto", all_series=False):
    columns = set(df.columns)
    if requested != "auto":
        selected = parse_csv_list([requested])
        missing = [col for col in selected if col not in columns]
        if missing:
            raise ValueError(f"Requested y column(s) not found: {', '.join(missing)}")
        return selected
    if is_binned_table(df):
        return ["rate_median"]
    if all_series:
        numeric_cols = [
            col
            for col in df.columns
            if col not in META_COLUMNS and pd.api.types.is_numeric_dtype(df[col])
        ]
        return numeric_cols
    mapped = _first_existing(columns, PRIMARY_Y_BY_STEM.get(stem, ()))
    if mapped is not None:
        return [mapped]
    rate_cols = [
        col
        for col in df.columns
        if str(col).startswith(("DissolutionRate_", "NormalizedDissolutionRate_"))
    ]
    if rate_cols:
        return [rate_cols[0]]
    numeric_cols = [
        col
        for col in df.columns
        if col not in META_COLUMNS and not str(col).endswith("_raw") and pd.api.types.is_numeric_dtype(df[col])
    ]
    if numeric_cols:
        return [numeric_cols[0]]
    raise ValueError(f"Could not infer y column for stem '{stem}'")


def infer_kind(stem, df):
    if is_binned_table(df):
        return "binned"
    if is_rate_like(stem, df) and ("Stage" in df.columns or "DissolutionStage" in df.columns or "_vs_" in stem):
        return "scatter"
    return "time_series"


def default_scales(kind, requested):
    if requested is not None:
        return ["linear", "log"] if requested == "both" else [requested]
    return ["linear", "log"] if kind == "time_series" else ["linear"]


def axis_label(column):
    if column == "Time_min":
        return "Time (min)"
    if column == "x_bin_median":
        return "Binned metric median"
    if column == "rate_median":
        return "Median dissolution rate"
    return Y_LABELS.get(column, str(column).replace("_", " "))


def line_label(experiment, y_col, y_cols):
    if len(y_cols) == 1:
        return experiment.label
    return f"{experiment.label} - {axis_label(y_col)}"


def _numeric_xy(df, x_col, y_col):
    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask], mask


def _numeric_column_or_nan(df, column):
    if column not in df.columns:
        return np.full(len(df), np.nan, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)


def _xy_for_plot(x, y, scale, x_col):
    if scale != "log":
        return x, y
    if x_col == "Time_min" and len(x) and np.any(x <= 0):
        finite_x = np.sort(np.unique(x[np.isfinite(x)]))
        diffs = np.diff(finite_x)
        positive = diffs[diffs > 0]
        interval = float(np.min(positive)) if len(positive) else 1.0
        synthetic_start = max(0.05 * interval, np.finfo(float).tiny)
        keep = x > 0
        if not np.any(keep):
            return np.array([], dtype=float), np.array([], dtype=float)
        first = int(np.argmin(x))
        return np.concatenate(([synthetic_start], x[keep])), np.concatenate(([y[first]], y[keep]))
    keep = x > 0
    return x[keep], y[keep]


def tidy_rows_for_workbook(workbook, x_col, y_cols):
    frames = []
    base = workbook.data.copy()
    base["ExperimentLabel"] = workbook.experiment.label
    base["SourceWorkbook"] = str(workbook.path)
    base["SourceSheet"] = workbook.sheet_name
    for y_col in y_cols:
        if x_col not in base.columns or y_col not in base.columns:
            continue
        out = base.copy()
        out["SeriesName"] = y_col
        out["X"] = pd.to_numeric(out[x_col], errors="coerce")
        out["Y"] = pd.to_numeric(out[y_col], errors="coerce")
        frames.append(out)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    first_cols = ["ExperimentLabel", "SourceWorkbook", "SourceSheet", "SeriesName", "X", "Y"]
    remaining = [col for col in combined.columns if col not in first_cols]
    return combined[first_cols + remaining]


def plot_time_series(ax, workbooks, stem, x_col, y_cols, scale):
    for wb in workbooks:
        for y_col in y_cols:
            x, y, _ = _numeric_xy(wb.data, x_col, y_col)
            x_plot, y_plot = _xy_for_plot(x, y, scale, x_col)
            if not len(x_plot):
                continue
            ax.plot(
                x_plot,
                y_plot,
                color=wb.experiment.color,
                linestyle=wb.experiment.linestyle,
                linewidth=LINEWIDTH,
                marker=wb.experiment.marker,
                markersize=MARKER_SIZE,
                markerfacecolor="white",
                markeredgecolor=wb.experiment.color,
                markeredgewidth=1.0,
                markevery=max(1, len(x_plot) // 20),
                label=line_label(wb.experiment, y_col, y_cols),
            )
    ax.set_xlabel(axis_label(x_col) + (" (log scale)" if scale == "log" else ""))
    ax.set_ylabel(axis_label(y_cols[0]) if len(y_cols) == 1 else "Value")
    if scale == "log":
        ax.set_xscale("log")
    style_axes(ax)
    if scale == "log":
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)
    legend_above(ax)


def _stage_column(df):
    if "Stage" in df.columns:
        return "Stage"
    if "DissolutionStage" in df.columns:
        return "DissolutionStage"
    return None


def plot_scatter(ax, workbooks, stem, x_col, y_cols, scale):
    y_col = y_cols[0]
    handles = []
    labels = []
    for wb in workbooks:
        df = wb.data
        stage_col = _stage_column(df)
        if stage_col:
            stages = [stage for stage in pd.Series(df[stage_col]).dropna().astype(str).unique()]
        else:
            stages = [None]
        for stage in stages:
            subset = df if stage is None else df[df[stage_col].astype(str) == stage]
            x, y, _ = _numeric_xy(subset, x_col, y_col)
            x_plot, y_plot = _xy_for_plot(x, y, scale, x_col)
            if not len(x_plot):
                continue
            marker = STAGE_MARKERS.get(str(stage), wb.experiment.marker) if stage is not None else wb.experiment.marker
            label = wb.experiment.label if stage is None else f"{wb.experiment.label} - {str(stage).replace('_', ' ')}"
            ax.scatter(
                x_plot,
                y_plot,
                s=18,
                color=wb.experiment.color,
                marker=marker,
                edgecolors="white" if marker not in {"x", "+"} else wb.experiment.color,
                linewidths=0.4,
                alpha=0.85,
                label=label,
            )
            handles.append(
                Line2D(
                    [0],
                    [0],
                    marker=marker,
                    color="none",
                    markerfacecolor=wb.experiment.color,
                    markeredgecolor=wb.experiment.color,
                    markersize=5,
                    label=label,
                )
            )
            labels.append(label)
    ax.set_xlabel(axis_label(x_col) + (" (log scale)" if scale == "log" else ""))
    ax.set_ylabel(axis_label(y_col))
    if scale == "log":
        ax.set_xscale("log")
    style_axes(ax)
    if scale == "log":
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)
    if handles:
        legend_above(ax, handles, labels, ncol=min(len(handles), 4), fontsize=7.0)


def plot_binned(ax, workbooks, stem, x_col, y_cols, scale):
    for wb in workbooks:
        df = wb.data
        x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(df["rate_median"], errors="coerce").to_numpy(dtype=float)
        yerr_low = y - _numeric_column_or_nan(df, "rate_p25")
        yerr_high = _numeric_column_or_nan(df, "rate_p75") - y
        mask = np.isfinite(x) & np.isfinite(y)
        if scale == "log":
            mask &= x > 0
        if not np.any(mask):
            continue
        yerr = np.vstack([yerr_low[mask], yerr_high[mask]])
        yerr = np.where(np.isfinite(yerr) & (yerr >= 0), yerr, 0.0)
        ax.errorbar(
            x[mask],
            y[mask],
            yerr=yerr,
            color=wb.experiment.color,
            linestyle=wb.experiment.linestyle,
            linewidth=LINEWIDTH,
            marker=wb.experiment.marker,
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=wb.experiment.color,
            capsize=2.0,
            label=wb.experiment.label,
        )
    ax.set_xlabel(axis_label(x_col) + (" (log scale)" if scale == "log" else ""))
    ax.set_ylabel("Median dissolution rate")
    if scale == "log":
        ax.set_xscale("log")
    style_axes(ax)
    if scale == "log":
        ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)
    legend_above(ax)


def save_figure(fig, out_dir, stem, dpi=300):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    svg = out_dir / f"{stem}.svg"
    fig.savefig(png, dpi=dpi, facecolor="white")
    fig.savefig(svg, facecolor="white")
    return [png, svg]


def write_combined_data(combined, out_dir, stem):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}_data.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        combined.to_excel(writer, sheet_name="data", index=False)
        worksheet = writer.sheets["data"]
        if len(combined.columns):
            worksheet.freeze_panes(1, 0)
        for idx, column in enumerate(combined.columns):
            width = min(max(len(str(column)) + 2, 12), 36)
            worksheet.set_column(idx, idx, width)
    return path


def create_comparison(
    experiments,
    stem,
    out_dir,
    out_stem=None,
    sheet="auto",
    x="auto",
    y="auto",
    scale=None,
    allow_missing=False,
    all_series=False,
    dpi=300,
):
    configure_nature_style()
    workbooks = load_workbooks(experiments, stem, sheet=sheet, allow_missing=allow_missing)
    reference = workbooks[0].data
    kind = infer_kind(stem, reference)
    x_col = select_x_column(stem, reference, requested=x)
    y_cols = select_y_columns(stem, reference, requested=y, all_series=all_series)

    for wb in workbooks[1:]:
        missing = [col for col in [x_col, *y_cols] if col not in wb.data.columns]
        if missing:
            raise ValueError(
                f"{wb.path} is missing required column(s) for stem '{stem}': {', '.join(missing)}"
            )

    combined = pd.concat(
        [tidy_rows_for_workbook(wb, x_col, y_cols) for wb in workbooks],
        ignore_index=True,
    )
    output_stem = out_stem or f"comparison_{stem}"
    written = [write_combined_data(combined, out_dir, output_stem)]

    for selected_scale in default_scales(kind, scale):
        fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
        if kind == "binned":
            plot_binned(ax, workbooks, stem, x_col, y_cols, selected_scale)
        elif kind == "scatter":
            plot_scatter(ax, workbooks, stem, x_col, y_cols, selected_scale)
        else:
            plot_time_series(ax, workbooks, stem, x_col, y_cols, selected_scale)
        fig.tight_layout(pad=0.6)
        suffix = "_log" if selected_scale == "log" else ""
        written.extend(save_figure(fig, out_dir, f"{output_stem}{suffix}", dpi=dpi))
        plt.close(fig)
    return written


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Compare one or more generated figure-data workbooks across experiments."
    )
    parser.add_argument("--manifest", required=True, help="CSV with label and figures_dir columns.")
    parser.add_argument(
        "--stem",
        action="append",
        required=True,
        help="Figure stem, e.g. 01_saturation_decay. Repeat or comma-separate.",
    )
    parser.add_argument(
        "--out-stem",
        default=None,
        help="Custom output filename stem. Only valid when one --stem is requested.",
    )
    parser.add_argument("--out-dir", required=True, help="Directory for comparison outputs.")
    parser.add_argument(
        "--sheet",
        default="auto",
        choices=["auto", "data", "data_all", "data_plotted"],
        help="Workbook sheet to read; auto prefers data_plotted, then data.",
    )
    parser.add_argument("--x", default="auto", help="X column, or auto.")
    parser.add_argument("--y", default="auto", help="Y column(s), comma-separated, or auto.")
    parser.add_argument(
        "--scale",
        choices=["linear", "log", "both"],
        default=None,
        help="X scale. Default: both for time-series, linear for rate/correlation.",
    )
    parser.add_argument("--allow-missing", action="store_true", help="Skip missing workbooks.")
    parser.add_argument("--all-series", action="store_true", help="Plot all numeric non-metadata y columns.")
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    experiments = load_manifest(args.manifest)
    stems = parse_csv_list(args.stem)
    if args.out_stem and len(stems) != 1:
        parser.error("--out-stem can only be used with one requested --stem")
    written = []
    for stem in stems:
        written.extend(
            create_comparison(
                experiments,
                stem,
                args.out_dir,
                out_stem=args.out_stem,
                sheet=args.sheet,
                x=args.x,
                y=args.y,
                scale=args.scale,
                allow_missing=args.allow_missing,
                all_series=args.all_series,
                dpi=args.dpi,
            )
        )
    print(f"Experiments: {len(experiments)}")
    print(f"Stems: {', '.join(stems)}")
    print(f"Output directory: {Path(args.out_dir)}")
    for path in written:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
