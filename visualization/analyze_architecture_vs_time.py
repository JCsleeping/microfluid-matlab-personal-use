from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import (  # noqa: E402
    add_sn_derived_columns,
    assign_level_a_stage,
    compute_rate_per_min,
    ensure_dir,
    numeric_series,
    prepare_time_columns,
    save_figure,
)


class ArchitectureThresholds:
    def __init__(
        self,
        pool_max_blob_frac_min=0.50,
        pool_num_blobs_max=10.0,
        pool_ai2d_max=3.0e4,
        ganglia_max_blob_frac_max=0.30,
        ganglia_num_blobs_min=25.0,
        ganglia_ai2d_min=6.0e4,
    ):
        self.pool_max_blob_frac_min = pool_max_blob_frac_min
        self.pool_num_blobs_max = pool_num_blobs_max
        self.pool_ai2d_max = pool_ai2d_max
        self.ganglia_max_blob_frac_max = ganglia_max_blob_frac_max
        self.ganglia_num_blobs_min = ganglia_num_blobs_min
        self.ganglia_ai2d_min = ganglia_ai2d_min


OUTPUT_COLUMNS = [
    "FrameIndex",
    "Time",
    "RealTime_s",
    "Time_min",
    "Sn",
    "SnNorm",
    "RemovalFraction",
    "DissolutionRate_Sn_per_min",
    "Stage",
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
]


def classify_architecture_row(row, thresholds=None):
    if thresholds is None:
        thresholds = ArchitectureThresholds()
    max_blob_fraction = float(pd.to_numeric(row.get("MaxBlobFrac", np.nan), errors="coerce"))
    num_blobs = float(pd.to_numeric(row.get("NumBlobs", np.nan), errors="coerce"))
    ai2d = float(pd.to_numeric(row.get("a_i_2D", np.nan), errors="coerce"))

    pool_score = 0
    pool_score += int(np.isfinite(max_blob_fraction) and max_blob_fraction >= thresholds.pool_max_blob_frac_min)
    pool_score += int(np.isfinite(num_blobs) and num_blobs <= thresholds.pool_num_blobs_max)
    pool_score += int(np.isfinite(ai2d) and ai2d <= thresholds.pool_ai2d_max)

    ganglia_score = 0
    ganglia_score += int(np.isfinite(max_blob_fraction) and max_blob_fraction <= thresholds.ganglia_max_blob_frac_max)
    ganglia_score += int(np.isfinite(num_blobs) and num_blobs >= thresholds.ganglia_num_blobs_min)
    ganglia_score += int(np.isfinite(ai2d) and ai2d >= thresholds.ganglia_ai2d_min)

    if not np.isfinite(ai2d):
        if pool_score >= 2 and ganglia_score == 0:
            arch_type = "pool-like"
        elif ganglia_score >= 2 and pool_score == 0:
            arch_type = "ganglia-rich"
        else:
            arch_type = "mixed"
        reason = "a_i_2D is non-finite; used MATLAB fallback branch"
    else:
        if pool_score >= 2 and ganglia_score <= 1:
            arch_type = "pool-like"
        elif ganglia_score >= 2 and pool_score == 0:
            arch_type = "ganglia-rich"
        else:
            arch_type = "mixed"
        reason = "pool_score >= 2" if arch_type == "pool-like" else (
            "ganglia_score >= 2" if arch_type == "ganglia-rich" else "mixed score pattern"
        )

    return {
        "ArchitectureType": arch_type,
        "PoolScore": int(pool_score),
        "GangliaScore": int(ganglia_score),
        "Reason": reason,
    }


def load_timeseries(csv_path, rate_window_min=20.0, rate_min_points=25):
    df = pd.read_csv(csv_path)
    df = prepare_time_columns(df)
    df = add_sn_derived_columns(df)
    df["DissolutionRate_Sn_per_min"] = compute_rate_per_min(
        df["Time_min"],
        numeric_series(df, "Sn"),
        rate_window_min=rate_window_min,
        min_points=rate_min_points,
        monotone=True,
    )
    df["Stage"] = assign_level_a_stage(df["SnNorm"])
    return df


def prepare_architecture_dataframe(timeseries, thresholds=None):
    if thresholds is None:
        thresholds = ArchitectureThresholds()
    df = timeseries.copy()
    for column in ["Sn", "MaxBlobFrac", "NumBlobs", "a_i_2D", "ReqMedian", "fracDroplets", "fracColumns", "fracClusters"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        else:
            df[column] = np.nan
    scored = df.apply(lambda row: classify_architecture_row(row, thresholds), axis=1, result_type="expand")
    df = pd.concat([df, scored], axis=1)
    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    return df.loc[:, OUTPUT_COLUMNS]


def detect_transitions(df):
    rows = []
    prev = None
    for _, row in df.iterrows():
        current = row.get("ArchitectureType")
        if pd.isna(current):
            continue
        if prev is None:
            prev = current
            continue
        if current != prev:
            rows.append(
                {
                    "From": prev,
                    "To": current,
                    "FrameIndex": row.get("FrameIndex"),
                    "Time_min": row.get("Time_min"),
                    "Sn": row.get("Sn"),
                    "DissolutionRate_Sn_per_min": row.get("DissolutionRate_Sn_per_min"),
                }
            )
            prev = current
    return pd.DataFrame(rows, columns=["From", "To", "FrameIndex", "Time_min", "Sn", "DissolutionRate_Sn_per_min"])


def create_rate_summary(df):
    rows = []
    for group_col in ["ArchitectureType", "Stage"]:
        for label, sub in df.groupby(group_col, dropna=False):
            rate = pd.to_numeric(sub["DissolutionRate_Sn_per_min"], errors="coerce")
            rows.append(
                {
                    "GroupType": group_col,
                    "Group": label,
                    "N": int(len(sub)),
                    "MedianRate_per_min": float(np.nanmedian(rate)) if rate.notna().any() else np.nan,
                    "MeanRate_per_min": float(np.nanmean(rate)) if rate.notna().any() else np.nan,
                    "MedianSnNorm": float(np.nanmedian(sub["SnNorm"])) if sub["SnNorm"].notna().any() else np.nan,
                }
            )
    return pd.DataFrame(rows)


def create_figures(df, transitions, figures_dir, dpi=300):
    paths = []
    figures_dir = ensure_dir(figures_dir)

    fig, ax = plt.subplots(figsize=(7, 4))
    for label, sub in df.groupby("ArchitectureType"):
        ax.scatter(sub["Time_min"], sub["SnNorm"], s=12, label=label)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("SnNorm")
    ax.legend(frameon=False, fontsize=8)
    paths.extend(save_figure(fig, figures_dir, "01_architecture_timeline", dpi))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(df["Time_min"], df["MaxBlobFrac"], label="MaxBlobFrac")
    ax.plot(df["Time_min"], df["NumBlobs"] / np.nanmax(df["NumBlobs"]), label="NumBlobs normalized")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Architecture indicators")
    ax.legend(frameon=False, fontsize=8)
    paths.extend(save_figure(fig, figures_dir, "02_architecture_indicators", dpi))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(df["a_i_2D"], df["DissolutionRate_Sn_per_min"], c=df["SnNorm"], s=14)
    ax.set_xlabel("a_i_2D")
    ax.set_ylabel("-dSn/dt (per min)")
    paths.extend(save_figure(fig, figures_dir, "03_rate_vs_ai2d_by_architecture", dpi))
    return paths


def analyze_architecture(timeseries_csv, postprocess_dir, dpi=300, no_figures=False, rate_window_min=20.0, rate_min_points=25):
    postprocess_dir = ensure_dir(postprocess_dir)
    df = prepare_architecture_dataframe(
        load_timeseries(timeseries_csv, rate_window_min=rate_window_min, rate_min_points=rate_min_points)
    )
    transitions = detect_transitions(df)
    summary = create_rate_summary(df)

    df.to_csv(postprocess_dir / "architecture_vs_time.csv", index=False)
    transitions.to_csv(postprocess_dir / "architecture_transitions.csv", index=False)
    summary.to_csv(postprocess_dir / "architecture_rate_summary.csv", index=False)

    figures = []
    if not no_figures:
        figures = create_figures(df, transitions, postprocess_dir / "figures_architecture_time", dpi=dpi)
    else:
        ensure_dir(postprocess_dir / "figures_architecture_time")

    return {"architecture": df, "transitions": transitions, "rate_summary": summary, "figures": figures}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze residual architecture vs time.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--timeseries-csv", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--rate-window-min", type=float, default=20.0)
    parser.add_argument("--rate-min-points", type=int, default=25)
    args = parser.parse_args(argv)
    analyze_architecture(
        args.timeseries_csv,
        args.postprocess_dir,
        dpi=args.dpi,
        no_figures=args.no_figures,
        rate_window_min=args.rate_window_min,
        rate_min_points=args.rate_min_points,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
