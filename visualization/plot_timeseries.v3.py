"""Timeseries plotting entry point.

Default (pipeline output folder):
    Same CLI as plot_timeseries.py — forwards to the full Nature-style figure set.

Level-A residual postprocess (optional):
    python plot_timeseries.v3.py --level-a-only --output-root ... --postprocess-dir ...
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import ensure_dir, save_figure  # noqa: E402
from plot_rate_correlations import compute_dissolution_rates  # noqa: E402


def _latest_by_mtime(paths):
    paths = [Path(p) for p in paths if Path(p).exists()]
    if not paths:
        return None
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, p.name))


def find_timeseries_csv(output_root, explicit=None):
    """Locate the newest timeseries CSV under a pipeline output directory."""
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"timeseries CSV not found: {path}")
        return path
    output_root = Path(output_root)
    realtime = _latest_by_mtime(output_root.glob("timeseries_realtime_*.csv"))
    if realtime is not None:
        return realtime
    plain = _latest_by_mtime(output_root.glob("timeseries_*.csv"))
    if plain is not None:
        return plain
    raise FileNotFoundError(f"No timeseries CSV found under {output_root}")


def resolve_postprocess_dir(output_root, explicit=None):
    """Use explicit postprocess dir or the newest postprocess_residual_structure_* folder."""
    if explicit:
        return ensure_dir(explicit)
    output_root = Path(output_root)
    latest = _latest_by_mtime(output_root.glob("postprocess_residual_structure_*"))
    if latest is not None:
        return latest
    return output_root


def _load_plot_timeseries():
    module_path = SCRIPT_DIR / "plot_timeseries.py"
    spec = importlib.util.spec_from_file_location("plot_timeseries", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plot_timeseries.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_timeseries_figures(
    timeseries_csv, figures_dir, dpi=300, min_time_min=None, rebase_time=True
):
    """Minimal Level-A overview (3-panel) for residual-structure postprocess."""
    figures_dir = ensure_dir(figures_dir)
    pt = _load_plot_timeseries()
    df = pt.load_timeseries(timeseries_csv)
    df = pt.filter_min_time(df, min_time_min, rebase=rebase_time)
    df = compute_dissolution_rates(df)
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
    plt.close(fig)
    return paths


def _parse_level_a_options(remainder):
    """Parse plotting options that must not be consumed before forwarding to plot_timeseries."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--figures-dir", default=None)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--min-time-min", type=float, default=None)
    parser.add_argument("--no-rebase-time", action="store_true")
    return parser.parse_args(remainder)


def run_level_a(args, level_a_options):
    output_root = Path(args.output_root)
    if not output_root.exists():
        raise FileNotFoundError(f"output root does not exist: {output_root}")
    timeseries_csv = find_timeseries_csv(output_root, args.timeseries_csv)
    postprocess_dir = resolve_postprocess_dir(output_root, args.postprocess_dir)
    figures_dir = (
        Path(level_a_options.figures_dir)
        if level_a_options.figures_dir
        else postprocess_dir / "figures_architecture_time"
    )
    written = create_timeseries_figures(
        timeseries_csv,
        figures_dir,
        dpi=level_a_options.dpi,
        min_time_min=level_a_options.min_time_min,
        rebase_time=not level_a_options.no_rebase_time,
    )
    print(f"Read: {timeseries_csv}")
    print(f"Figures directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Create time-series figures from pipeline output. "
            "By default uses the same CLI as plot_timeseries.py (full figure set). "
            "Use --level-a-only for the minimal residual-structure overview."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python plot_timeseries.v3.py <output_dir> --min-time-min 1\n"
            "  python plot_timeseries.v3.py --level-a-only --output-root <dir> "
            "--postprocess-dir <dir> --timeseries-csv <csv>\n"
        ),
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        help="Pipeline output directory (same as plot_timeseries.py).",
    )
    parser.add_argument(
        "--level-a-only",
        action="store_true",
        help="Only write the 3-panel Level-A overview into figures_architecture_time.",
    )
    parser.add_argument(
        "--output-root",
        help="Pipeline output root (Level-A mode; defaults to output_dir).",
    )
    parser.add_argument("--postprocess-dir", default=None, help="Residual postprocess folder.")
    parser.add_argument("--timeseries-csv", default=None, help="Explicit timeseries CSV path.")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args, remainder = parser.parse_known_args(argv)

    if args.level_a_only:
        if args.output_root is None and args.output_dir is None:
            parser.error("--level-a-only requires output_dir or --output-root")
        args.output_root = args.output_root or args.output_dir
        level_a_options = _parse_level_a_options(remainder)
        return run_level_a(args, level_a_options)

    if args.output_dir:
        # Do not define plot_timeseries.py flags here; they must stay in remainder.
        forward_argv = [args.output_dir, *remainder]
        return _load_plot_timeseries().main(forward_argv)

    if args.output_root and args.postprocess_dir and args.timeseries_csv:
        level_a_options = _parse_level_a_options(remainder)
        return run_level_a(args, level_a_options)

    parser.error(
        "Provide output_dir (pipeline folder), e.g.\n"
        "  python plot_timeseries.v3.py <output_dir> --min-time-min 1\n"
        "Or use --level-a-only with --output-root, --postprocess-dir, and --timeseries-csv."
    )


if __name__ == "__main__":
    raise SystemExit(main())
