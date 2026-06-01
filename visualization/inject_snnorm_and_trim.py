"""Inject SnNorm from saturation workbooks into a comparison xlsx, then trim to onset.

Usage:
    python visualization/inject_snnorm_and_trim.py ^
        "G:\...\custom_NumBlobs_data.xlsx" ^
        --sn-manifest sn_sources.csv ^
        --threshold 0.95 ^
        --out-stem "custom_NumBlobs_onset_pv0"

The sn-manifest CSV maps each ExperimentLabel to a figures_dir (or xlsx path)
that contains SnNorm vs PV data. Format:

    label,figures_dir
    4 uL,G:\...\output_A\figure_PV
    5 uL,G:\...\output_B\figure_PV
    6 uL,G:\...\output_C\figure_PV

If --sn-manifest is omitted, the script tries to find SnNorm from the
SourceWorkbook paths already recorded in the comparison xlsx.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from trim_comparison_onset import create_onset_aligned_outputs  # noqa: E402


def _load_sn_from_figures_dir(figures_dir: Path) -> pd.DataFrame | None:
    """Load PV + SnNorm from 01_saturation_decay_data.xlsx in a figures dir."""
    candidates = [
        figures_dir / "01_saturation_decay_data.xlsx",
        figures_dir / "timeseries_6panel_data.xlsx",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            with pd.ExcelFile(path) as xls:
                sheet = "data" if "data" in xls.sheet_names else xls.sheet_names[0]
                df = pd.read_excel(xls, sheet_name=sheet)
        except Exception:
            continue
        if "PV" in df.columns and "SnNorm" in df.columns:
            out = df[["PV", "SnNorm"]].copy()
            out["PV"] = pd.to_numeric(out["PV"], errors="coerce")
            out["SnNorm"] = pd.to_numeric(out["SnNorm"], errors="coerce")
            return out.dropna().drop_duplicates(subset=["PV"]).sort_values("PV")
    return None


def _load_sn_from_workbook(workbook_path: Path) -> pd.DataFrame | None:
    """Load PV + SnNorm from a workbook that may contain both."""
    if not workbook_path.exists():
        return None
    try:
        with pd.ExcelFile(workbook_path) as xls:
            sheet = "data" if "data" in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(xls, sheet_name=sheet)
    except Exception:
        return None
    if "PV" in df.columns and "SnNorm" in df.columns:
        out = df[["PV", "SnNorm"]].copy()
        out["PV"] = pd.to_numeric(out["PV"], errors="coerce")
        out["SnNorm"] = pd.to_numeric(out["SnNorm"], errors="coerce")
        return out.dropna().drop_duplicates(subset=["PV"]).sort_values("PV")
    return None


def load_sn_manifest(manifest_path: Path) -> dict[str, Path]:
    """Return {label: figures_dir} from a CSV manifest."""
    df = pd.read_csv(manifest_path, encoding="utf-8-sig")
    mapping = {}
    for _, row in df.iterrows():
        label = str(row["label"]).strip()
        if "figures_dir" in df.columns and not pd.isna(row.get("figures_dir")):
            mapping[label] = Path(str(row["figures_dir"]).strip())
        elif "workbook" in df.columns and not pd.isna(row.get("workbook")):
            mapping[label] = Path(str(row["workbook"]).strip())
    return mapping


def inject_snnorm(
    workbook_path: Path,
    sn_manifest: dict[str, Path] | None = None,
    sheet_name: str = "data",
) -> pd.DataFrame:
    """Read comparison xlsx, inject SnNorm per experiment via PV-based merge."""
    workbook_path = Path(workbook_path)
    with pd.ExcelFile(workbook_path) as xls:
        sheet = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(xls, sheet_name=sheet)

    if "SnNorm" in df.columns:
        sn = pd.to_numeric(df["SnNorm"], errors="coerce")
        if sn.notna().sum() > 0:
            print(f"  SnNorm already present ({sn.notna().sum()} finite values), skipping injection.")
            return df

    if "PV" not in df.columns:
        raise ValueError("Workbook must contain PV column for SnNorm injection.")
    if "ExperimentLabel" not in df.columns:
        raise ValueError("Workbook must contain ExperimentLabel column.")

    df["PV"] = pd.to_numeric(df["PV"], errors="coerce")
    labels = df["ExperimentLabel"].dropna().unique()
    df["SnNorm"] = np.nan

    for label in labels:
        mask = df["ExperimentLabel"] == label
        sn_data = None

        if sn_manifest and label in sn_manifest:
            source = sn_manifest[label]
            if source.is_dir():
                sn_data = _load_sn_from_figures_dir(source)
            elif source.is_file():
                sn_data = _load_sn_from_workbook(source)

        if sn_data is None and "SourceWorkbook" in df.columns:
            source_wbs = df.loc[mask, "SourceWorkbook"].dropna().unique()
            for wb in source_wbs:
                wb_path = Path(str(wb))
                parent = wb_path.parent
                sn_data = _load_sn_from_figures_dir(parent)
                if sn_data is not None:
                    break

        if sn_data is None:
            print(f"  WARNING: No SnNorm source found for '{label}', leaving NaN.")
            continue

        experiment_pv = df.loc[mask, "PV"].to_numpy(dtype=float)
        sn_pv = sn_data["PV"].to_numpy(dtype=float)
        sn_values = sn_data["SnNorm"].to_numpy(dtype=float)
        interpolated = np.interp(experiment_pv, sn_pv, sn_values, left=np.nan, right=np.nan)
        df.loc[mask, "SnNorm"] = interpolated
        finite = np.isfinite(interpolated).sum()
        print(f"  Injected SnNorm for '{label}': {finite}/{mask.sum()} points matched.")

    return df


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Inject SnNorm into a comparison workbook (from per-experiment saturation data), "
            "then trim to onset and produce PV-since-onset figures."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python visualization/inject_snnorm_and_trim.py \\\n"
            '    "G:\\...\\custom_NumBlobs_data.xlsx" \\\n'
            "    --sn-manifest sn_sources.csv \\\n"
            "    --threshold 0.95\n"
        ),
    )
    parser.add_argument("workbook", help="Comparison *_data.xlsx to inject SnNorm into and trim.")
    parser.add_argument(
        "--sn-manifest",
        default=None,
        help="CSV with label,figures_dir pointing to SnNorm sources. If omitted, auto-detect from SourceWorkbook.",
    )
    parser.add_argument("--out-dir", default=None, help="Output directory (default: same as workbook).")
    parser.add_argument("--out-stem", default=None, help="Output filename stem.")
    parser.add_argument("--threshold", type=float, default=0.98, help="Onset threshold on SnNorm.")
    parser.add_argument("--min-consecutive", type=int, default=5)
    parser.add_argument("--sheet", default="data")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--save-injected",
        action="store_true",
        help="Also save the intermediate xlsx with SnNorm injected (before trimming).",
    )
    args = parser.parse_args(argv)

    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")

    sn_manifest = None
    if args.sn_manifest:
        sn_manifest = load_sn_manifest(Path(args.sn_manifest))

    print(f"Input: {workbook_path}")
    df = inject_snnorm(workbook_path, sn_manifest=sn_manifest, sheet_name=args.sheet)

    sn_finite = pd.to_numeric(df.get("SnNorm"), errors="coerce")
    if sn_finite.isna().all():
        raise ValueError(
            "No SnNorm values could be injected. Provide --sn-manifest or ensure "
            "SourceWorkbook directories contain 01_saturation_decay_data.xlsx with PV+SnNorm."
        )

    out_dir = Path(args.out_dir) if args.out_dir else workbook_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    injected_path = out_dir / workbook_path.name.replace("_data.xlsx", "_with_snnorm_data.xlsx")
    with pd.ExcelWriter(injected_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="data", index=False)
    print(f"  Saved injected workbook: {injected_path}")

    out_stem = args.out_stem
    if not out_stem:
        stem = workbook_path.stem
        if stem.endswith("_data"):
            stem = stem[:-5]
        out_stem = f"{stem}_onset_pv0"

    create_onset_aligned_outputs(
        injected_path,
        out_dir=str(out_dir),
        out_stem=out_stem,
        threshold=args.threshold,
        onset_col="SnNorm",
        min_consecutive=args.min_consecutive,
        sheet_name="data",
        dpi=args.dpi,
    )

    if not args.save_injected:
        injected_path.unlink(missing_ok=True)

    print(f"\nDone. Output in: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
