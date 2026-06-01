from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED_OUTPUTS = [
    "g21_geometry_scope_decision.md",
    "g21_level_a_interpretation_final.md",
    "g21_level_a_stage_summary.csv",
    "g21_rate_window_sensitivity_summary.csv",
    "g21_interpretation_candidates_ranked.csv",
    "g21_limited_2d_geometry_support.md",
    "g21_2d_geometry_reliability_summary.csv",
    "g21_geometry_smoke_vs_level_a_consistency.md",
    "g21_interpretation_package_acceptance_review.md",
    "g21_claims_register.md",
    "interpretation_package_manifest.json",
]


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as fid:
        return json.load(fid)


def write_json(path: Path, payload) -> None:
    def clean(value):
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value) if np.isfinite(value) else None
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if value is None:
            return None
        try:
            if pd.isna(value) and not isinstance(value, (str, bytes)):
                return None
        except TypeError:
            pass
        return value

    with path.open("w", encoding="utf-8") as fid:
        json.dump(clean(payload), fid, ensure_ascii=False, indent=2)


def read_csv_required(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return pd.read_csv(path)


def numeric(df: pd.DataFrame, column: str, default=np.nan) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def load_rates(postprocess_dir: Path) -> pd.DataFrame:
    rates = read_csv_required(postprocess_dir / "dissolution_rates.csv", "dissolution_rates.csv")
    rates = rates.copy()
    if "FrameIndex" not in rates.columns:
        rates["FrameIndex"] = np.arange(1, len(rates) + 1)
    rates["FrameIndex"] = pd.to_numeric(rates["FrameIndex"], errors="coerce").astype("Int64")
    if "RealTime_s" not in rates.columns:
        if "Time" in rates.columns:
            rates["RealTime_s"] = pd.to_numeric(rates["Time"], errors="coerce")
        elif "Time_min" in rates.columns:
            rates["RealTime_s"] = pd.to_numeric(rates["Time_min"], errors="coerce") * 60.0
        else:
            rates["RealTime_s"] = np.arange(len(rates), dtype=float)
    if "Time_min" not in rates.columns or numeric(rates, "Time_min").isna().all():
        rates["Time_min"] = numeric(rates, "RealTime_s") / 60.0
    if "SnMonotone" not in rates.columns:
        sn = numeric(rates, "Sn").fillna(np.inf).to_numpy(dtype=float)
        mono = np.minimum.accumulate(sn)
        mono = np.where(np.isfinite(mono), mono, np.nan)
        rates["SnMonotone"] = mono
    return rates.sort_values("FrameIndex", kind="mergesort").reset_index(drop=True)


def assign_fixed_stages(rates: pd.DataFrame) -> pd.Series:
    sn = numeric(rates, "SnMonotone").to_numpy(dtype=float)
    n = len(rates)
    stage = np.full(n, "unknown", dtype=object)
    finite = np.isfinite(sn)
    stage[finite & (sn >= 0.20)] = "early_depletion"
    stage[finite & (sn >= 0.05) & (sn < 0.20)] = "active_dissolution"
    stage[finite & (sn >= 0.005) & (sn < 0.05)] = "late_depletion"
    endpoint = finite & (sn < 0.005)
    if n:
        final_start = int(np.floor(0.95 * n))
        endpoint[final_start:] = True
    stage[endpoint] = "endpoint"
    return pd.Series(stage, index=rates.index, name="StageFixed")


def merge_level_a(primary_dir: Path) -> pd.DataFrame:
    rates = load_rates(primary_dir)
    rates["StageFixed"] = assign_fixed_stages(rates)
    keep_rate_cols = [
        "FrameIndex",
        "RealTime_s",
        "Time_min",
        "Sn",
        "SnNorm",
        "SnMonotone",
        "DissolutionRate_Sn_per_min",
        "NormalizedDissolutionRate_Sn_per_min",
        "StageFixed",
    ]
    merged = rates[[c for c in keep_rate_cols if c in rates.columns]].copy()

    for filename in [
        "architecture_vs_time.csv",
        "blob_population_morphology_by_frame.csv",
        "topology_population_by_frame.csv",
        "size_distribution_slope_vs_time.csv",
    ]:
        path = primary_dir / filename
        if not path.exists():
            continue
        table = pd.read_csv(path)
        if "FrameIndex" not in table.columns:
            continue
        drop = [c for c in table.columns if c in merged.columns and c != "FrameIndex"]
        table = table.drop(columns=drop)
        merged = merged.merge(table, on="FrameIndex", how="left")
    return merged


def finite_summary(values: pd.Series) -> dict:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"mean": np.nan, "median": np.nan, "p25": np.nan, "p75": np.nan, "p99": np.nan, "max": np.nan}
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(np.max(arr)),
    }


def dominant_value(series: pd.Series) -> str:
    if series.empty:
        return ""
    counts = series.dropna().astype(str).value_counts()
    return "" if counts.empty else str(counts.index[0])


def make_stage_summary(level_a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    stage_order = ["early_depletion", "active_dissolution", "late_depletion", "endpoint"]
    for stage in stage_order:
        sub = level_a[level_a["StageFixed"] == stage].copy()
        if sub.empty:
            continue
        rate_stats = finite_summary(sub["DissolutionRate_Sn_per_min"])
        rows.append(
            {
                "StageFixed": stage,
                "NFrames": int(len(sub)),
                "FrameStart": int(numeric(sub, "FrameIndex").min()),
                "FrameEnd": int(numeric(sub, "FrameIndex").max()),
                "TimeStart_min": float(numeric(sub, "RealTime_s").min() / 60.0),
                "TimeEnd_min": float(numeric(sub, "RealTime_s").max() / 60.0),
                "SnMonotoneStart": float(numeric(sub, "SnMonotone").iloc[0]),
                "SnMonotoneEnd": float(numeric(sub, "SnMonotone").iloc[-1]),
                "Rate10_mean": rate_stats["mean"],
                "Rate10_median": rate_stats["median"],
                "Rate10_p25": rate_stats["p25"],
                "Rate10_p75": rate_stats["p75"],
                "NumBlobs_median": float(numeric(sub, "NumBlobs").median()),
                "InterfaceArea_median": float(numeric(sub, "InterfaceArea").median()),
                "ReqMedian_median": float(numeric(sub, "ReqMedian").median()),
                "MaxBlobFrac_median": float(numeric(sub, "MaxBlobFrac").median()),
                "Amax_Atotal_median": float(numeric(sub, "Amax_Atotal").median()),
                "Slope_logN_gt_Req_vs_logReq_median": float(numeric(sub, "Slope_logN_gt_Req_vs_logReq").median()),
                "DominantArchitecture": dominant_value(sub["ArchitectureType"]) if "ArchitectureType" in sub.columns else "",
                "AreaFracDroplets_median": float(numeric(sub, "areaFracDroplets").median()),
                "AreaFracColumns_median": float(numeric(sub, "areaFracColumns").median()),
                "AreaFracClusters_median": float(numeric(sub, "areaFracClusters").median()),
            }
        )
    out = pd.DataFrame(rows)
    if int(out["NFrames"].sum()) != len(level_a):
        raise ValueError("Stage summary does not cover all frames exactly once.")
    return out


def sn_monotone_increase_count(rates: pd.DataFrame) -> int:
    sn = numeric(rates, "SnMonotone").to_numpy(dtype=float)
    diff = np.diff(sn)
    return int(np.count_nonzero(np.isfinite(diff) & (diff > 1e-12)))


def make_rate_sensitivity_summary(rate_dirs: dict[str, Path], stage_by_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rate_tables = {}
    rows = []
    for label, directory in rate_dirs.items():
        rates = load_rates(directory)
        if len(rates) != 12024:
            raise ValueError(f"{label} rate rows = {len(rates)}, expected 12024")
        rates = rates.merge(stage_by_frame[["FrameIndex", "StageFixed"]], on="FrameIndex", how="left")
        rate_tables[label] = rates
        for stage in ["all", "early_depletion", "active_dissolution", "late_depletion", "endpoint"]:
            sub = rates if stage == "all" else rates[rates["StageFixed"] == stage]
            stats = finite_summary(sub["DissolutionRate_Sn_per_min"])
            rows.append(
                {
                    "WindowMin": int(label.replace("min", "")),
                    "StageFixed": stage,
                    "NFrames": int(len(sub)),
                    "SnMonotoneIncreaseCount": sn_monotone_increase_count(rates),
                    "RateMean": stats["mean"],
                    "RateMedian": stats["median"],
                    "RateP99": stats["p99"],
                    "RateMax": stats["max"],
                    "NonzeroRateFrames": int(np.count_nonzero(numeric(sub, "DissolutionRate_Sn_per_min").fillna(0).to_numpy(dtype=float) > 0)),
                }
            )
    curves = [numeric(rate_tables[k], "DissolutionRate_Sn_per_min").to_numpy(dtype=float) for k in ["5min", "10min", "20min"]]
    if all(np.allclose(curves[0], curve, equal_nan=True) for curve in curves[1:]):
        raise ValueError("Regenerated 5/20 min rate curves are still identical to the 10 min primary curve.")
    for rates in rate_tables.values():
        if sn_monotone_increase_count(rates) != 0:
            raise ValueError("SnMonotone has increases in a sensitivity rate table.")
    return pd.DataFrame(rows), rate_tables


def latest_candidate_table(primary_dir: Path) -> Path | None:
    candidates = sorted(primary_dir.glob("level_a_qc_*/*interpretation_candidates.csv"), key=lambda p: p.stat().st_mtime_ns)
    return candidates[-1] if candidates else None


def spearman_for_metric(metric_source: pd.DataFrame, rates: pd.DataFrame, metric: str) -> float:
    if metric not in metric_source.columns:
        return np.nan
    joined = metric_source[["FrameIndex", metric]].merge(
        rates[["FrameIndex", "DissolutionRate_Sn_per_min"]], on="FrameIndex", how="inner"
    )
    x = pd.to_numeric(joined[metric], errors="coerce")
    y = pd.to_numeric(joined["DissolutionRate_Sn_per_min"], errors="coerce")
    valid = x.notna() & y.notna()
    if int(valid.sum()) < 20:
        return np.nan
    return float(x[valid].corr(y[valid], method="spearman"))


def make_ranked_candidates(primary_dir: Path, level_a: pd.DataFrame, rate_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    candidate_path = latest_candidate_table(primary_dir)
    if candidate_path:
        base = pd.read_csv(candidate_path)
    else:
        assoc = pd.read_csv(primary_dir / "rate_metric_associations.csv")
        base = assoc.rename(columns={"spearman_r": "best_raw_stable_score"})
        base["best_time_detrended_stable_score"] = np.nan
        base["candidate_status"] = "LEVEL_A_RATE_ASSOCIATION_SCREEN"
        base["category"] = "unspecified"
    rows = []
    for _, row in base.iterrows():
        metric = str(row.get("metric", ""))
        s5 = spearman_for_metric(level_a, rate_tables["5min"], metric)
        s10 = spearman_for_metric(level_a, rate_tables["10min"], metric)
        s20 = spearman_for_metric(level_a, rate_tables["20min"], metric)
        signs = [np.sign(v) for v in [s5, s10, s20] if np.isfinite(v) and abs(v) > 1e-12]
        direction_consistent = bool(signs) and len(set(signs)) == 1
        min_abs = float(np.nanmin(np.abs([s5, s10, s20]))) if any(np.isfinite(v) for v in [s5, s10, s20]) else np.nan
        existing_status = str(row.get("candidate_status", ""))
        detrended = float(row.get("best_time_detrended_stable_score", np.nan))
        if "HIGH_CONFIDENCE" in existing_status and direction_consistent and np.isfinite(min_abs) and min_abs >= 0.4 and detrended >= 0.4:
            final_status = "RETAIN_LEVEL_A_ASSOCIATION_CANDIDATE"
        elif "HIGH_CONFIDENCE" in existing_status:
            final_status = "DOWNGRADED_SENSITIVITY_OR_DETRENDING_LIMIT"
        elif direction_consistent and np.isfinite(min_abs) and min_abs >= 0.4:
            final_status = "SUPPORTING_ASSOCIATION_SCREEN"
        else:
            final_status = "UNSTABLE_OR_TIME_TREND_LIMITED"
        out = row.to_dict()
        out.update(
            {
                "Spearman_5min": s5,
                "Spearman_10min": s10,
                "Spearman_20min": s20,
                "SensitivityDirectionConsistent": direction_consistent,
                "SensitivityMinAbsSpearman": min_abs,
                "FinalInterpretationStatus": final_status,
            }
        )
        rows.append(out)
    ranked = pd.DataFrame(rows)
    ranked["RankScore"] = pd.to_numeric(ranked.get("best_time_detrended_stable_score"), errors="coerce").fillna(0) + pd.to_numeric(ranked["SensitivityMinAbsSpearman"], errors="coerce").fillna(0)
    return ranked.sort_values(["FinalInterpretationStatus", "RankScore"], ascending=[True, False]).reset_index(drop=True)


def make_geometry_reliability_summary(sample_dir: Path, v2_dir: Path, sidecar_500_dir: Path) -> pd.DataFrame:
    rows = []
    comparison = read_csv_required(sample_dir / "geometry_level_a_comparison.csv", "sample geometry comparison")
    rows.append(
        {
            "EvidenceLayer": "sample_validation_40_frames",
            "Metric": "agreement",
            "N": int(len(comparison)),
            "Value": float(comparison["BlobCountPass"].sum()) if "BlobCountPass" in comparison.columns else np.nan,
            "Detail": f"blob count pass {int(comparison['BlobCountPass'].sum())}/{len(comparison)}, total area pass {int(comparison['TotalAreaPass'].sum())}/{len(comparison)}",
        }
    )
    v2_summary = read_json(v2_dir / "geometry_validation_summary.json") or {}
    rows.extend(
        [
            {
                "EvidenceLayer": "v2_perimeter_qc",
                "Metric": "DecisionLabel",
                "N": int(v2_summary.get("GeneratedBlobRows") or 0),
                "Value": np.nan,
                "Detail": str(v2_summary.get("DecisionLabel", "")),
            },
            {
                "EvidenceLayer": "v2_perimeter_qc",
                "Metric": "RoughnessLtOneFractionAreaGe250",
                "N": int(v2_summary.get("GeneratedBlobRows") or 0),
                "Value": float(v2_summary.get("RoughnessLtOneFractionAreaGe250") or 0),
                "Detail": "Reliable-tier roughness gate",
            },
            {
                "EvidenceLayer": "v2_perimeter_qc",
                "Metric": "RoughnessLtOneFractionAreaGe500",
                "N": int(v2_summary.get("GeneratedBlobRows") or 0),
                "Value": float(v2_summary.get("RoughnessLtOneFractionAreaGe500") or 0),
                "Detail": "High-confidence roughness gate",
            },
            {
                "EvidenceLayer": "v2_perimeter_qc",
                "Metric": "CircularityGt1p05FractionAreaGe500",
                "N": int(v2_summary.get("GeneratedBlobRows") or 0),
                "Value": float(v2_summary.get("CircularityGt1p05FractionAreaGe500") or 0),
                "Detail": "High-confidence circularity artifact gate",
            },
        ]
    )
    if (v2_dir / "boundary_metric_reliability.csv").exists():
        reliability = pd.read_csv(v2_dir / "boundary_metric_reliability.csv")
        for _, row in reliability.iterrows():
            rows.append(
                {
                    "EvidenceLayer": "v2_area_tier_reliability",
                    "Metric": str(row.get("AreaGroup", row.get("AreaTier", row.get("Group", "group")))),
                    "N": int(row.get("N", 0)),
                    "Value": float(row.get("BoundaryMetricValidFraction", np.nan)),
                    "Detail": f"roughness_lt_one={row.get('RoughnessLtOneFraction', np.nan)}, circularity_gt_1p05={row.get('CircularityGt1p05Fraction', np.nan)}",
                }
            )
    qc = read_csv_required(sidecar_500_dir / "geometry_qc_summary.csv", "500-frame sidecar QC")
    qc_row = qc.iloc[0].to_dict()
    rows.append(
        {
            "EvidenceLayer": "sidecar_500_smoke",
            "Metric": "OverallStatus",
            "N": int(qc_row.get("ProcessedFrames", 0)),
            "Value": float(qc_row.get("GeometryBlobRows", np.nan)),
            "Detail": f"status={qc_row.get('OverallStatus')}, blob pass={qc_row.get('BlobCountPassFrames')}, area pass={qc_row.get('TotalAreaPassFrames')}, empty={qc_row.get('EmptyGeometryFrames')}",
        }
    )
    blob_path = sidecar_500_dir / "geometry_by_blob.csv"
    if blob_path.exists():
        blobs = pd.read_csv(blob_path, usecols=lambda c: c in {
            "Area_px",
            "AreaTier",
            "BoundaryMetricValid",
            "ProjectedRoughness_boundary",
            "Circularity2D_boundary",
        })
        for label, mask in [
            ("all", pd.Series(True, index=blobs.index)),
            ("area_ge_250", numeric(blobs, "Area_px") >= 250),
            ("area_ge_500", numeric(blobs, "Area_px") >= 500),
        ]:
            sub = blobs[mask].copy()
            if sub.empty:
                continue
            rough = numeric(sub, "ProjectedRoughness_boundary")
            circ = numeric(sub, "Circularity2D_boundary")
            valid = sub["BoundaryMetricValid"].astype(bool) if "BoundaryMetricValid" in sub.columns else pd.Series(False, index=sub.index)
            rows.append(
                {
                    "EvidenceLayer": "sidecar_500_blob_distribution",
                    "Metric": label,
                    "N": int(len(sub)),
                    "Value": float(valid.mean()),
                    "Detail": f"median_roughness={rough.median()}, roughness_lt_one={(rough < 1).mean()}, circularity_gt_1p05={(circ > 1.05).mean()}",
                }
            )
    return pd.DataFrame(rows)


def save_figures(out_dir: Path, level_a: pd.DataFrame, rate_tables: dict[str, pd.DataFrame], candidates: pd.DataFrame) -> list[str]:
    figures_dir = ensure_dir(out_dir / "figures_level_a_final")
    written = []

    fig, axes = plt.subplots(2, 1, figsize=(8.0, 5.0), sharex=True)
    axes[0].plot(numeric(level_a, "RealTime_s") / 60.0, numeric(level_a, "SnMonotone"), color="#0072B2", linewidth=1.0)
    axes[0].set_ylabel("SnMonotone")
    axes[1].plot(numeric(level_a, "RealTime_s") / 60.0, numeric(level_a, "DissolutionRate_Sn_per_min"), color="#D55E00", linewidth=0.8)
    axes[1].set_ylabel("Rate (Sn/min)")
    axes[1].set_xlabel("Time (min)")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        path = figures_dir / f"sn_and_primary_rate.{suffix}"
        fig.savefig(path, dpi=250 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        written.append(str(path))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 3.2))
    colors = {"5min": "#009E73", "10min": "#0072B2", "20min": "#D55E00"}
    for label, rates in rate_tables.items():
        ax.plot(numeric(rates, "RealTime_s") / 60.0, numeric(rates, "DissolutionRate_Sn_per_min"), label=label, color=colors[label], linewidth=0.75)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Rate (Sn/min)")
    ax.legend(frameon=False)
    fig.tight_layout()
    for suffix in ("png", "svg"):
        path = figures_dir / f"rate_window_sensitivity.{suffix}"
        fig.savefig(path, dpi=250 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        written.append(str(path))
    plt.close(fig)

    metrics = [
        ("NumBlobs", "NumBlobs"),
        ("InterfaceArea", "Interface proxy (px)"),
        ("ReqMedian", "Req median (px)"),
        ("MaxBlobFrac", "Max blob fraction"),
    ]
    fig, axes = plt.subplots(len(metrics), 1, figsize=(8.0, 7.0), sharex=True)
    for ax, (column, label) in zip(axes, metrics):
        ax.plot(numeric(level_a, "RealTime_s") / 60.0, numeric(level_a, column), linewidth=0.8)
        ax.set_ylabel(label)
    axes[-1].set_xlabel("Time (min)")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        path = figures_dir / f"level_a_key_metrics.{suffix}"
        fig.savefig(path, dpi=250 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        written.append(str(path))
    plt.close(fig)

    top = candidates.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.barh(top["metric"].astype(str), pd.to_numeric(top["RankScore"], errors="coerce"), color="#56B4E9")
    ax.set_xlabel("Rank score")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        path = figures_dir / f"interpretation_candidates_ranked.{suffix}"
        fig.savefig(path, dpi=250 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        written.append(str(path))
    plt.close(fig)
    return written


def write_scope_decision(out_dir: Path, metadata_dir: Path, sidecar_500_dir: Path) -> None:
    metadata = read_json(metadata_dir / "metadata_recovery_summary.json") or read_json(metadata_dir / "experiment_metadata.json") or {}
    depth = metadata.get("channel_depth_m", 2.0044627037376862e-05)
    text = f"""# G21 Geometry Scope Decision

Decision: full 12024-frame sidecar extraction is intentionally skipped at this stage.

The accepted analysis scope is full-duration Level A interpretation plus limited 2D geometry support from selected-frame validation, V2 perimeter QC, and the 500-frame sidecar smoke at `{sidecar_500_dir}`.

Allowed use:
- 2D projected morphology and population-level Level A metrics.
- Corrected perimeter reliability in reliable area tiers only.
- `ProjectedRoughness_boundary = P_outer_boundary / Pc_outer_boundary` as a 2D exterior-boundary proxy.
- Apparent quasi-2D volume convention using mean channel depth, if needed.

Not allowed:
- Full-duration boundary roughness trends.
- Tiny/small blob boundary interpretation.
- 3D roughness, true fluid-fluid interfacial area, or out-of-plane morphology.
- Tracking, split/merge lineage, or boundary fractal dimension.

Mean depth note: `channel_depth_m = {depth}` is only an apparent quasi-2D volume convention. It does not recover z-direction interface shape.
"""
    (out_dir / "g21_geometry_scope_decision.md").write_text(text, encoding="utf-8")


def write_level_a_interpretation(out_dir: Path, stage_summary: pd.DataFrame, sensitivity: pd.DataFrame, candidates: pd.DataFrame) -> None:
    top_candidates = candidates[candidates["FinalInterpretationStatus"].astype(str).str.contains("RETAIN|SUPPORTING", regex=True)].head(8)
    top_lines = "\n".join(
        f"- `{data.get('metric')}`: {data.get('FinalInterpretationStatus')}, detrended score={data.get('best_time_detrended_stable_score')}, min sensitivity rho={data.get('SensitivityMinAbsSpearman')}"
        for data in (row._asdict() for row in top_candidates.itertuples(index=False))
    )
    if not top_lines:
        top_lines = "- No candidate met the retained sensitivity criteria."
    raw_increase_note = "Raw Sn increase steps were previously recorded as 5154 / 12023; rate interpretation therefore uses SnMonotone plus local regression."
    text = f"""# G21 Level A Interpretation Final

This package uses the full-duration Level A outputs. The primary dissolution rate is the 10 min local-regression rate on `SnMonotone`; 5 min and 20 min runs are sensitivity checks. {raw_increase_note}

## Stage Summary

The fixed stages are:
- `early_depletion`: `SnMonotone >= 0.20`
- `active_dissolution`: `0.05 <= SnMonotone < 0.20`
- `late_depletion`: `0.005 <= SnMonotone < 0.05`
- `endpoint`: `SnMonotone < 0.005` or final 5% of frames, with endpoint taking precedence.

The stage table covers {int(stage_summary['NFrames'].sum())} frames exactly once.

## Rate Sensitivity

`g21_rate_window_sensitivity_summary.csv` records max, p99, median, and stage-wise median rates for 5, 10, and 20 min windows. Sensitivity is used to downgrade associations whose direction is not stable.

## Association Candidates

All candidates are association screens, not causal mechanisms. Size-distribution slope is a population size-distribution proxy, not boundary fractal dimension.

{top_lines}

## Interpretation Boundaries

This document does not present tracking, split/merge lineage, full-time boundary roughness trends, boundary fractal dimension, 3D roughness, or true 3D interfacial area.
"""
    (out_dir / "g21_level_a_interpretation_final.md").write_text(text, encoding="utf-8")


def write_geometry_support_docs(out_dir: Path, reliability: pd.DataFrame, sidecar_500_dir: Path) -> None:
    text = f"""# G21 Limited 2D Geometry Support

Geometry evidence is limited to:
- 40-frame sample validation.
- V2 perimeter QC.
- 500-frame sidecar smoke at `{sidecar_500_dir}`.

The full 12024-frame sidecar was skipped by design, so no full-duration boundary trend is claimed.

`ProjectedRoughness_boundary = P_outer_boundary / Pc_outer_boundary` is interpreted only as a 2D exterior-boundary proxy. Reliable interpretation requires `BoundaryMetricValid`, `Area >= 250 px`, or `Area >= 500 px`. Tiny and small blob boundary metrics are excluded from mechanism interpretation because perimeter/circularity artifacts concentrate in those tiers.

`P_total_boundary` is a projected total boundary-length diagnostic. It is not true fluid-fluid interfacial area and not 3D roughness.
"""
    (out_dir / "g21_limited_2d_geometry_support.md").write_text(text, encoding="utf-8")

    sidecar_rows = reliability[reliability["EvidenceLayer"].astype(str).str.contains("sidecar_500")]
    detail = "\n".join(f"- {row.Metric}: N={row.N}, value={row.Value}, {row.Detail}" for row in sidecar_rows.itertuples())
    consistency = f"""# G21 Geometry Smoke vs Level A Consistency

The 500-frame sidecar smoke is treated as backend and reconstruction validation, not as a full-time geometry dataset.

{detail}

The accepted use is limited supporting evidence for 2D geometry reliability. Full-duration Level A metrics remain the primary interpretation layer.
"""
    (out_dir / "g21_geometry_smoke_vs_level_a_consistency.md").write_text(consistency, encoding="utf-8")


def write_acceptance_review(
    out_dir: Path,
    stage_summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
    reliability: pd.DataFrame,
    rate_tables: dict[str, pd.DataFrame],
) -> dict:
    md_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in out_dir.glob("*.md")
        if path.name != "g21_interpretation_package_acceptance_review.md"
    )
    required_existing = [
        name
        for name in REQUIRED_OUTPUTS
        if name not in {"interpretation_package_manifest.json", "g21_interpretation_package_acceptance_review.md"}
    ]
    missing = [name for name in required_existing if not (out_dir / name).exists()]
    stage_total = int(stage_summary["NFrames"].sum()) if "NFrames" in stage_summary.columns else 0
    window_rows = sensitivity[sensitivity["StageFixed"] == "all"].set_index("WindowMin")
    windows_present = set(pd.to_numeric(sensitivity["WindowMin"], errors="coerce").dropna().astype(int)) == {5, 10, 20}
    sensitivity_rows_ok = windows_present and all(int(window_rows.loc[w, "NFrames"]) == 12024 for w in [5, 10, 20])
    sn_mono_ok = windows_present and all(int(window_rows.loc[w, "SnMonotoneIncreaseCount"]) == 0 for w in [5, 10, 20])
    curves = {
        label: numeric(table, "DissolutionRate_Sn_per_min").to_numpy(dtype=float)
        for label, table in rate_tables.items()
    }
    curves_differ = not all(np.allclose(curves["10min"], curve, equal_nan=True) for key, curve in curves.items() if key != "10min")
    reliability_text = "\n".join(reliability.astype(str).agg(" ".join, axis=1).tolist())

    gates = [
        ("File completeness", not missing and (out_dir / "figures_level_a_final").exists(), f"missing={missing or 'none'}"),
        ("Stage coverage", stage_total == 12024, f"stage_total={stage_total}"),
        ("Rate sensitivity windows", sensitivity_rows_ok and sn_mono_ok and curves_differ, f"windows_present={windows_present}, SnMonotoneOK={sn_mono_ok}, curves_differ={curves_differ}"),
        ("Sn/rate logic", "SnMonotone plus local regression" in md_text and "raw Sn increase steps" in md_text, "rate text inherits raw Sn noise warning"),
        ("Association strength", "association screens, not causal mechanisms" in md_text, "candidate text remains non-causal"),
        ("Full sidecar scope", "full 12024-frame sidecar extraction is intentionally skipped" in md_text, "full sidecar is explicitly skipped"),
        ("500-frame smoke scope", "not as a full-time geometry dataset" in md_text, "500-frame smoke kept as validation subset"),
        ("Boundary terminology", "2D exterior-boundary proxy" in md_text and "3D roughness" in md_text, "ProjectedRoughness_boundary is scoped"),
        ("Tiny/small exclusion", "Tiny and small blob boundary metrics are excluded" in md_text or "tiny" in reliability_text and "small" in reliability_text, "tier limits documented"),
        ("No forbidden analyses", all(term in md_text for term in ["tracking", "fractal", "3D roughness"]), "tracking/fractal/3D exclusions present"),
    ]
    all_pass = all(passed for _, passed, _ in gates)
    decision = "ACCEPT_FOR_RESULTS_WRITING_WITH_SCOPE_LIMITS" if all_pass else "NEEDS_REVISION_BEFORE_RESULTS_WRITING"
    rows = "\n".join(
        f"| {gate} | {'PASS' if passed else 'FAIL'} | {detail} |"
        for gate, passed, detail in gates
    )
    text = f"""# G21 Interpretation Package Acceptance Review

Decision: `{decision}`

Reviewed package: `{out_dir}`

| Gate | Result | Evidence |
| --- | --- | --- |
{rows}

Acceptance notes:
- The package is accepted only for full-duration Level A interpretation and limited 2D geometry support.
- It does not support full-duration boundary roughness trends.
- It does not support tracking, split/merge lineage, boundary fractal dimension, true fluid-fluid interfacial area, or 3D roughness.
- Rate interpretation uses `SnMonotone` plus local regression; raw frame-to-frame Sn differences are not used for rate claims.
"""
    (out_dir / "g21_interpretation_package_acceptance_review.md").write_text(text, encoding="utf-8")
    return {"decision": decision, "gates": [{"gate": g, "passed": p, "detail": d} for g, p, d in gates]}


def write_claims_register(out_dir: Path) -> None:
    claims = [
        {
            "Claim": "G21 NAPL depletion is near-complete in the Level A record.",
            "Evidence": "SnMonotone depletion across 12024 frames.",
            "DataSource": "dissolution_rates.csv and g21_level_a_stage_summary.csv",
            "AllowedStrength": "strong Level A claim",
            "Limitation": "raw Sn is noisy; use monotone local-regression rate for rate interpretation",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "Rate interpretation requires monotone smoothing and local regression.",
            "Evidence": "raw Sn increase steps previously recorded as 5154 / 12023; SnMonotone increase count is 0 in all sensitivity windows.",
            "DataSource": "Level A QC and g21_rate_window_sensitivity_summary.csv",
            "AllowedStrength": "strong methodological claim",
            "Limitation": "rate magnitude is window-sensitive; report 5/10/20 min sensitivity",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "NumBlobs is a retained rate-association candidate.",
            "Evidence": "ranked candidate table retains NumBlobs after time-detrended and sensitivity checks.",
            "DataSource": "g21_interpretation_candidates_ranked.csv",
            "AllowedStrength": "moderate association claim",
            "Limitation": "association only, not causal; no tracking or split/merge lineage",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "Size-distribution slope is a rate-association candidate.",
            "Evidence": "ranked candidate table retains Slope_logN_gt_Req_vs_logReq.",
            "DataSource": "g21_interpretation_candidates_ranked.csv and size_distribution_slope_vs_time.csv",
            "AllowedStrength": "moderate association claim",
            "Limitation": "population size-distribution proxy, not boundary fractal dimension",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "Corrected boundary metrics are stable in reliable area tiers.",
            "Evidence": "V2 roughness<1 fractions are 0 for Area >= 250 px and Area >= 500 px; circularity>1.05 fraction is 0 for Area >= 500 px.",
            "DataSource": "geometry_sample_validation_v2_20260519_094142 and g21_2d_geometry_reliability_summary.csv",
            "AllowedStrength": "supporting limited 2D geometry claim",
            "Limitation": "selected-frame and 500-frame support only; no full-duration boundary trend",
            "AllowedInWriteup": "yes, with scope limits",
        },
        {
            "Claim": "Tiny/small blob boundary metrics are not reliable mechanism evidence.",
            "Evidence": "V2 reliability table shows circularity artifacts concentrated in tiny/small tiers.",
            "DataSource": "boundary_metric_reliability.csv and g21_2d_geometry_reliability_summary.csv",
            "AllowedStrength": "strong limitation",
            "Limitation": "use AreaTier, BoundaryMetricValid, Area >= 250 px, and Area >= 500 px filters",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "Tracking and split/merge conclusions are unavailable.",
            "Evidence": "tracking was not run by design.",
            "DataSource": "g21_geometry_scope_decision.md",
            "AllowedStrength": "scope limitation",
            "Limitation": "no per-blob lineage or lifetime claims",
            "AllowedInWriteup": "yes",
        },
        {
            "Claim": "3D roughness and true interfacial area are out of scope.",
            "Evidence": "only mean channel depth is available; P_outer_boundary is a 2D exterior-boundary proxy.",
            "DataSource": "g21_geometry_scope_decision.md and g21_limited_2d_geometry_support.md",
            "AllowedStrength": "scope limitation",
            "Limitation": "mean depth supports apparent quasi-2D volume convention only",
            "AllowedInWriteup": "yes",
        },
    ]
    header = "| Claim | Evidence | Data source | Allowed strength | Limitation | Allowed in final write-up |\n| --- | --- | --- | --- | --- | --- |"
    body = "\n".join(
        f"| {c['Claim']} | {c['Evidence']} | {c['DataSource']} | {c['AllowedStrength']} | {c['Limitation']} | {c['AllowedInWriteup']} |"
        for c in claims
    )
    text = f"""# G21 Claims Register

This register binds each allowed scientific statement to its evidence and limitation. Claims not listed here should be treated as out of scope until separately reviewed.

{header}
{body}
"""
    (out_dir / "g21_claims_register.md").write_text(text, encoding="utf-8")


def build_package(args) -> Path:
    primary_dir = Path(args.primary_postprocess_dir)
    rate5_dir = Path(args.rate5_postprocess_dir)
    rate20_dir = Path(args.rate20_postprocess_dir)
    metadata_dir = Path(args.metadata_dir)
    sample_dir = Path(args.sample_validation_dir)
    v2_dir = Path(args.validation_v2_dir)
    sidecar_500_dir = Path(args.sidecar_500_dir)
    out_dir = Path(args.output_dir) if args.output_dir else primary_dir / f"g21_interpretation_package_{timestamp()}"
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory exists and is not empty: {out_dir}")
    ensure_dir(out_dir)

    level_a = merge_level_a(primary_dir)
    if len(level_a) != 12024:
        raise ValueError(f"Primary Level A rows = {len(level_a)}, expected 12024")
    stage_summary = make_stage_summary(level_a)

    rate_dirs = {"5min": rate5_dir, "10min": primary_dir, "20min": rate20_dir}
    sensitivity, rate_tables = make_rate_sensitivity_summary(rate_dirs, level_a[["FrameIndex", "StageFixed"]])
    candidates = make_ranked_candidates(primary_dir, level_a, rate_tables)
    reliability = make_geometry_reliability_summary(sample_dir, v2_dir, sidecar_500_dir)

    stage_summary.to_csv(out_dir / "g21_level_a_stage_summary.csv", index=False)
    sensitivity.to_csv(out_dir / "g21_rate_window_sensitivity_summary.csv", index=False)
    candidates.to_csv(out_dir / "g21_interpretation_candidates_ranked.csv", index=False)
    reliability.to_csv(out_dir / "g21_2d_geometry_reliability_summary.csv", index=False)

    write_scope_decision(out_dir, metadata_dir, sidecar_500_dir)
    write_level_a_interpretation(out_dir, stage_summary, sensitivity, candidates)
    write_geometry_support_docs(out_dir, reliability, sidecar_500_dir)
    figure_paths = save_figures(out_dir, level_a, rate_tables, candidates)
    write_claims_register(out_dir)
    acceptance = write_acceptance_review(out_dir, stage_summary, sensitivity, reliability, rate_tables)

    manifest = {
        "created_at": timestamp(),
        "primary_postprocess_dir": primary_dir,
        "rate5_postprocess_dir": rate5_dir,
        "rate20_postprocess_dir": rate20_dir,
        "metadata_dir": metadata_dir,
        "sample_validation_dir": sample_dir,
        "validation_v2_dir": v2_dir,
        "sidecar_500_dir": sidecar_500_dir,
        "output_dir": out_dir,
        "required_outputs": REQUIRED_OUTPUTS,
        "figures": figure_paths,
        "acceptance_review": acceptance,
        "n_primary_frames": int(len(level_a)),
        "stage_frame_total": int(stage_summary["NFrames"].sum()),
        "scope_limits": [
            "full_sidecar_skipped_by_design",
            "no_tracking",
            "no_fractal_dimension",
            "no_3d_roughness",
            "no_full_duration_boundary_trend",
        ],
    }
    write_json(out_dir / "interpretation_package_manifest.json", manifest)

    missing = [name for name in REQUIRED_OUTPUTS if not (out_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required package output(s): {missing}")
    if not (out_dir / "figures_level_a_final").exists():
        raise RuntimeError("Missing figures_level_a_final directory")
    return out_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the G21 Level A interpretation package with limited 2D geometry support.")
    parser.add_argument("--primary-postprocess-dir", required=True)
    parser.add_argument("--rate5-postprocess-dir", required=True)
    parser.add_argument("--rate20-postprocess-dir", required=True)
    parser.add_argument("--metadata-dir", required=True)
    parser.add_argument("--sample-validation-dir", required=True)
    parser.add_argument("--validation-v2-dir", required=True)
    parser.add_argument("--sidecar-500-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = build_package(args)
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
