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

from residual_postprocess_common import ensure_dir, save_figure, timestamp  # noqa: E402


RATE_COL = "DissolutionRate_Sn_per_min"
TIME_COL = "Time_min"
DEFAULT_METRICS = [
    "NumBlobs",
    "ReqMedian",
    "MaxBlobFrac",
    "fracDroplets",
    "fracColumns",
    "fracClusters",
    "areaFracDroplets",
    "areaFracColumns",
    "areaFracClusters",
    "a_i_2D",
    "InterfaceArea",
    "Circularity2D_area_weighted_mean",
    "Solidity_area_weighted_mean",
    "AspectRatio_area_weighted_mean",
    "Slope_logN_gt_Req_vs_logReq",
]

METRIC_CATEGORY = {
    "NumBlobs": "population_fragmentation",
    "ReqMedian": "population_fragmentation",
    "MaxBlobFrac": "population_fragmentation",
    "a_i_2D": "interface_exposure_proxy",
    "InterfaceArea": "interface_exposure_proxy",
    "fracDroplets": "topology_composition",
    "fracColumns": "topology_composition",
    "fracClusters": "topology_composition",
    "areaFracDroplets": "topology_composition",
    "areaFracColumns": "topology_composition",
    "areaFracClusters": "topology_composition",
    "Circularity2D_area_weighted_mean": "scalar_morphology",
    "Solidity_area_weighted_mean": "scalar_morphology",
    "AspectRatio_area_weighted_mean": "scalar_morphology",
    "Slope_logN_gt_Req_vs_logReq": "population_fractal_proxy",
}


def stable_score(pearson_r, spearman_r):
    vals = [abs(v) for v in [pearson_r, spearman_r] if np.isfinite(v)]
    if len(vals) < 2:
        return 0.0
    return float(min(vals))


def safe_corr(x, y, method):
    x = pd.to_numeric(pd.Series(x), errors="coerce")
    y = pd.to_numeric(pd.Series(y), errors="coerce")
    ok = x.notna() & y.notna()
    if int(ok.sum()) < 3:
        return np.nan
    if x[ok].nunique() < 2 or y[ok].nunique() < 2:
        return np.nan
    return float(x[ok].corr(y[ok], method=method))


def residualize_against_time(values, time_values):
    y = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(pd.Series(time_values), errors="coerce").to_numpy(dtype=float)
    out = np.full(y.shape, np.nan, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or np.unique(x[ok]).size < 2:
        return out
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    out[ok] = y[ok] - (slope * x[ok] + intercept)
    return out


def make_output_dir(postprocess_dir, explicit=None, overwrite=False):
    if explicit:
        out = Path(explicit)
        if out.exists() and any(out.iterdir()) and not overwrite:
            raise FileExistsError(f"QC output directory already exists and is not empty: {out}")
        return ensure_dir(out)
    return ensure_dir(Path(postprocess_dir) / f"level_a_qc_{timestamp()}")


def read_optional_csv(path):
    path = Path(path)
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_level_a_tables(postprocess_dir):
    postprocess_dir = Path(postprocess_dir)
    rates_path = postprocess_dir / "dissolution_rates.csv"
    arch_path = postprocess_dir / "architecture_vs_time.csv"
    if not rates_path.exists():
        raise FileNotFoundError(f"Missing required file: {rates_path}")
    if not arch_path.exists():
        raise FileNotFoundError(f"Missing required file: {arch_path}")

    rates = pd.read_csv(rates_path)
    merged = rates.copy()
    for name in [
        "blob_population_morphology_by_frame.csv",
        "topology_population_by_frame.csv",
        "size_distribution_slope_vs_time.csv",
    ]:
        table = read_optional_csv(postprocess_dir / name)
        if table is not None and "FrameIndex" in table.columns:
            merged = merged.merge(table, on="FrameIndex", how="left", suffixes=("", f"_{Path(name).stem}"))

    return {
        "rates": rates,
        "merged": merged,
        "architecture": pd.read_csv(arch_path),
        "transitions": read_optional_csv(postprocess_dir / "architecture_transitions.csv"),
    }


def association_for_metric(df, metric, min_n=20, detrend=False):
    if metric not in df.columns:
        return {
            "metric": metric,
            "category": METRIC_CATEGORY.get(metric, "unknown"),
            "available": False,
            "n": 0,
            "pearson_r": np.nan,
            "spearman_r": np.nan,
            "stable_score": 0.0,
            "direction": "unavailable",
        }

    x = pd.to_numeric(df[metric], errors="coerce")
    y = pd.to_numeric(df[RATE_COL], errors="coerce")
    if detrend:
        time_values = pd.to_numeric(df[TIME_COL] if TIME_COL in df.columns else df["FrameIndex"], errors="coerce")
        x = pd.Series(residualize_against_time(x, time_values))
        y = pd.Series(residualize_against_time(y, time_values))

    ok = x.notna() & y.notna()
    if int(ok.sum()) < min_n:
        pearson_r = np.nan
        spearman_r = np.nan
    else:
        pearson_r = safe_corr(x[ok], y[ok], "pearson")
        spearman_r = safe_corr(x[ok], y[ok], "spearman")
    score = stable_score(pearson_r, spearman_r)
    if score == 0:
        direction = "unstable"
    else:
        sign = np.sign(np.nanmean([pearson_r, spearman_r]))
        direction = "positive" if sign > 0 else "negative"
    return {
        "metric": metric,
        "category": METRIC_CATEGORY.get(metric, "unknown"),
        "available": True,
        "n": int(ok.sum()),
        "pearson_r": pearson_r,
        "spearman_r": spearman_r,
        "stable_score": score,
        "direction": direction,
    }


def compute_global_associations(df, metrics=None, min_n=20, threshold=0.4):
    rows = [association_for_metric(df, metric, min_n=min_n, detrend=False) for metric in (metrics or DEFAULT_METRICS)]
    out = pd.DataFrame(rows)
    out["passes_threshold"] = out["stable_score"] >= threshold
    return out.sort_values(["passes_threshold", "stable_score", "metric"], ascending=[False, False, True])


def compute_stage_associations(df, metrics=None, min_n=20, threshold=0.4, detrend=False):
    rows = []
    if "Stage" not in df.columns:
        return pd.DataFrame(columns=["stage", "metric", "category", "available", "n", "pearson_r", "spearman_r", "stable_score", "direction", "passes_threshold"])
    for stage, sub in df.groupby("Stage", dropna=False):
        for metric in metrics or DEFAULT_METRICS:
            row = association_for_metric(sub, metric, min_n=min_n, detrend=detrend)
            row["stage"] = stage
            rows.append(row)
    out = pd.DataFrame(rows)
    out["passes_threshold"] = out["stable_score"] >= threshold
    cols = ["stage", "metric", "category", "available", "n", "pearson_r", "spearman_r", "stable_score", "direction", "passes_threshold"]
    return out.loc[:, cols].sort_values(["stage", "passes_threshold", "stable_score", "metric"], ascending=[True, False, False, True])


def compute_stage_rate_summary(rates):
    if "Stage" not in rates.columns:
        return pd.DataFrame()
    grouped = rates.groupby("Stage", dropna=False)[RATE_COL]
    return grouped.agg(["count", "median", "mean", "std", "min", "max"]).reset_index()


def compute_architecture_qc(architecture, transitions):
    arch_type = architecture["ArchitectureType"] if "ArchitectureType" in architecture.columns else pd.Series(dtype=object)
    counts = arch_type.value_counts(dropna=False)
    n_types = int(counts.shape[0])
    dominant = str(counts.index[0]) if n_types else ""
    n_transitions = 0 if transitions is None else int(len(transitions))
    if n_types <= 1 or n_transitions == 0:
        signal = "no_architecture_transition_signal"
        interpretability = "Architecture transition is not a useful primary interpretation axis for this run."
    else:
        signal = "architecture_transition_signal_present"
        interpretability = "Architecture transitions can be considered as candidate interpretation events."
    return pd.DataFrame(
        [
            {
                "n_frames": int(len(architecture)),
                "n_architecture_types": n_types,
                "dominant_architecture_type": dominant,
                "n_transitions": n_transitions,
                "transition_signal": signal,
                "interpretability_note": interpretability,
            }
        ]
    )


def build_candidates(global_assoc, stage_assoc, detrended_assoc, threshold=0.4):
    rows = []
    metrics = list(dict.fromkeys(DEFAULT_METRICS))
    for metric in metrics:
        g = global_assoc[global_assoc["metric"] == metric]
        s = stage_assoc[stage_assoc["metric"] == metric]
        d = detrended_assoc[detrended_assoc["metric"] == metric]
        raw_score = max(
            [float(g["stable_score"].max()) if not g.empty else 0.0, float(s["stable_score"].max()) if not s.empty else 0.0]
        )
        det_score = float(d["stable_score"].max()) if not d.empty else 0.0
        available = bool((not g.empty and bool(g["available"].iloc[0])) or (not s.empty and bool(s["available"].any())))
        if raw_score >= threshold and det_score >= threshold:
            status = "HIGH_CONFIDENCE_LEVEL_A_CANDIDATE"
        elif raw_score >= threshold:
            status = "RAW_ASSOCIATION_POSSIBLE_TIME_TREND"
        elif available:
            status = "WEAK_OR_UNSTABLE_LEVEL_A_ASSOCIATION"
        else:
            status = "UNAVAILABLE"
        rows.append(
            {
                "metric": metric,
                "category": METRIC_CATEGORY.get(metric, "unknown"),
                "best_raw_stable_score": raw_score,
                "best_time_detrended_stable_score": det_score,
                "candidate_status": status,
            }
        )
    return pd.DataFrame(rows).sort_values(["candidate_status", "best_time_detrended_stable_score", "best_raw_stable_score"], ascending=[True, False, False])


def create_figures(global_assoc, stage_rate_summary, output_dir, dpi=300):
    figures_dir = ensure_dir(Path(output_dir) / "figures_qc")
    paths = []
    top = global_assoc[global_assoc["available"]].head(12)
    if not top.empty:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.barh(top["metric"], top["stable_score"])
        ax.invert_yaxis()
        ax.set_xlabel("stable_score = min(|Pearson|, |Spearman|)")
        ax.set_title("Global Level A Association Stability")
        paths.extend(save_figure(fig, figures_dir, "global_stable_associations", dpi=dpi))
    if not stage_rate_summary.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(stage_rate_summary["Stage"].astype(str), stage_rate_summary["median"])
        ax.set_ylabel("Median -dSn/dt per min")
        ax.set_title("Dissolution Rate By Stage")
        paths.extend(save_figure(fig, figures_dir, "stage_rate_summary", dpi=dpi))
    return paths


def write_report(output_dir, global_assoc, stage_assoc, detrended_assoc, stage_rate, architecture_qc, candidates):
    output_dir = Path(output_dir)
    top_global = global_assoc[global_assoc["passes_threshold"]].head(10)
    top_detrended = detrended_assoc[detrended_assoc["passes_threshold"]].head(12)
    high = candidates[candidates["candidate_status"] == "HIGH_CONFIDENCE_LEVEL_A_CANDIDATE"]
    arch_row = architecture_qc.iloc[0].to_dict() if not architecture_qc.empty else {}

    lines = [
        "# Level A QC And Interpretation Screening Report",
        "",
        "## Executive Summary",
        "- This report screens association candidates only; it does not claim causality.",
        "- Architecture transition is not a useful primary interpretation axis if all frames remain in one architecture class.",
        "- Level A is sufficient for preliminary interpretation screening, but not for boundary roughness, per-blob tracking, or transport dimensionless numbers.",
        "",
        "## Architecture QC",
        f"- transition_signal: `{arch_row.get('transition_signal', 'unknown')}`",
        f"- dominant_architecture_type: `{arch_row.get('dominant_architecture_type', '')}`",
        f"- n_transitions: `{arch_row.get('n_transitions', '')}`",
        "",
        "## Most Stable Global Associations",
    ]
    if top_global.empty:
        lines.append("- No global association met the stable threshold.")
    else:
        for _, row in top_global.iterrows():
            lines.append(
                f"- `{row.metric}` ({row.category}): stable_score={row.stable_score:.3f}, "
                f"Pearson={row.pearson_r:.3f}, Spearman={row.spearman_r:.3f}, direction={row.direction}"
            )
    lines.extend(["", "## Time-Detrended Stage Associations"])
    if top_detrended.empty:
        lines.append("- No time-detrended stage association met the stable threshold.")
    else:
        for _, row in top_detrended.iterrows():
            lines.append(
                f"- `{row.metric}` in `{row.stage}`: stable_score={row.stable_score:.3f}, "
                f"Pearson={row.pearson_r:.3f}, Spearman={row.spearman_r:.3f}, direction={row.direction}"
            )
    lines.extend(["", "## Interpretation Candidates"])
    if high.empty:
        lines.append("- No metric met both raw and time-detrended stability thresholds.")
    else:
        for _, row in high.iterrows():
            lines.append(
                f"- `{row.metric}` ({row.category}): raw={row.best_raw_stable_score:.3f}, "
                f"detrended={row.best_time_detrended_stable_score:.3f}"
            )
    lines.extend(
        [
            "",
            "## Not Interpreted At Level A",
            "- Boundary roughness, convex perimeter, and boundary fractal dimension require mask/boundary geometry.",
            "- Per-blob shrink rate and split/merge events require tracking.",
            "- Ca, Pe, Sherwood proxy, and physical-unit rates require metadata such as pixel size, flow, surfactant concentration, channel geometry, viscosity, IFT, and diffusion coefficient.",
            "",
            "## Recommended Next Step",
            "Prioritize metadata recovery first, then run a small-frame mask/geometry extraction validation. Do not run a full segmentation pipeline rerun at this stage.",
        ]
    )
    (output_dir / "level_a_qc_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_qc(args):
    postprocess_dir = Path(args.postprocess_dir)
    if not postprocess_dir.exists():
        raise FileNotFoundError(f"postprocess dir does not exist: {postprocess_dir}")
    output_dir = make_output_dir(postprocess_dir, args.output_dir, overwrite=args.overwrite)
    tables = load_level_a_tables(postprocess_dir)

    global_assoc = compute_global_associations(
        tables["merged"], min_n=args.min_n, threshold=args.stable_threshold
    )
    stage_assoc = compute_stage_associations(
        tables["merged"], min_n=args.min_n, threshold=args.stable_threshold, detrend=False
    )
    detrended_assoc = compute_stage_associations(
        tables["merged"], min_n=args.min_n, threshold=args.stable_threshold, detrend=True
    )
    stage_rate = compute_stage_rate_summary(tables["rates"])
    architecture_qc = compute_architecture_qc(tables["architecture"], tables["transitions"])
    candidates = build_candidates(global_assoc, stage_assoc, detrended_assoc, threshold=args.stable_threshold)

    global_assoc.to_csv(output_dir / "global_stable_associations.csv", index=False)
    stage_assoc.to_csv(output_dir / "stage_stable_associations.csv", index=False)
    detrended_assoc.to_csv(output_dir / "stage_time_detrended_associations.csv", index=False)
    stage_rate.to_csv(output_dir / "stage_rate_summary.csv", index=False)
    architecture_qc.to_csv(output_dir / "architecture_qc_summary.csv", index=False)
    candidates.to_csv(output_dir / "interpretation_candidates.csv", index=False)
    ensure_dir(output_dir / "figures_qc")
    if not args.no_figures:
        create_figures(global_assoc, stage_rate, output_dir, dpi=args.dpi)
    write_report(output_dir, global_assoc, stage_assoc, detrended_assoc, stage_rate, architecture_qc, candidates)
    return output_dir


def build_parser():
    parser = argparse.ArgumentParser(description="Screen Level A QC associations for interpretation.")
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--min-n", type=int, default=20)
    parser.add_argument("--stable-threshold", type=float, default=0.4)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    output_dir = run_qc(args)
    print(f"Level A QC directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
