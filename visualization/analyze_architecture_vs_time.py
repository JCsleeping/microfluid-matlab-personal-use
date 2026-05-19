"""Frame-wise dynamic residual architecture analysis.

This post-processing script converts a Step-4 time-series CSV into an
``architecture_vs_time.csv`` table using the same score logic as the legacy
MATLAB ``classify_residual_architecture.m`` whole-state classifier.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_OUTPUT_DIR = Path(
    r"G:\微流控\17 1-BO 4UL 5% TWEEM 80 6UL WATER DISPLACE\Tween 80\output_20260428_214120"
)

ARCHITECTURE_ORDER = ("pool-like", "mixed", "ganglia-rich")
ARCHITECTURE_CODES = {name: index for index, name in enumerate(ARCHITECTURE_ORDER)}
ARCHITECTURE_COLORS = {
    "pool-like": "#D55E00",
    "mixed": "#7F7F7F",
    "ganglia-rich": "#0072B2",
}
REQUIRED_TIMESERIES_COLUMNS = (
    "Sn",
    "MaxBlobFrac",
    "NumBlobs",
    "a_i_2D",
)
OUTPUT_COLUMNS = [
    "FrameIndex",
    "Time",
    "Sn",
    "ArchitectureType",
    "PoolScore",
    "GangliaScore",
    "MaxBlobFrac",
    "NumBlobs",
    "a_i_2D",
    "ReqMedian",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "Reason",
    "RealTime_s",
    "Time_min",
    "SnNorm",
    "ValidArchitecture",
    "DissolutionRate_per_min",
]
TRANSITION_COLUMNS = [
    "From",
    "To",
    "FrameIndex",
    "Time",
    "Time_min",
    "RealTime_s",
    "Sn",
    "PreWindow_min",
    "PostWindow_min",
    "PreMedianRate",
    "PostMedianRate",
    "RateChange_PostMinusPre",
    "PreMedian_a_i_2D",
    "PostMedian_a_i_2D",
    "PreMedianMaxBlobFrac",
    "PostMedianMaxBlobFrac",
    "PreMedianNumBlobs",
    "PostMedianNumBlobs",
]
MM_PER_INCH = 25.4
INDIVIDUAL_SIZE = (89 / MM_PER_INCH, 68 / MM_PER_INCH)
STACKED_SIZE = (89 / MM_PER_INCH, 120 / MM_PER_INCH)
LINEWIDTH = 1.8


@dataclass(frozen=True)
class ArchitectureThresholds:
    pool_max_blob_frac_min: float = 0.50
    pool_num_blobs_max: float = 10.0
    pool_ai2d_max: float = 3.0e4
    ganglia_max_blob_frac_max: float = 0.30
    ganglia_num_blobs_min: float = 25.0
    ganglia_ai2d_min: float = 6.0e4


def find_latest_timeseries_csv(output_dir, explicit_csv=None):
    if explicit_csv:
        return Path(explicit_csv)
    output_dir = Path(output_dir)
    candidates = list(output_dir.glob("timeseries_realtime*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No timeseries_realtime*.csv found in {output_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def find_rates_csv(output_dir, explicit_rates_csv=None):
    if explicit_rates_csv:
        path = Path(explicit_rates_csv)
        return path if path.exists() else None
    path = Path(output_dir) / "figures_rate" / "dissolution_rates.csv"
    return path if path.exists() else None


def _numeric(df, column, default=np.nan):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _bool_series(values, default=False):
    if values is None:
        return pd.Series(default)
    if values.dtype == bool:
        return values.fillna(default).astype(bool)
    mapped = values.map(
        {
            True: True,
            False: False,
            "True": True,
            "False": False,
            "true": True,
            "false": False,
            "1": True,
            "0": False,
            1: True,
            0: False,
        }
    )
    return mapped.astype("boolean").fillna(bool(default)).astype(bool)


def load_timeseries(csv_path):
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    missing = [col for col in REQUIRED_TIMESERIES_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required time-series column(s): {', '.join(missing)}")

    df = df.copy()
    numeric_cols = set(REQUIRED_TIMESERIES_COLUMNS) | {
        "Time",
        "FrameIndex",
        "RealTime_s",
        "ReqMedian",
        "fracDroplets",
        "fracColumns",
        "fracClusters",
    }
    for column in numeric_cols:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "FrameIndex" in df.columns:
        frame_index = df["FrameIndex"]
    elif "Time" in df.columns:
        frame_index = df["Time"]
    else:
        frame_index = pd.Series(np.arange(len(df)), index=df.index)
    df["FrameIndex"] = frame_index.astype("Int64")

    if "RealTime_s" in df.columns:
        df["Time_min"] = pd.to_numeric(df["RealTime_s"], errors="coerce") / 60.0
    elif "Time_min" in df.columns:
        df["Time_min"] = pd.to_numeric(df["Time_min"], errors="coerce")
    elif "Time" in df.columns:
        df["Time_min"] = pd.to_numeric(df["Time"], errors="coerce")
    else:
        df["Time_min"] = np.arange(len(df), dtype=float)
    if "RealTime_s" not in df.columns:
        df["RealTime_s"] = df["Time_min"] * 60.0
    df["Time"] = df["Time_min"]
    return df.sort_values("Time_min", kind="mergesort").reset_index(drop=True)


def _score_bool(value):
    return bool(pd.notna(value) and np.isfinite(float(value)))


def classify_architecture_row(row, thresholds):
    max_blob = row.get("MaxBlobFrac", np.nan)
    num_blobs = row.get("NumBlobs", np.nan)
    ai2d = row.get("a_i_2D", np.nan)

    pool_hits = []
    ganglia_hits = []

    if _score_bool(max_blob) and float(max_blob) >= thresholds.pool_max_blob_frac_min:
        pool_hits.append("MaxBlobFrac high")
    if _score_bool(num_blobs) and float(num_blobs) <= thresholds.pool_num_blobs_max:
        pool_hits.append("NumBlobs low")
    if _score_bool(ai2d) and float(ai2d) <= thresholds.pool_ai2d_max:
        pool_hits.append("a_i_2D low")

    if _score_bool(max_blob) and float(max_blob) <= thresholds.ganglia_max_blob_frac_max:
        ganglia_hits.append("MaxBlobFrac low")
    if _score_bool(num_blobs) and float(num_blobs) >= thresholds.ganglia_num_blobs_min:
        ganglia_hits.append("NumBlobs high")
    if _score_bool(ai2d) and float(ai2d) >= thresholds.ganglia_ai2d_min:
        ganglia_hits.append("a_i_2D high")

    pool_score = len(pool_hits)
    ganglia_score = len(ganglia_hits)
    ai2d_finite = _score_bool(ai2d)

    if not ai2d_finite:
        if pool_score >= 2 and ganglia_score == 0:
            arch_type = "pool-like"
            rule = "a_i_2D is non-finite; pool_score >= 2 and ganglia_score == 0"
        elif ganglia_score >= 2 and pool_score == 0:
            arch_type = "ganglia-rich"
            rule = "a_i_2D is non-finite; ganglia_score >= 2 and pool_score == 0"
        else:
            arch_type = "mixed"
            rule = "a_i_2D is non-finite; neither legacy score rule was decisive"
    else:
        if pool_score >= 2 and ganglia_score <= 1:
            arch_type = "pool-like"
            rule = "pool_score >= 2 and ganglia_score <= 1"
        elif ganglia_score >= 2 and pool_score == 0:
            arch_type = "ganglia-rich"
            rule = "ganglia_score >= 2 and pool_score == 0"
        else:
            arch_type = "mixed"
            rule = "otherwise mixed"

    return {
        "ArchitectureType": arch_type,
        "PoolScore": int(pool_score),
        "GangliaScore": int(ganglia_score),
        "Reason": (
            f"pool hits={pool_hits or ['none']}; "
            f"ganglia hits={ganglia_hits or ['none']}; rule: {rule}"
        ),
    }


def compute_fallback_rate(df, window_min=20.0, min_points=5):
    time = _numeric(df, "Time_min").to_numpy(dtype=float)
    sn = _numeric(df, "Sn").to_numpy(dtype=float)
    smooth = (
        pd.Series(sn)
        .rolling(window=51, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )
    mono = np.minimum.accumulate(smooth)
    rate = np.full(len(df), np.nan, dtype=float)

    for idx, t0 in enumerate(time):
        if not np.isfinite(t0):
            continue
        mask = np.isfinite(time) & np.isfinite(mono) & (np.abs(time - t0) <= window_min / 2.0)
        if np.count_nonzero(mask) < 2:
            distances = np.abs(time - t0)
            valid_idx = np.flatnonzero(np.isfinite(distances) & np.isfinite(mono))
            if valid_idx.size >= 2:
                nearest = valid_idx[np.argsort(distances[valid_idx])[: max(2, min_points)]]
                mask = np.zeros(len(df), dtype=bool)
                mask[nearest] = True
        if np.count_nonzero(mask) >= 2:
            slope = np.polyfit(time[mask], mono[mask], 1)[0]
            rate[idx] = max(0.0, -float(slope))
    if np.isnan(rate).any() and np.isfinite(rate).any():
        valid = np.flatnonzero(np.isfinite(rate))
        rate = np.interp(np.arange(len(rate)), valid, rate[valid])
    return pd.Series(rate, index=df.index, name="DissolutionRate_per_min")


def _computed_sn_norm(df):
    sn = _numeric(df, "Sn")
    sn0_candidates = sn[np.isfinite(sn) & (sn > 0)]
    sn0 = float(sn0_candidates.iloc[0]) if not sn0_candidates.empty else np.nan
    return sn / sn0 if np.isfinite(sn0) and sn0 > 0 else pd.Series(np.nan, index=df.index)


def merge_or_compute_rates(df, output_dir, rates_csv_path, min_sn_norm_valid, min_blobs_valid):
    df = df.copy()
    rates_path = find_rates_csv(output_dir, rates_csv_path)
    rate_from_csv = None
    sn_norm_from_csv = None
    valid_from_csv = None

    if rates_path is not None:
        rates = pd.read_csv(rates_path)
        if "DissolutionRate_Sn_time_lr" in rates.columns:
            rate_from_csv = pd.to_numeric(rates["DissolutionRate_Sn_time_lr"], errors="coerce")
        if "SnNorm" in rates.columns:
            sn_norm_from_csv = pd.to_numeric(rates["SnNorm"], errors="coerce")
        if "ValidStructure" in rates.columns:
            valid_from_csv = _bool_series(rates["ValidStructure"])

        merge_cols = ["RealTime_s"]
        keep = ["RealTime_s"]
        rename = {}
        if rate_from_csv is not None:
            rates["DissolutionRate_per_min"] = rate_from_csv
            keep.append("DissolutionRate_per_min")
        if sn_norm_from_csv is not None:
            keep.append("SnNorm")
        if valid_from_csv is not None:
            rates["ValidStructure"] = valid_from_csv
            keep.append("ValidStructure")
        if all(col in df.columns for col in merge_cols) and all(col in rates.columns for col in merge_cols):
            df = df.merge(rates.loc[:, keep], on="RealTime_s", how="left")
        else:
            aligned = rates.loc[:, keep[1:]].reset_index(drop=True)
            for column in aligned.columns:
                df[column] = aligned[column].reindex(df.index).to_numpy()
        _ = rename

    computed_sn_norm = _computed_sn_norm(df)
    if "SnNorm" not in df.columns:
        df["SnNorm"] = computed_sn_norm
    else:
        df["SnNorm"] = pd.to_numeric(df["SnNorm"], errors="coerce").fillna(computed_sn_norm)

    fallback_rate = None
    if "DissolutionRate_per_min" not in df.columns:
        fallback_rate = compute_fallback_rate(df)
        df["DissolutionRate_per_min"] = fallback_rate
    else:
        rate = pd.to_numeric(df["DissolutionRate_per_min"], errors="coerce")
        if rate.isna().any():
            fallback_rate = compute_fallback_rate(df)
            rate = rate.fillna(fallback_rate)
        df["DissolutionRate_per_min"] = rate

    default_valid = (
        pd.to_numeric(df["SnNorm"], errors="coerce").ge(float(min_sn_norm_valid))
        & _numeric(df, "NumBlobs").ge(int(min_blobs_valid))
    )
    if "ValidStructure" in df.columns:
        df["ValidArchitecture"] = default_valid & _bool_series(df["ValidStructure"], default=True)
    else:
        df["ValidArchitecture"] = default_valid
    return df


def apply_architecture_classification(df, thresholds):
    rows = [classify_architecture_row(row, thresholds) for _, row in df.iterrows()]
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def prepare_architecture_dataframe(
    df,
    output_dir,
    rates_csv_path,
    thresholds,
    min_sn_norm_valid,
    min_blobs_valid,
):
    df = merge_or_compute_rates(
        df,
        output_dir=output_dir,
        rates_csv_path=rates_csv_path,
        min_sn_norm_valid=min_sn_norm_valid,
        min_blobs_valid=min_blobs_valid,
    )
    df = apply_architecture_classification(df, thresholds)
    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    return df.loc[:, OUTPUT_COLUMNS + [c for c in df.columns if c not in OUTPUT_COLUMNS]]


def _stable_runs(valid_df, min_run_frames):
    if valid_df.empty:
        return []
    labels = valid_df["ArchitectureType"].astype(str).to_numpy()
    runs = []
    start = 0
    for idx in range(1, len(labels) + 1):
        if idx == len(labels) or labels[idx] != labels[start]:
            if idx - start >= int(min_run_frames):
                runs.append((labels[start], start, idx - 1))
            start = idx
    return runs


def _median(df, column):
    if df.empty or column not in df.columns:
        return np.nan
    values = pd.to_numeric(df[column], errors="coerce")
    return float(values.median()) if values.notna().any() else np.nan


def detect_transitions(df, min_run_frames=5, window_min=20.0):
    valid = df[df["ValidArchitecture"].astype(bool)].copy().reset_index(drop=True)
    runs = _stable_runs(valid, min_run_frames)
    rows = []
    previous = None
    for current in runs:
        if previous is None:
            previous = current
            continue
        from_label, _, _ = previous
        to_label, start, _ = current
        if from_label == to_label:
            previous = current
            continue
        transition_row = valid.iloc[start]
        t0 = float(transition_row["Time_min"])
        valid_source = df[df["ValidArchitecture"].astype(bool)]
        pre = valid_source[(valid_source["Time_min"] >= t0 - window_min) & (valid_source["Time_min"] < t0)]
        post = valid_source[(valid_source["Time_min"] >= t0) & (valid_source["Time_min"] <= t0 + window_min)]
        rows.append(
            {
                "From": from_label,
                "To": to_label,
                "FrameIndex": transition_row["FrameIndex"],
                "Time": transition_row["Time"],
                "Time_min": t0,
                "RealTime_s": transition_row["RealTime_s"],
                "Sn": transition_row["Sn"],
                "PreWindow_min": float(window_min),
                "PostWindow_min": float(window_min),
                "PreMedianRate": _median(pre, "DissolutionRate_per_min"),
                "PostMedianRate": _median(post, "DissolutionRate_per_min"),
                "RateChange_PostMinusPre": _median(post, "DissolutionRate_per_min")
                - _median(pre, "DissolutionRate_per_min"),
                "PreMedian_a_i_2D": _median(pre, "a_i_2D"),
                "PostMedian_a_i_2D": _median(post, "a_i_2D"),
                "PreMedianMaxBlobFrac": _median(pre, "MaxBlobFrac"),
                "PostMedianMaxBlobFrac": _median(post, "MaxBlobFrac"),
                "PreMedianNumBlobs": _median(pre, "NumBlobs"),
                "PostMedianNumBlobs": _median(post, "NumBlobs"),
            }
        )
        previous = current
    return pd.DataFrame(rows, columns=TRANSITION_COLUMNS)


def create_rate_summary(df):
    valid = df[df["ValidArchitecture"].astype(bool)]
    rows = []
    for label in ARCHITECTURE_ORDER:
        subset = valid[valid["ArchitectureType"] == label]
        rows.append(
            {
                "ArchitectureType": label,
                "n": int(len(subset)),
                "MedianRate": _median(subset, "DissolutionRate_per_min"),
                "RateP25": float(subset["DissolutionRate_per_min"].quantile(0.25))
                if not subset.empty
                else np.nan,
                "RateP75": float(subset["DissolutionRate_per_min"].quantile(0.75))
                if not subset.empty
                else np.nan,
                "Median_a_i_2D": _median(subset, "a_i_2D"),
                "MedianMaxBlobFrac": _median(subset, "MaxBlobFrac"),
                "MedianNumBlobs": _median(subset, "NumBlobs"),
            }
        )
    return pd.DataFrame(rows)


def rate_distribution_groups(df):
    """Valid positive-rate groups for the architecture rate distribution plot."""
    valid = df[df["ValidArchitecture"].astype(bool)].copy()
    groups = []
    for label in ARCHITECTURE_ORDER:
        subset = valid[valid["ArchitectureType"] == label]
        values = pd.to_numeric(subset["DissolutionRate_per_min"], errors="coerce")
        values = values[np.isfinite(values) & (values > 0)].to_numpy(dtype=float)
        if values.size == 0:
            continue
        groups.append(
            {
                "architecture": label,
                "label": f"{label}\nn={values.size}",
                "values": values,
            }
        )
    return groups


def _row_snapshot(row):
    if row is None or len(row) == 0:
        return None
    fields = ["FrameIndex", "Time_min", "RealTime_s", "Sn", "SnNorm", "ArchitectureType", "DissolutionRate_per_min"]
    return {field: _json_default(row[field]) for field in fields if field in row.index}


def create_summary(df, transitions):
    valid = df[df["ValidArchitecture"].astype(bool)]
    first_pool_to_mixed = transitions[
        (transitions["From"] == "pool-like") & (transitions["To"] == "mixed")
    ]
    first_ganglia = valid[valid["ArchitectureType"] == "ganglia-rich"]
    finite_rate = valid[np.isfinite(pd.to_numeric(valid["DissolutionRate_per_min"], errors="coerce"))]
    peak_rate_row = None if finite_rate.empty else finite_rate.loc[finite_rate["DissolutionRate_per_min"].idxmax()]

    late_high_ai2d_low_rate = {
        "matched": False,
        "n": 0,
        "late_sn_norm_max": 0.25,
        "high_ai2d_threshold": np.nan,
        "low_rate_threshold": np.nan,
    }
    if not valid.empty:
        ai = pd.to_numeric(valid["a_i_2D"], errors="coerce")
        rate = pd.to_numeric(valid["DissolutionRate_per_min"], errors="coerce")
        high_ai = float(ai.quantile(0.75)) if ai.notna().any() else np.nan
        low_rate = float(rate.quantile(0.25)) if rate.notna().any() else np.nan
        late_mask = pd.to_numeric(valid["SnNorm"], errors="coerce") <= 0.25
        matched = late_mask & (ai >= high_ai) & (rate <= low_rate)
        late_high_ai2d_low_rate = {
            "matched": bool(matched.any()),
            "n": int(matched.sum()),
            "late_sn_norm_max": 0.25,
            "high_ai2d_threshold": high_ai,
            "low_rate_threshold": low_rate,
        }

    return {
        "thresholds": None,
        "n_rows": int(len(df)),
        "n_valid_architecture": int(len(valid)),
        "architecture_counts": df["ArchitectureType"].value_counts(dropna=False).to_dict(),
        "valid_architecture_counts": valid["ArchitectureType"].value_counts(dropna=False).to_dict(),
        "first_pool_like_to_mixed": None
        if first_pool_to_mixed.empty
        else first_pool_to_mixed.iloc[0].to_dict(),
        "first_ganglia_rich": None if first_ganglia.empty else _row_snapshot(first_ganglia.iloc[0]),
        "peak_rate": _row_snapshot(peak_rate_row),
        "late_high_ai2d_low_rate": late_high_ai2d_low_rate,
    }


def configure_style():
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


def style_twin_axis(ax):
    style_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(True)
    ax.spines["right"].set_linewidth(0.9)
    ax.spines["right"].set_color("#2B2B2B")
    ax.grid(False)
    return ax


def legend_above(ax, handles=None, labels=None, ncol=None):
    if handles is None or labels is None:
        handles, labels = ax.get_legend_handles_labels()
    pairs = [(handle, label) for handle, label in zip(handles, labels) if label and not label.startswith("_")]
    if not pairs:
        return None
    handles, labels = zip(*pairs)
    return ax.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.04),
        ncol=ncol or min(len(labels), 3),
        frameon=False,
        handlelength=1.6,
        handletextpad=0.4,
        columnspacing=1.2,
        borderaxespad=0.0,
    )


def _save(fig, figures_dir, stem, dpi):
    figures_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ("png", "svg"):
        path = figures_dir / f"{stem}.{suffix}"
        if suffix == "png":
            fig.savefig(path, dpi=dpi, facecolor="white")
        else:
            fig.savefig(path, facecolor="white")
        paths.append(path)
    return paths


def _add_transition_lines(ax, transitions):
    for _, row in transitions.iterrows():
        ax.axvline(row["Time_min"], color="#555555", linewidth=0.7, linestyle="--", alpha=0.7)


def plot_architecture_timeline(df, transitions, figures_dir, dpi):
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    for label in ARCHITECTURE_ORDER:
        subset = df[(df["ArchitectureType"] == label) & df["ValidArchitecture"].astype(bool)]
        ax.scatter(
            subset["Time_min"],
            [ARCHITECTURE_CODES[label]] * len(subset),
            s=5,
            color=ARCHITECTURE_COLORS[label],
            label=label,
            alpha=0.75,
        )
    invalid = df[~df["ValidArchitecture"].astype(bool)]
    if not invalid.empty:
        ax.scatter(invalid["Time_min"], [-0.45] * len(invalid), s=4, color="#CCCCCC", alpha=0.5)
    ax.set_yticks(list(ARCHITECTURE_CODES.values()))
    ax.set_yticklabels(list(ARCHITECTURE_CODES.keys()))
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Architecture")
    _add_transition_lines(ax, transitions)
    ax2 = ax.twinx()
    ax2.plot(df["Time_min"], df["SnNorm"], color="#000000", linewidth=LINEWIDTH, alpha=0.7, label="Sn/Sn0")
    ax2.set_ylabel("Sn/Sn0")
    style_axes(ax)
    style_twin_axis(ax2)
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    legend_above(ax, handles + handles2, labels + labels2, ncol=2)
    fig.tight_layout(pad=0.6)
    paths = _save(fig, figures_dir, "01_architecture_timeline", dpi)
    plt.close(fig)
    return paths


def plot_architecture_indicators(df, transitions, figures_dir, dpi):
    metrics = [
        ("MaxBlobFrac", "Largest blob fraction"),
        ("NumBlobs", "Number of blobs"),
        ("a_i_2D", r"$a_i^{2D}$"),
    ]
    fig, axes = plt.subplots(3, 1, figsize=STACKED_SIZE, sharex=True)
    for ax, (column, label) in zip(axes, metrics):
        ax.plot(df["Time_min"], df[column], color="#333333", linewidth=LINEWIDTH)
        _add_transition_lines(ax, transitions)
        ax.set_ylabel(label)
        style_axes(ax)
    axes[-1].set_xlabel("Time (min)")
    fig.tight_layout(pad=0.6)
    paths = _save(fig, figures_dir, "02_architecture_indicators", dpi)
    plt.close(fig)
    return paths


def plot_rate_by_architecture(df, figures_dir, dpi):
    groups = rate_distribution_groups(df)
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    if groups:
        data = [group["values"] for group in groups]
        positions = np.arange(1, len(groups) + 1)
        violins = ax.violinplot(
            data,
            positions=positions,
            widths=0.62,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )
        for body, group in zip(violins["bodies"], groups):
            body.set_facecolor(ARCHITECTURE_COLORS[group["architecture"]])
            body.set_edgecolor("none")
            body.set_alpha(0.28)
            body.set_zorder(1)

        rng = np.random.default_rng(7)
        for pos, group in zip(positions, groups):
            values = np.sort(group["values"])
            if values.size > 450:
                sample_idx = np.linspace(0, values.size - 1, 450).astype(int)
                sample = values[sample_idx]
            else:
                sample = values
            jitter = rng.uniform(-0.16, 0.16, size=sample.size)
            ax.scatter(
                pos + jitter,
                sample,
                s=3.5,
                color="#333333",
                alpha=0.16,
                linewidths=0,
                rasterized=True,
                zorder=2,
            )

            q25, q50, q75 = np.percentile(values, [25, 50, 75])
            ax.vlines(pos, q25, q75, color="#000000", linewidth=1.1, zorder=4)
            ax.hlines(q50, pos - 0.20, pos + 0.20, color="#000000", linewidth=1.3, zorder=5)

        ax.set_xticks(positions)
        ax.set_xticklabels([group["label"] for group in groups], rotation=0)
        ax.set_yscale("log")
    else:
        ax.text(0.5, 0.5, "No valid rate data", transform=ax.transAxes, ha="center", va="center")
    style_axes(ax)
    ax.set_ylabel(r"$-dS_n/dt$ (min$^{-1}$)")
    fig.tight_layout(pad=0.6)
    paths = _save(fig, figures_dir, "03_rate_by_architecture", dpi)
    plt.close(fig)
    return paths


def plot_rate_vs_ai2d_by_architecture(df, figures_dir, dpi):
    valid = df[df["ValidArchitecture"].astype(bool)]
    fig, ax = plt.subplots(figsize=INDIVIDUAL_SIZE)
    for label in ARCHITECTURE_ORDER:
        subset = valid[valid["ArchitectureType"] == label]
        ax.scatter(
            subset["a_i_2D"],
            subset["DissolutionRate_per_min"],
            s=8,
            color=ARCHITECTURE_COLORS[label],
            alpha=0.7,
            label=label,
        )
    ax.axhline(0, color="#999999", linewidth=0.7, linestyle="--")
    ax.set_xlabel(r"$a_i^{2D}$")
    ax.set_ylabel(r"$-dS_n/dt$ (min$^{-1}$)")
    style_axes(ax)
    legend_above(ax, ncol=3)
    fig.tight_layout(pad=0.6)
    paths = _save(fig, figures_dir, "04_rate_vs_ai2d_by_architecture", dpi)
    plt.close(fig)
    return paths


def create_all_figures(df, transitions, figures_dir, dpi=300):
    configure_style()
    figures_dir = Path(figures_dir)
    written = []
    written.extend(plot_architecture_timeline(df, transitions, figures_dir, dpi))
    written.extend(plot_architecture_indicators(df, transitions, figures_dir, dpi))
    written.extend(plot_rate_by_architecture(df, figures_dir, dpi))
    written.extend(plot_rate_vs_ai2d_by_architecture(df, figures_dir, dpi))
    return written


def analyze_architecture(
    timeseries_csv,
    postprocess_dir,
    dpi=300,
    no_figures=False,
    rate_window_min=20.0,
    rate_min_points=25,
):
    """Write architecture Level A outputs for the batch postprocess driver."""
    _ = rate_window_min, rate_min_points
    postprocess_dir = Path(postprocess_dir)
    postprocess_dir.mkdir(parents=True, exist_ok=True)
    thresholds = ArchitectureThresholds()
    df = load_timeseries(timeseries_csv)
    architecture_df = prepare_architecture_dataframe(
        df,
        output_dir=postprocess_dir,
        rates_csv_path=None,
        thresholds=thresholds,
        min_sn_norm_valid=0.05,
        min_blobs_valid=20,
    )
    transitions = detect_transitions(architecture_df, min_run_frames=5, window_min=20.0)
    rate_summary = create_rate_summary(architecture_df)
    summary = create_summary(architecture_df, transitions)
    summary["thresholds"] = asdict(thresholds)

    architecture_df.loc[:, OUTPUT_COLUMNS].to_csv(postprocess_dir / "architecture_vs_time.csv", index=False)
    transitions.to_csv(postprocess_dir / "architecture_transitions.csv", index=False)
    rate_summary.to_csv(postprocess_dir / "architecture_rate_summary.csv", index=False)
    with (postprocess_dir / "architecture_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False, default=_json_default)

    figure_paths = []
    if not no_figures:
        figure_paths = create_all_figures(
            architecture_df,
            transitions,
            postprocess_dir / "figures_architecture_time",
            dpi=dpi,
        )

    return {
        "architecture": architecture_df,
        "transitions": transitions,
        "rate_summary": rate_summary,
        "summary": summary,
        "figures": figure_paths,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Analyze residual architecture vs time.")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Pipeline output directory containing timeseries_realtime*.csv.",
    )
    parser.add_argument("--csv", dest="csv_path", help="Explicit time-series CSV path.")
    parser.add_argument("--rates-csv", dest="rates_csv_path", help="Explicit dissolution_rates.csv path.")
    parser.add_argument("--figures-dir", help="Figure output directory.")
    parser.add_argument("--dpi", type=int, default=300, help="PNG output DPI.")
    parser.add_argument("--min-sn-norm-valid", type=float, default=0.05)
    parser.add_argument("--min-blobs-valid", type=int, default=20)
    parser.add_argument("--transition-min-run-frames", type=int, default=5)
    parser.add_argument("--transition-window-min", type=float, default=20.0)
    parser.add_argument("--pool-max-blob-frac-min", type=float, default=0.50)
    parser.add_argument("--pool-num-blobs-max", type=float, default=10.0)
    parser.add_argument("--pool-ai2d-max", type=float, default=3.0e4)
    parser.add_argument("--ganglia-max-blob-frac-max", type=float, default=0.30)
    parser.add_argument("--ganglia-num-blobs-min", type=float, default=25.0)
    parser.add_argument("--ganglia-ai2d-min", type=float, default=6.0e4)
    return parser


def thresholds_from_args(args):
    return ArchitectureThresholds(
        pool_max_blob_frac_min=args.pool_max_blob_frac_min,
        pool_num_blobs_max=args.pool_num_blobs_max,
        pool_ai2d_max=args.pool_ai2d_max,
        ganglia_max_blob_frac_max=args.ganglia_max_blob_frac_max,
        ganglia_num_blobs_min=args.ganglia_num_blobs_min,
        ganglia_ai2d_min=args.ganglia_ai2d_min,
    )


def _json_default(obj):
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd._libs.missing.NAType):
        return None
    if pd.isna(obj) if not isinstance(obj, (dict, list, tuple)) else False:
        return None
    return obj


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    csv_path = find_latest_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figures_architecture_time"

    if args.transition_min_run_frames < 1:
        raise ValueError("--transition-min-run-frames must be >= 1")
    if args.transition_window_min <= 0:
        raise ValueError("--transition-window-min must be positive")

    thresholds = thresholds_from_args(args)
    df = load_timeseries(csv_path)
    architecture_df = prepare_architecture_dataframe(
        df,
        output_dir=output_dir,
        rates_csv_path=args.rates_csv_path,
        thresholds=thresholds,
        min_sn_norm_valid=args.min_sn_norm_valid,
        min_blobs_valid=args.min_blobs_valid,
    )
    transitions = detect_transitions(
        architecture_df,
        min_run_frames=args.transition_min_run_frames,
        window_min=args.transition_window_min,
    )
    rate_summary = create_rate_summary(architecture_df)
    summary = create_summary(architecture_df, transitions)
    summary["thresholds"] = asdict(thresholds)

    arch_csv = output_dir / "architecture_vs_time.csv"
    transitions_csv = output_dir / "architecture_transitions.csv"
    rate_summary_csv = output_dir / "architecture_rate_summary.csv"
    summary_json = output_dir / "architecture_summary.json"

    architecture_df.loc[:, OUTPUT_COLUMNS].to_csv(arch_csv, index=False)
    transitions.to_csv(transitions_csv, index=False)
    rate_summary.to_csv(rate_summary_csv, index=False)
    with open(summary_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False, default=_json_default)

    figure_paths = create_all_figures(architecture_df, transitions, figures_dir, dpi=args.dpi)

    print(f"Read: {csv_path}")
    print(f"Rows: {len(architecture_df)}")
    print(f"Architecture counts: {architecture_df['ArchitectureType'].value_counts().to_dict()}")
    print(f"Saved: {arch_csv}")
    print(f"Saved: {transitions_csv}")
    print(f"Saved: {rate_summary_csv}")
    print(f"Saved: {summary_json}")
    for path in figure_paths:
        print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
