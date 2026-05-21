"""Shared PV-axis wrapper logic for plot_timeseries variants."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


PORE_VOLUME_PATTERN = re.compile(
    r"Flow\s+Domain\s+Pore\s+Volume(?:\*\*)?\s*:?\s*"
    r"([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*m\^?3",
    flags=re.IGNORECASE,
)


def load_source_module(path, module_name):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_report_pore_volume_ul(output_dir):
    """Return flow-domain pore volume in uL from analysis_report, or None."""
    output_dir = Path(output_dir)
    for report_name in ("analysis_report.txt", "analysis_report.md"):
        report = output_dir / report_name
        if not report.exists():
            continue
        text = report.read_text(encoding="utf-8", errors="replace")
        match = PORE_VOLUME_PATTERN.search(text)
        if match:
            return float(match.group(1)) * 1e9
    return None


def resolve_pore_volume_ul(output_dir, explicit_pore_volume_ul=None):
    report_value = parse_report_pore_volume_ul(output_dir)
    if report_value is not None:
        return report_value, "analysis_report.txt"
    if explicit_pore_volume_ul is not None:
        value = float(explicit_pore_volume_ul)
        if value <= 0:
            raise ValueError("--pore-volume-ul must be positive")
        return value, "user-provided"
    raise ValueError(
        "Pore volume is required for computed PV. Provide --pore-volume-ul "
        "or include Flow Domain Pore Volume in analysis_report.txt."
    )


def compute_pv_from_flow(df, flow_rate_ul_min, pore_volume_ul):
    flow_rate = float(flow_rate_ul_min)
    pore_volume = float(pore_volume_ul)
    if flow_rate <= 0:
        raise ValueError("--flow-rate-ul-min must be positive")
    if pore_volume <= 0:
        raise ValueError("pore volume must be positive")
    real_time_s = pd.to_numeric(df["RealTime_s"], errors="coerce")
    if real_time_s.isna().any() or not np.isfinite(real_time_s).all():
        raise ValueError("RealTime_s must be finite to compute PV")
    return real_time_s * flow_rate / 60.0 / pore_volume


def _complete_csv_pv(df):
    if "PV" not in df.columns:
        return None
    pv = pd.to_numeric(df["PV"], errors="coerce")
    if len(pv) == 0 or pv.isna().any() or not np.isfinite(pv).all():
        return None
    return pv


def attach_pv(df, output_dir, pv_source="auto", flow_rate_ul_min=None, explicit_pore_volume_ul=None):
    """Attach PV to df and return (df, metadata)."""
    source = str(pv_source).lower()
    if source not in {"auto", "csv", "computed"}:
        raise ValueError("--pv-source must be one of: auto, csv, computed")

    plot_df = df.copy()
    csv_pv = _complete_csv_pv(plot_df)
    if source in {"auto", "csv"} and csv_pv is not None:
        plot_df["PV"] = csv_pv.astype(float)
        metadata = {
            "pv_source": "csv",
            "flow_rate_ul_min": None if flow_rate_ul_min is None else float(flow_rate_ul_min),
            "pore_volume_ul": None,
            "pore_volume_source": None,
            "formula": "PV read from CSV column",
        }
        return plot_df, _add_pv_range(metadata, plot_df)

    if source == "csv":
        raise ValueError("--pv-source csv requested, but CSV has no complete finite PV column")
    if flow_rate_ul_min is None:
        raise ValueError("--flow-rate-ul-min is required when PV is computed")

    pore_volume_ul, pore_volume_source = resolve_pore_volume_ul(
        output_dir,
        explicit_pore_volume_ul=explicit_pore_volume_ul,
    )
    plot_df["PV"] = compute_pv_from_flow(plot_df, flow_rate_ul_min, pore_volume_ul)
    metadata = {
        "pv_source": "computed",
        "flow_rate_ul_min": float(flow_rate_ul_min),
        "pore_volume_ul": float(pore_volume_ul),
        "pore_volume_source": pore_volume_source,
        "formula": "PV = flow_rate_ul_min * RealTime_s / 60 / pore_volume_ul",
    }
    return plot_df, _add_pv_range(metadata, plot_df)


def _add_pv_range(metadata, df):
    pv = pd.to_numeric(df["PV"], errors="coerce")
    metadata = dict(metadata)
    metadata["pv_min"] = float(pv.min())
    metadata["pv_max"] = float(pv.max())
    metadata["n_rows"] = int(len(df))
    return metadata


def patch_time_axis_to_pv(module):
    """Patch one loaded plot_timeseries module so time axes display as PV axes."""

    def _finalize_pv_axis(ax, ylabel, log_scale=False):
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Pore volumes (PV, log scale)" if log_scale else "Pore volumes (PV)")
        if log_scale:
            ax.set_xscale("log")
        module.style_axes(ax)
        if log_scale:
            ax.grid(True, which="both", color="#E4E4E4", linewidth=0.55, alpha=0.7)

    module._finalize_time_axis = _finalize_pv_axis


def _kwargs_for(func, candidates):
    params = inspect.signature(func).parameters
    return {key: value for key, value in candidates.items() if key in params}


def _prepare_variant_plot_df(module, df, args):
    candidates = {
        "smooth_window": args.smooth_window,
        "smooth_polyorder": args.smooth_polyorder,
        "rate_lr_window": getattr(args, "rate_lr_window", None),
    }
    return module._prepare_plot_df(df, **_kwargs_for(module._prepare_plot_df, candidates))


def _pv_plot_df(plot_df):
    pv_df = plot_df.copy()
    pv_df["Time_min_for_rate"] = plot_df["Time_min"]
    pv_df["Time_min"] = plot_df["PV"]
    return pv_df


def _data_columns_with_pv(columns, df):
    selected = [column for column in columns if column in df.columns]
    if "PV" not in selected and "PV" in df.columns:
        if "Time_min" in selected:
            selected.insert(selected.index("Time_min") + 1, "PV")
        elif "RealTime_s" in selected:
            selected.insert(selected.index("RealTime_s") + 1, "PV")
        else:
            selected.insert(0, "PV")
    return selected


def write_plot_data_workbooks_pv(module, df, figures_dir):
    paths = []
    for stem, columns in module.DATA_EXPORTS:
        paths.append(
            module._write_data_workbook(
                df,
                stem,
                _data_columns_with_pv(columns, df),
                figures_dir,
            )
        )
    return paths


def _v3_qc(module, plot_df, args, output_dir):
    blob_detail = None
    blob_detail_path = module.find_blob_detail_csv(output_dir)
    if blob_detail_path is not None:
        blob_detail = pd.read_csv(blob_detail_path)
        plot_df, qc = module.apply_blob_detail_qc(
            plot_df,
            blob_detail,
            min_blob_area_px=args.min_blob_area_px,
            min_shape_area_px=args.min_shape_area_px,
            min_shape_perimeter_px=args.min_shape_perimeter_px,
        )
    else:
        message = "blob_detail_all_frames.csv not found; skipped Req distribution and blob-detail audits"
        qc = {
            "circularity": {
                "status": pd.DataFrame({"Status": [message]}),
                "gt1_blobs": pd.DataFrame(),
                "by_frame": pd.DataFrame(),
            },
            "topology": {
                "status": pd.DataFrame({"Status": [message], "classification": ["ambiguous"]}),
                "by_frame": module._empty_topology_by_frame(),
                "classification": "ambiguous",
            },
        }
    return plot_df, qc, blob_detail


def create_all_figures_pv(module, df, figures_dir, args, output_dir=None):
    """Create PV-axis figures while preserving true Time_min for rate/QC calculations."""
    module.configure_nature_style()
    patch_time_axis_to_pv(module)
    plot_df = _prepare_variant_plot_df(module, df, args)

    qc = None
    blob_detail = None
    if hasattr(module, "find_blob_detail_csv"):
        plot_df, qc, blob_detail = _v3_qc(module, plot_df, args, output_dir)

    pv_df = _pv_plot_df(plot_df)
    written = []

    for log_scale in (False, True):
        suffix = "_log" if log_scale else ""
        fig = module._create_combined_figure(pv_df, log_scale=log_scale)
        written.extend(module._save_figure(fig, f"timeseries_6panel{suffix}", figures_dir, args.dpi))
        module.plt.close(fig)

        for stem, plotter in module.PLOTTERS:
            fig = module._create_individual_figure(pv_df, plotter, log_scale=log_scale)
            written.extend(module._save_figure(fig, f"{stem}{suffix}", figures_dir, args.dpi))
            module.plt.close(fig)

    if hasattr(module, "plot_rate_vs_ai_2d_stage"):
        fig = module._create_individual_figure(pv_df, module.plot_rate_vs_ai_2d_stage, log_scale=False)
        written.extend(module._save_figure(fig, "S01_rate_vs_ai_2D_stage", figures_dir, args.dpi))
        module.plt.close(fig)

    if blob_detail is not None:
        req_data = module.selected_req_distribution_data(
            plot_df,
            blob_detail,
            target_times=module.REQ_TARGET_TIMES_MIN,
            min_blob_area_px=args.min_blob_area_px,
        )
        if not req_data.empty:
            fig = module._plot_req_distribution(req_data)
            written.extend(module._save_figure(fig, "18_req_distribution", figures_dir, args.dpi))
            module.plt.close(fig)
        supplemental_req_data = module.selected_req_distribution_data(
            plot_df,
            blob_detail,
            target_times=module.REQ_SUPPLEMENTAL_TARGET_TIMES_MIN,
            min_blob_area_px=args.min_blob_area_px,
        )
        if not supplemental_req_data.empty:
            fig = module._plot_req_distribution(supplemental_req_data)
            written.extend(
                module._save_figure(fig, "S02_req_distribution_near_depleted", figures_dir, args.dpi)
            )
            module.plt.close(fig)

    written.extend(write_plot_data_workbooks_pv(module, plot_df, figures_dir))
    if qc is not None:
        written.extend(module.write_qc_workbooks(plot_df, qc, figures_dir))
    return written


def write_pv_metadata(figures_dir, metadata, written_paths):
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / "pv_conversion_metadata.json"
    payload = dict(metadata)
    payload["outputs"] = [str(path) for path in written_paths]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def add_pv_arguments(parser):
    parser.add_argument(
        "--flow-rate-ul-min",
        type=float,
        default=None,
        help="Actual flow rate in uL/min. Required when PV is computed.",
    )
    parser.add_argument(
        "--pore-volume-ul",
        type=float,
        default=None,
        help="Fallback pore volume in uL if analysis_report.txt has no Flow Domain Pore Volume.",
    )
    parser.add_argument(
        "--pv-source",
        choices=("auto", "csv", "computed"),
        default="auto",
        help="Use CSV PV if available, force CSV PV, or compute PV from flow rate and pore volume.",
    )
    return parser


def main_for_original(original_filename, module_name, argv=None):
    script_dir = Path(__file__).resolve().parent
    module = load_source_module(script_dir / original_filename, module_name)
    parser = add_pv_arguments(module.build_arg_parser())
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    csv_path = module.find_timeseries_csv(output_dir, args.csv_path)
    figures_dir = Path(args.figures_dir) if args.figures_dir else output_dir / "figure_PV"

    df = module.load_timeseries(csv_path)
    if args.skip_frames > 0:
        if args.skip_frames >= len(df) - 1:
            raise ValueError(
                f"--skip-frames {args.skip_frames} would leave fewer than 2 rows out of {len(df)}"
            )
        df = df.iloc[args.skip_frames:].reset_index(drop=True)
    df = module.filter_min_time(df, args.min_time_min)
    df, pv_metadata = attach_pv(
        df,
        output_dir=output_dir,
        pv_source=args.pv_source,
        flow_rate_ul_min=args.flow_rate_ul_min,
        explicit_pore_volume_ul=args.pore_volume_ul,
    )

    pixel_size_um = args.pixel_size_um
    pixel_size_source = "user-provided"
    if pixel_size_um is None:
        pixel_size_um = module.find_pixel_size_um(output_dir)
        pixel_size_source = "analysis_report.txt"
    df = module.apply_pixel_size_to_req(df, pixel_size_um)

    written = create_all_figures_pv(module, df, figures_dir, args, output_dir=output_dir)
    metadata_path = write_pv_metadata(figures_dir, pv_metadata, written)
    written.append(metadata_path)

    print(f"Read: {csv_path}")
    print(f"Rows: {len(df)}")
    if pixel_size_um is not None:
        print(f"Pixel size: {pixel_size_um} um/px (source: {pixel_size_source}); Req* converted to um.")
    else:
        print("Pixel size: not provided/auto-detected; Req* kept in pixels.")
    print(
        "PV conversion: "
        f"{pv_metadata['pv_source']}, "
        f"Q={pv_metadata['flow_rate_ul_min']} uL/min, "
        f"Vpore={pv_metadata['pore_volume_ul']} uL"
    )
    print(f"Figures directory: {figures_dir}")
    for path in written:
        print(f"Saved: {path}")
    return 0

