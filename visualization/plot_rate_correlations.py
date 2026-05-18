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
    monotone_nonincreasing,
    numeric_series,
    pearson,
    prepare_time_columns,
    save_figure,
    spearman,
)


DEFAULT_METRICS = [
    "a_i_2D",
    "InterfaceArea",
    "MaxBlobFrac",
    "NumBlobs",
    "ReqMedian",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "Circularity2D_area_weighted_mean",
    "AspectRatio_area_weighted_mean",
    "Solidity_area_weighted_mean",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "Slope_logN_gt_Req_vs_logReq",
]


def compute_dissolution_rates(df, rate_window_min=20.0, rate_min_points=25):
    out = prepare_time_columns(df)
    out = add_sn_derived_columns(out)
    out["SnMonotone"] = monotone_nonincreasing(numeric_series(out, "Sn"))
    out["DissolutionRate_Sn_per_min"] = compute_rate_per_min(
        out["Time_min"],
        numeric_series(out, "Sn"),
        rate_window_min=rate_window_min,
        min_points=rate_min_points,
        monotone=True,
    )
    sn = numeric_series(out, "Sn")
    rate = numeric_series(out, "DissolutionRate_Sn_per_min")
    out["NormalizedDissolutionRate_Sn_per_min"] = np.where(sn > 0, rate / sn, np.nan)
    out["Stage"] = assign_level_a_stage(out["SnNorm"])
    return out


def load_rate_input(timeseries_csv, rate_window_min=20.0, rate_min_points=25):
    return compute_dissolution_rates(
        pd.read_csv(timeseries_csv),
        rate_window_min=rate_window_min,
        rate_min_points=rate_min_points,
    )


def merge_optional_tables(rates, postprocess_dir):
    df = rates.copy()
    postprocess_dir = Path(postprocess_dir)
    for filename in [
        "blob_population_morphology_by_frame.csv",
        "topology_population_by_frame.csv",
        "size_distribution_slope_vs_time.csv",
    ]:
        path = postprocess_dir / filename
        if path.exists():
            aux = pd.read_csv(path)
            if "FrameIndex" in aux.columns:
                df = df.merge(aux, on="FrameIndex", how="left", suffixes=("", f"_{path.stem}"))
    return df


def association_rows(df, metrics=None, rate_col="DissolutionRate_Sn_per_min"):
    metrics = metrics or DEFAULT_METRICS
    rows = []
    for metric in metrics:
        if metric not in df.columns:
            rows.append(
                {
                    "metric": metric,
                    "available": False,
                    "n": 0,
                    "pearson_r": np.nan,
                    "spearman_r": np.nan,
                    "rate_column": rate_col,
                }
            )
            continue
        x = pd.to_numeric(df[metric], errors="coerce")
        y = pd.to_numeric(df[rate_col], errors="coerce")
        finite = np.isfinite(x) & np.isfinite(y)
        rows.append(
            {
                "metric": metric,
                "available": True,
                "n": int(finite.sum()),
                "pearson_r": pearson(x, y),
                "spearman_r": spearman(x, y),
                "rate_column": rate_col,
            }
        )
    return pd.DataFrame(rows)


def binned_summary_rows(df, metrics=None, rate_col="DissolutionRate_Sn_per_min", n_bins=5):
    metrics = metrics or DEFAULT_METRICS
    rows = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        sub = df[[metric, rate_col, "Stage"]].copy()
        sub[metric] = pd.to_numeric(sub[metric], errors="coerce")
        sub[rate_col] = pd.to_numeric(sub[rate_col], errors="coerce")
        sub = sub[np.isfinite(sub[metric]) & np.isfinite(sub[rate_col])]
        if len(sub) < 3:
            continue
        try:
            sub["bin"] = pd.qcut(sub[metric], q=min(n_bins, sub[metric].nunique()), duplicates="drop")
        except ValueError:
            continue
        for (stage, bin_label), group in sub.groupby(["Stage", "bin"], observed=True):
            rows.append(
                {
                    "metric": metric,
                    "stage": stage,
                    "bin": str(bin_label),
                    "n": int(len(group)),
                    "metric_median": float(np.nanmedian(group[metric])),
                    "rate_median": float(np.nanmedian(group[rate_col])),
                    "rate_q25": float(np.nanpercentile(group[rate_col], 25)),
                    "rate_q75": float(np.nanpercentile(group[rate_col], 75)),
                }
            )
    return pd.DataFrame(rows)


def create_figures(df, figures_dir, metrics=None, rate_col="DissolutionRate_Sn_per_min", dpi=300):
    metrics = metrics or ["a_i_2D", "InterfaceArea", "MaxBlobFrac", "NumBlobs", "ReqMedian", "areaFracClusters"]
    figures_dir = ensure_dir(figures_dir)
    paths = []
    for metric in metrics:
        if metric not in df.columns:
            continue
        fig, ax = plt.subplots(figsize=(6, 4))
        scatter = ax.scatter(
            pd.to_numeric(df[metric], errors="coerce"),
            pd.to_numeric(df[rate_col], errors="coerce"),
            c=pd.to_numeric(df.get("SnNorm", np.nan), errors="coerce"),
            s=12,
        )
        ax.set_xlabel(metric)
        ax.set_ylabel("-dSn/dt (per min)")
        fig.colorbar(scatter, ax=ax, label="SnNorm")
        safe_metric = metric.replace("/", "_").replace(" ", "_")
        paths.extend(save_figure(fig, figures_dir, f"rate_vs_{safe_metric}", dpi))
    return paths


def write_rate_outputs(timeseries_csv, postprocess_dir, dpi=300, no_figures=False, rate_window_min=20.0, rate_min_points=25):
    postprocess_dir = ensure_dir(postprocess_dir)
    rates = load_rate_input(timeseries_csv, rate_window_min=rate_window_min, rate_min_points=rate_min_points)
    merged = merge_optional_tables(rates, postprocess_dir)
    associations = association_rows(merged)
    binned = binned_summary_rows(merged)

    rates.to_csv(postprocess_dir / "dissolution_rates.csv", index=False)
    associations.to_csv(postprocess_dir / "rate_metric_associations.csv", index=False)
    binned.to_csv(postprocess_dir / "rate_metric_binned_summary.csv", index=False)

    figures = []
    if not no_figures:
        figures = create_figures(merged, postprocess_dir / "figures_rate", dpi=dpi)
    else:
        ensure_dir(postprocess_dir / "figures_rate")
    return {"rates": rates, "merged": merged, "associations": associations, "binned": binned, "figures": figures}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plot dissolution rate correlations.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--timeseries-csv", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--rate-window-min", type=float, default=20.0)
    parser.add_argument("--rate-min-points", type=int, default=25)
    args = parser.parse_args(argv)
    write_rate_outputs(
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
