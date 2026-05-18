from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_architecture_vs_time as architecture  # noqa: E402
import analyze_blob_population_morphology as blob_population  # noqa: E402
import plot_rate_correlations as rate_correlations  # noqa: E402
from residual_postprocess_common import ensure_dir, read_json, timestamp, write_json  # noqa: E402


EXPECTED_OUTPUTS = [
    "architecture_vs_time.csv",
    "architecture_transitions.csv",
    "architecture_rate_summary.csv",
    "blob_population_morphology_by_frame.csv",
    "topology_population_by_frame.csv",
    "size_distribution_slope_vs_time.csv",
    "dissolution_rates.csv",
    "rate_metric_associations.csv",
    "rate_metric_binned_summary.csv",
    "postprocess_summary.json",
    "input_file_inventory.csv",
]


def latest_by_mtime(paths):
    paths = [Path(p) for p in paths if Path(p).exists()]
    if not paths:
        return None
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, p.name))


def find_timeseries_csv(output_root, explicit=None):
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"timeseries CSV not found: {path}")
        return path
    output_root = Path(output_root)
    realtime = latest_by_mtime(output_root.glob("timeseries_realtime_*.csv"))
    if realtime is not None:
        return realtime
    plain = latest_by_mtime(output_root.glob("timeseries_*.csv"))
    if plain is not None:
        return plain
    raise FileNotFoundError(f"No timeseries CSV found under {output_root}")


def find_blob_csv(output_root, explicit=None):
    if explicit:
        path = Path(explicit)
    else:
        path = Path(output_root) / "blob_detail_all_frames.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"blob_detail_all_frames.csv not found at {path}; Python Level A postprocess requires CSV input"
        )
    return path


def find_audit_dir(output_root, explicit=None):
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    return latest_by_mtime(Path(output_root).glob("audit_blob_morphology_gap_*"))


def make_postprocess_dir(output_root, explicit=None, overwrite=False):
    if explicit:
        path = Path(explicit)
        if path.exists() and any(path.iterdir()) and not overwrite:
            raise FileExistsError(f"postprocess directory already exists and is not empty: {path}")
        return ensure_dir(path)
    return ensure_dir(Path(output_root) / f"postprocess_residual_structure_{timestamp()}")


def file_row(path, file_type):
    path = Path(path) if path else None
    if path is None or not path.exists():
        return {
            "file_type": file_type,
            "path": "" if path is None else str(path),
            "exists": False,
            "bytes": 0,
            "modified_time": "",
        }
    stat = path.stat()
    return {
        "file_type": file_type,
        "path": str(path),
        "exists": True,
        "bytes": int(stat.st_size),
        "modified_time": pd.Timestamp(stat.st_mtime, unit="s").isoformat(),
    }


def write_input_inventory(postprocess_dir, output_root, timeseries_csv, blob_csv, audit_dir):
    rows = [
        file_row(output_root, "output_root"),
        file_row(timeseries_csv, "timeseries_csv"),
        file_row(blob_csv, "blob_csv"),
        file_row(audit_dir, "audit_dir"),
    ]
    if audit_dir:
        for name in ["audit_summary.json", "metric_feasibility_matrix.csv", "recommended_next_actions.md"]:
            rows.append(file_row(Path(audit_dir) / name, name))
    pd.DataFrame(rows).to_csv(Path(postprocess_dir) / "input_file_inventory.csv", index=False)


def write_qc_outputs(postprocess_dir):
    qc_dir = ensure_dir(Path(postprocess_dir) / "qc_workbooks")
    rows = []
    for name in EXPECTED_OUTPUTS:
        path = Path(postprocess_dir) / name
        rows.append(file_row(path, name))
    pd.DataFrame(rows).to_csv(qc_dir / "level_a_output_inventory.csv", index=False)
    return qc_dir


def build_summary(output_root, postprocess_dir, timeseries_csv, blob_csv, audit_dir, arch_result, blob_result, rate_result):
    audit_summary = read_json(Path(audit_dir) / "audit_summary.json") if audit_dir else None
    return {
        "analysis_level": "Level A",
        "output_root": str(output_root),
        "postprocess_dir": str(postprocess_dir),
        "inputs": {
            "timeseries_csv": str(timeseries_csv),
            "blob_csv": str(blob_csv),
            "audit_dir": str(audit_dir) if audit_dir else "",
        },
        "audit_context": {
            "overall_status": audit_summary.get("overall_status") if isinstance(audit_summary, dict) else None,
            "tracking_feasibility": audit_summary.get("tracking_feasibility") if isinstance(audit_summary, dict) else None,
            "status_flags": audit_summary.get("status_flags") if isinstance(audit_summary, dict) else [],
        },
        "outputs": EXPECTED_OUTPUTS,
        "counts": {
            "n_architecture_frames": int(len(arch_result["architecture"])),
            "n_blob_population_frames": int(len(blob_result["frame_summary"])),
            "n_rate_rows": int(len(rate_result["rates"])),
        },
        "not_computed": {
            "tracking_metrics": "requires tracking",
            "boundary_metrics": "requires mask/boundary or raw-frame rerun",
            "transport_metrics": "requires experiment metadata",
            "physical_units": "requires pixel_size_um metadata",
        },
        "notes": [
            "CSV Circularity is treated as Circularity2D.",
            "Size-distribution slope is a population fractal proxy, not boundary fractal dimension.",
            "This workflow does not rerun Step 4, segmentation, mask extraction, or tracking.",
        ],
    }


def run_postprocess(args):
    output_root = Path(args.output_root)
    if not output_root.exists():
        raise FileNotFoundError(f"output root does not exist: {output_root}")
    postprocess_dir = make_postprocess_dir(output_root, args.postprocess_dir, overwrite=args.overwrite)
    for subdir in ["figures_architecture_time", "figures_blob_population", "figures_rate", "qc_workbooks"]:
        ensure_dir(postprocess_dir / subdir)

    timeseries_csv = find_timeseries_csv(output_root, args.timeseries_csv)
    blob_csv = find_blob_csv(output_root, args.blob_csv)
    audit_dir = find_audit_dir(output_root, args.audit_dir)
    write_input_inventory(postprocess_dir, output_root, timeseries_csv, blob_csv, audit_dir)

    arch_result = architecture.analyze_architecture(
        timeseries_csv,
        postprocess_dir,
        dpi=args.dpi,
        no_figures=args.no_figures,
        rate_window_min=args.rate_window_min,
        rate_min_points=args.rate_min_points,
    )
    blob_result = blob_population.write_blob_population_outputs(
        blob_csv,
        postprocess_dir,
        timeseries_csv=timeseries_csv,
        chunksize=args.chunksize,
        dpi=args.dpi,
        no_figures=args.no_figures,
        min_slope_points=args.min_slope_points,
    )
    rate_result = rate_correlations.write_rate_outputs(
        timeseries_csv,
        postprocess_dir,
        dpi=args.dpi,
        no_figures=args.no_figures,
        rate_window_min=args.rate_window_min,
        rate_min_points=args.rate_min_points,
    )
    summary = build_summary(output_root, postprocess_dir, timeseries_csv, blob_csv, audit_dir, arch_result, blob_result, rate_result)
    write_json(postprocess_dir / "postprocess_summary.json", summary)
    write_qc_outputs(postprocess_dir)
    return postprocess_dir


def build_parser():
    parser = argparse.ArgumentParser(description="Run read-only Level A residual structure post-processing.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", default=None)
    parser.add_argument("--timeseries-csv", default=None)
    parser.add_argument("--blob-csv", default=None)
    parser.add_argument("--audit-dir", default=None)
    parser.add_argument("--chunksize", type=int, default=200000)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--min-slope-points", type=int, default=20)
    parser.add_argument("--rate-window-min", type=float, default=20.0)
    parser.add_argument("--rate-min-points", type=int, default=25)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    postprocess_dir = run_postprocess(args)
    print(f"Postprocess directory: {postprocess_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
