from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import ensure_dir, save_figure  # noqa: E402
from plot_rate_correlations import compute_dissolution_rates  # noqa: E402


def create_timeseries_figures(timeseries_csv, figures_dir, dpi=300):
    figures_dir = ensure_dir(figures_dir)
    df = compute_dissolution_rates(pd.read_csv(timeseries_csv))
    paths = []
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), sharex=True)
    axes[0].plot(df["Time_min"], df["SnNorm"])
    axes[0].set_ylabel("SnNorm")
    axes[1].plot(df["Time_min"], df["DissolutionRate_Sn_per_min"])
    axes[1].set_ylabel("-dSn/dt")
    for column in ["a_i_2D", "InterfaceArea", "NumBlobs", "MaxBlobFrac"]:
        if column in df.columns:
            axes[2].plot(df["Time_min"], pd.to_numeric(df[column], errors="coerce"), label=column)
    axes[2].set_xlabel("Time (min)")
    axes[2].set_ylabel("Metric")
    axes[2].legend(frameon=False, fontsize=8)
    paths.extend(save_figure(fig, figures_dir, "timeseries_level_a_overview", dpi))
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create Level A residual structure timeseries figures.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--timeseries-csv", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args(argv)
    create_timeseries_figures(args.timeseries_csv, Path(args.postprocess_dir) / "figures_architecture_time", dpi=args.dpi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
