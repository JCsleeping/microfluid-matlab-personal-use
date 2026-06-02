from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


def load_residual_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "residual"
        / "compute_residual_trapping_metrics.py"
    )
    spec = importlib.util.spec_from_file_location("compute_residual_trapping_metrics", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def make_inputs(tmp_path: Path):
    residual = load_residual_module()
    primary = tmp_path / "S_NAPL_color_primary_A_realtime.csv"
    sensitivity = tmp_path / "S_NAPL_color_sensitivity_B_realtime.csv"
    comparison = tmp_path / "S_NAPL_color_A_B_sensitivity_comparison_realtime.csv"
    mask = tmp_path / "red_mask_timeseries_realtime.csv"
    xzone = tmp_path / "S_NAPL_color_xzones_primary_A_realtime.csv"
    out_dir = tmp_path / "out"
    return residual, primary, sensitivity, comparison, mask, xzone, out_dir


def test_residual_trapping_outputs_retention_and_structure_proxy(tmp_path: Path):
    residual, primary, sensitivity, comparison, mask, xzone, out_dir = make_inputs(tmp_path)
    write_csv(
        primary,
        [
            frame_row("f1", "full_napl", 1, 0, 1.0),
            frame_row("f2", "full_napl", 2, 3, 0.9),
            frame_row("r1", "residual", 3, 4, 0.2),
            frame_row("r2", "residual", 4, 5, 0.3),
        ],
    )
    write_csv(
        sensitivity,
        [
            frame_row("f1", "full_napl", 1, 0, 0.98),
            frame_row("f2", "full_napl", 2, 3, 0.96),
            frame_row("r1", "residual", 3, 4, 0.19),
            frame_row("r2", "residual", 4, 5, 0.29),
        ],
    )
    write_csv(
        comparison,
        [
            comparison_row("f1", 0.02, -0.02),
            comparison_row("f2", 0.06, 0.06),
            comparison_row("r1", 0.01, -0.01),
            comparison_row("r2", 0.01, -0.01),
        ],
    )
    write_csv(
        mask,
        [
            mask_row("f1", "full_napl", 0.4, 3, 0.9),
            mask_row("f2", "full_napl", 0.5, 4, 0.8),
            mask_row("r1", "residual", 0.1, 50, 0.1),
            mask_row("r2", "residual", 0.2, 60, 0.2),
        ],
    )
    write_csv(
        xzone,
        [
            xzone_row("f1", 1.0, 0.9, 0.8),
            xzone_row("f2", 0.9, 0.8, 0.7),
            xzone_row("r1", 0.2, 0.1, 0.3),
            xzone_row("r2", 0.3, 0.2, 0.4),
        ],
    )

    summary = residual.build_outputs(
        residual.Inputs(
            primary_csv=primary,
            sensitivity_csv=sensitivity,
            comparison_csv=comparison,
            mask_csv=mask,
            xzone_csv=xzone,
            out_dir=out_dir,
        )
    )
    rows = read_csv(out_dir / "residual_trapping_timeseries.csv")
    summary_rows = read_csv(out_dir / "residual_trapping_summary.csv")

    r1 = next(row for row in rows if row["label"] == "r1")
    assert summary["status"] == "pass"
    assert float(summary["baselines"]["full_baseline_S_NAPL_color_A_median"]) == 0.95
    assert float(summary["baselines"]["full_baseline_dnapl_water_length_px_median"]) == 45.0
    assert abs(float(r1["S_color_retention_ratio_A"]) - (0.2 / 0.95)) < 1e-10
    assert abs(float(r1["red_mask_retention_ratio"]) - (0.1 / 0.45)) < 1e-10
    assert abs(float(r1["L_ow_retention_ratio"]) - (10.0 / 45.0)) < 1e-10
    assert float(r1["InterfaceArea"]) == float(r1["dnapl_water_length_px"])
    assert r1["interface_semantics"] == "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area"
    assert r1["structure_proxy"] == "ganglia-rich"
    assert r1["structure_proxy_scope"] == "residual_proxy"
    assert any(
        row["section"] == "residual"
        and row["metric"] == "S_NAPL_color_A_median"
        and row["value"] == "0.25"
        for row in summary_rows
    )


def test_residual_trapping_marks_missing_mask_as_review(tmp_path: Path):
    residual, primary, _sensitivity, _comparison, mask, _xzone, out_dir = make_inputs(tmp_path)
    write_csv(
        primary,
        [
            frame_row("f1", "full_napl", 1, 0, 1.0),
            frame_row("r1", "residual", 2, 1, 0.2),
        ],
    )
    write_csv(mask, [mask_row("f1", "full_napl", 0.4, 3, 0.9)])

    summary = residual.build_outputs(
        residual.Inputs(
            primary_csv=primary,
            mask_csv=mask,
            out_dir=out_dir,
        )
    )
    rows = read_csv(out_dir / "residual_trapping_timeseries.csv")

    assert summary["status"] == "review"
    assert summary["missing_label_counts"]["mask"] == 1
    assert next(row for row in rows if row["label"] == "r1")["residual_metric_status"] == "missing_mask_label"


def test_residual_trapping_marks_missing_provided_optional_csv_as_review(tmp_path: Path):
    residual, primary, sensitivity, _comparison, mask, _xzone, out_dir = make_inputs(tmp_path)
    write_csv(
        primary,
        [
            frame_row("f1", "full_napl", 1, 0, 1.0),
            frame_row("r1", "residual", 2, 1, 0.2),
        ],
    )
    write_csv(
        sensitivity,
        [
            frame_row("f1", "full_napl", 1, 0, 0.98),
        ],
    )
    write_csv(
        mask,
        [
            mask_row("f1", "full_napl", 0.4, 3, 0.9),
            mask_row("r1", "residual", 0.1, 50, 0.1),
        ],
    )

    summary = residual.build_outputs(
        residual.Inputs(
            primary_csv=primary,
            sensitivity_csv=sensitivity,
            mask_csv=mask,
            out_dir=out_dir,
        )
    )

    assert summary["status"] == "review"
    assert summary["missing_label_counts"]["sensitivity"] == 1


def frame_row(label: str, role: str, frame_index: int, real_time_s: float, s_value: float) -> dict[str, object]:
    return {
        "frame_index": frame_index,
        "label": label,
        "role": role,
        "S_NAPL_color": s_value,
        "RealTime_s": real_time_s,
        "Time_min": real_time_s / 60,
        "Interval_s": 1,
    }


def comparison_row(label: str, abs_sensitivity: float, b_minus_a: float) -> dict[str, object]:
    return {
        "label": label,
        "abs_endpoint_sensitivity": abs_sensitivity,
        "S_NAPL_color_B_minus_A": b_minus_a,
    }


def mask_row(
    label: str,
    role: str,
    area_fraction: float,
    num_blobs: int,
    largest_fraction: float,
) -> dict[str, object]:
    red_area_px = area_fraction * 1000
    water_length_px = area_fraction * 100
    solid_length_px = area_fraction * 10
    return {
        "label": label,
        "role": role,
        "red_mask_area_px": red_area_px,
        "domain_area_px": 1000,
        "red_mask_area_fraction": area_fraction,
        "dnapl_water_length_px": water_length_px,
        "dnapl_water_length_m": "NaN",
        "dnapl_solid_length_px": solid_length_px,
        "dnapl_solid_length_m": "NaN",
        "InterfaceArea": water_length_px,
        "solid_contact_fraction": solid_length_px / (water_length_px + solid_length_px),
        "a_i_2D_proxy": water_length_px / red_area_px,
        "interface_semantics": "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area",
        "num_blobs": num_blobs,
        "component_count": num_blobs,
        "mean_blob_size": 10,
        "largest_component_fraction": largest_fraction,
        "max_blob_frac": largest_fraction,
        "Req_median": 1,
        "Req_mean": 1,
        "Req_std": 0,
        "mean_circularity": 0.5,
        "n_droplets": num_blobs,
        "n_columns": 0,
        "n_clusters": 0,
        "frac_droplets": 0.8,
        "frac_columns": 0.1,
        "frac_clusters": 0.1,
    }


def xzone_row(label: str, inlet: float, mid: float, outlet: float) -> dict[str, object]:
    return {
        "label": label,
        "S_x_inlet": inlet,
        "S_x_mid": mid,
        "S_x_outlet": outlet,
        "S_x_inlet_outlet_asymmetry": inlet - outlet,
        "active_bin_fraction_ge_0p2": 0.5,
        "active_bin_fraction_ge_0p5": 0.2,
        "napl_extent_fraction_ge_0p2": 0.5,
        "napl_extent_fraction_ge_0p5": 0.2,
    }
