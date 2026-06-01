"""Trim comparison workbooks to the post-onset saturation decay segment."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


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

Y_LABELS = {
    "SnNorm": "Sn/Sn0",
    "Sn": "Saturation, Sn",
    "Y": "Value",
}


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


def legend_above(ax):
    handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return
    ax.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=max(1, len(handles)),
        frameon=False,
        handlelength=1.2,
        handletextpad=0.4,
        columnspacing=1.0,
        borderaxespad=0.0,
    )


def read_input_workbook(path, sheet_name="data"):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with pd.ExcelFile(path) as xls:
        sheet = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(xls, sheet_name=sheet), sheet


def _first_consecutive_true(mask, min_consecutive):
    min_consecutive = max(1, int(min_consecutive))
    run = 0
    for idx, value in enumerate(mask):
        if bool(value):
            run += 1
            if run >= min_consecutive:
                return idx - min_consecutive + 1
        else:
            run = 0
    return None


def _first_onset_x(group, x_col, onset_col, threshold, min_consecutive):
    detect = group[[x_col]].copy()
    detect[x_col] = pd.to_numeric(detect[x_col], errors="coerce")
    if onset_col in group.columns:
        detect[onset_col] = pd.to_numeric(group[onset_col], errors="coerce")
        signal_name = onset_col
    else:
        detect[onset_col] = np.nan
        signal_name = "missing"
    detect = detect.sort_values(x_col, kind="mergesort")
    if not np.any(np.isfinite(detect[onset_col])) and "Sn" in group.columns:
        sn = pd.to_numeric(group.loc[detect.index, "Sn"], errors="coerce").to_numpy(dtype=float)
        finite_sn = sn[np.isfinite(sn)]
        if len(finite_sn) and finite_sn[0] != 0:
            detect[onset_col] = sn / finite_sn[0]
            signal_name = "Sn_normalized"
    detect = detect[np.isfinite(detect[x_col]) & np.isfinite(detect[onset_col])]
    if detect.empty:
        return np.nan, False, signal_name
    detect = detect.drop_duplicates(subset=[x_col])
    below = detect[onset_col].to_numpy(dtype=float) <= float(threshold)
    start = _first_consecutive_true(below, min_consecutive)
    if start is None:
        return float(detect[x_col].iloc[0]), False, signal_name
    return float(detect[x_col].iloc[start]), True, signal_name


def _label_column(df):
    if "ExperimentLabel" in df.columns:
        return "ExperimentLabel"
    return None


def trim_to_onset(
    df,
    threshold=0.98,
    min_consecutive=5,
    x_col="PV",
    onset_col="SnNorm",
):
    if x_col not in df.columns:
        raise ValueError(f"Input workbook must contain {x_col!r}.")
    if onset_col not in df.columns:
        if "Y" in df.columns and "SeriesName" in df.columns:
            series_names = df["SeriesName"].dropna().unique()
            if len(series_names) == 1 and str(series_names[0]).strip() == onset_col:
                df = df.copy()
                df[onset_col] = df["Y"]
            else:
                raise ValueError(
                    f"Input workbook does not contain {onset_col!r} for onset detection.\n"
                    f"  Available Y series: {[str(s) for s in series_names]}\n"
                    f"  Use --onset-col to specify which column/series to use, or ensure\n"
                    f"  the comparison workbook was generated with --y {onset_col}."
                )
        elif "Y" in df.columns and "SeriesName" not in df.columns:
            df = df.copy()
            df[onset_col] = df["Y"]
        else:
            raise ValueError(
                f"Input workbook must contain {onset_col!r} for onset detection."
            )
    if "Y" not in df.columns:
        raise ValueError("Input workbook must contain plotted value column 'Y'.")

    label_col = _label_column(df)
    working = df.copy()
    if label_col is None:
        label_col = "ExperimentLabel"
        working[label_col] = "Series"

    trimmed_groups = []
    metadata_rows = []
    for label, group in working.groupby(label_col, sort=False, dropna=False):
        group = group.copy()
        group[x_col] = pd.to_numeric(group[x_col], errors="coerce")
        group = group.sort_values(x_col, kind="mergesort")
        original_rows = int(len(group))
        onset_x, found, signal_name = _first_onset_x(group, x_col, onset_col, threshold, min_consecutive)
        if np.isfinite(onset_x):
            keep = group[x_col] >= onset_x
            kept = group.loc[keep].copy()
        else:
            kept = group.copy()
        trimmed_rows = original_rows - int(len(kept))
        kept["PV_original"] = kept[x_col]
        kept["PV_onset"] = onset_x
        kept["PV_since_onset"] = kept[x_col] - onset_x if np.isfinite(onset_x) else np.nan
        kept["OnsetFound"] = bool(found)
        kept["TrimmedRows"] = trimmed_rows
        kept["OnsetThreshold"] = float(threshold)
        kept["OnsetMinConsecutive"] = int(min_consecutive)
        kept["OnsetSignal"] = signal_name
        kept["X"] = kept["PV_since_onset"]
        trimmed_groups.append(kept)
        metadata_rows.append(
            {
                "ExperimentLabel": label,
                "OnsetFound": bool(found),
                "PV_onset": onset_x,
                "OnsetThreshold": float(threshold),
                "OnsetMinConsecutive": int(min_consecutive),
                "OnsetSignal": signal_name,
                "OriginalRows": original_rows,
                "RowsKept": int(len(kept)),
                "TrimmedRows": trimmed_rows,
                "PV_min_original": float(np.nanmin(group[x_col])) if np.any(np.isfinite(group[x_col])) else np.nan,
                "PV_max_original": float(np.nanmax(group[x_col])) if np.any(np.isfinite(group[x_col])) else np.nan,
            }
        )

    trimmed = pd.concat(trimmed_groups, ignore_index=True) if trimmed_groups else working.iloc[0:0].copy()
    metadata = pd.DataFrame(metadata_rows)
    first_cols = [
        "ExperimentLabel",
        "SourceWorkbook",
        "SourceSheet",
        "SeriesName",
        "X",
        "Y",
        "PV_since_onset",
        "PV_original",
        "PV_onset",
        "OnsetFound",
        "TrimmedRows",
    ]
    existing_first = [col for col in first_cols if col in trimmed.columns]
    remaining = [col for col in trimmed.columns if col not in existing_first]
    return trimmed[existing_first + remaining], metadata


def xy_for_plot(df, scale="linear", x_col="PV_since_onset", y_col="Y"):
    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if scale == "log":
        mask &= x > 0
    return x[mask], y[mask]


def _series_name(df):
    if "SeriesName" in df.columns:
        values = pd.Series(df["SeriesName"]).dropna().astype(str).unique()
        if len(values) == 1:
            return values[0]
    return "Y"


def axis_label_for_y(series_name):
    return Y_LABELS.get(series_name, str(series_name).replace("_", " "))


def plot_trimmed(ax, df, scale):
    labels = pd.Series(df["ExperimentLabel"]).dropna().astype(str).unique()
    for idx, label in enumerate(labels):
        subset = df[df["ExperimentLabel"].astype(str) == label]
        x, y = xy_for_plot(subset, scale=scale)
        if not len(x):
            continue
        color = COLOR_CYCLE[idx % len(COLOR_CYCLE)]
        marker = MARKER_CYCLE[idx % len(MARKER_CYCLE)]
        linestyle = LINESTYLE_CYCLE[idx % len(LINESTYLE_CYCLE)]
        ax.plot(
            x,
            y,
            color=color,
            linestyle=linestyle,
            linewidth=LINEWIDTH,
            marker=marker,
            markersize=MARKER_SIZE,
            markerfacecolor="white",
            markeredgecolor=color,
            markeredgewidth=1.0,
            markevery=max(1, len(x) // 20),
            label=label,
        )
    ax.set_xlabel("PV since onset" + (" (log scale)" if scale == "log" else ""))
    ax.set_ylabel(axis_label_for_y(_series_name(df)))
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
    plt.close(fig)
    return [png, svg]


def write_output_workbook(trimmed, metadata, out_dir, out_stem):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{out_stem}_data.xlsx"
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        trimmed.to_excel(writer, sheet_name="data", index=False)
        metadata.to_excel(writer, sheet_name="onset_metadata", index=False)
        for sheet_name, frame in {"data": trimmed, "onset_metadata": metadata}.items():
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            for idx, column in enumerate(frame.columns):
                width = min(max(len(str(column)) + 2, 12), 38)
                worksheet.set_column(idx, idx, width)
    return path


def default_out_stem(workbook_path):
    stem = Path(workbook_path).stem
    if stem.endswith("_data"):
        stem = stem[: -len("_data")]
    return f"{stem}_onset_pv0"


def create_onset_aligned_outputs(
    workbook_path,
    out_dir=None,
    out_stem=None,
    threshold=0.98,
    onset_col="SnNorm",
    min_consecutive=5,
    sheet_name="data",
    dpi=300,
):
    configure_nature_style()
    workbook_path = Path(workbook_path)
    df, _ = read_input_workbook(workbook_path, sheet_name=sheet_name)
    out_dir = Path(out_dir) if out_dir is not None else workbook_path.parent
    out_stem = out_stem or default_out_stem(workbook_path)
    trimmed, metadata = trim_to_onset(
        df, threshold=threshold, min_consecutive=min_consecutive, onset_col=onset_col
    )
    workbook_out = write_output_workbook(trimmed, metadata, out_dir, out_stem)

    written = [workbook_out]
    for scale, suffix in [("linear", ""), ("log", "_log")]:
        fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
        plot_trimmed(ax, trimmed, scale=scale)
        written.extend(save_figure(fig, out_dir, f"{out_stem}{suffix}", dpi=dpi))
    return written


def build_parser():
    parser = argparse.ArgumentParser(
        description="Trim a comparison data workbook to post-onset decay and redraw PV-since-onset figures."
    )
    parser.add_argument("workbook", help="Existing comparison *_data.xlsx workbook.")
    parser.add_argument("--out-dir", default=None, help="Output directory. Default: input workbook directory.")
    parser.add_argument("--out-stem", default=None, help="Output filename stem. Default: input stem + _onset_pv0.")
    parser.add_argument("--threshold", type=float, default=0.98, help="Onset threshold on the onset signal.")
    parser.add_argument(
        "--onset-col",
        default="SnNorm",
        help="Column used for onset detection (default: SnNorm). Falls back to Y if SeriesName matches.",
    )
    parser.add_argument(
        "--min-consecutive",
        type=int,
        default=5,
        help="Number of consecutive points at or below threshold required for onset.",
    )
    parser.add_argument("--sheet", default="data", help="Input workbook sheet name. Default: data.")
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    create_onset_aligned_outputs(
        args.workbook,
        out_dir=args.out_dir,
        out_stem=args.out_stem,
        threshold=args.threshold,
        onset_col=args.onset_col,
        min_consecutive=args.min_consecutive,
        sheet_name=args.sheet,
        dpi=args.dpi,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
