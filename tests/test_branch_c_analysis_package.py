import csv
import json
from pathlib import Path

from tools.analysis_package.build_branch_c_analysis_package import (
    PackageInputs,
    build_package,
)


def test_branch_c_analysis_package_writes_figures_report_and_provenance(tmp_path: Path) -> None:
    timeline_dir = tmp_path / "timeline"
    residual_dir = tmp_path / "residual"
    out_dir = tmp_path / "analysis_package"
    timeline_dir.mkdir()
    residual_dir.mkdir()
    write_timeline_inputs(timeline_dir)
    write_residual_inputs(residual_dir)

    provenance = build_package(
        PackageInputs(
            timeline_dir=timeline_dir,
            residual_dir=residual_dir,
            out_dir=out_dir,
            run_label="unit full3585",
        )
    )

    assert provenance["status"] == "pass"
    assert (out_dir / "analysis_report.md").is_file()
    assert (out_dir / "run_commands.md").is_file()
    assert (out_dir / "analysis_parameter_summary.csv").is_file()
    assert (out_dir / "analysis_timeseries_derived.csv").is_file()
    assert (out_dir / "branch_c_legacy_plot_timeseries.csv").is_file()
    assert (out_dir / "analysis_qc_summary.csv").is_file()
    assert (out_dir / "research_parameter_alignment.csv").is_file()
    assert (out_dir / "analysis_package_provenance.json").is_file()
    figures = provenance["outputs"]["figures"]
    assert len(figures) == 11
    for outputs in figures.values():
        for path_value in outputs.values():
            path = Path(path_value)
            assert path.is_file()
            assert path.stat().st_size > 0

    report = (out_dir / "analysis_report.md").read_text(encoding="utf-8")
    assert "InterfaceArea" in report
    assert "legacy alias" in report
    assert "Derived Parameters" in report
    saved = json.loads((out_dir / "analysis_package_provenance.json").read_text(encoding="utf-8"))
    assert saved["row_counts"]["primary_rows"] == 4
    assert saved["figure_style"] == "nature_timeseries_v1"
    assert saved["analysis_policy_version"] == "branch_c_proxy_alignment_v2_physical_metadata_gate"
    assert saved["outputs"]["parameter_summary_csv"].endswith("analysis_parameter_summary.csv")
    assert saved["outputs"]["derived_timeseries_csv"].endswith("analysis_timeseries_derived.csv")
    assert saved["outputs"]["legacy_plot_timeseries_csv"].endswith("branch_c_legacy_plot_timeseries.csv")
    assert saved["outputs"]["qc_summary_csv"].endswith("analysis_qc_summary.csv")
    assert saved["outputs"]["research_parameter_alignment_csv"].endswith("research_parameter_alignment.csv")
    assert saved["derived_parameters"]["run.total_rows"] == "4"
    assert saved["derived_parameters"]["front_proxy.residual_first_outlet_zone_ge_0p2_since_residual_start_min"] == "0"

    derived_rows = read_csv(out_dir / "analysis_timeseries_derived.csv")
    assert len(derived_rows) == 4
    assert derived_rows[0]["S_color_norm"] == "0.974358974359"
    assert derived_rows[-1]["DissolutionStage_proxy"] == "active_removal"
    assert derived_rows[-1]["ValidStructure_proxy"] == "true"
    assert "DissolutionRate_time_lr_per_min" in derived_rows[0]
    assert "MaxBlobFlowFrac_proxy" in derived_rows[0]

    legacy_rows = read_csv(out_dir / "branch_c_legacy_plot_timeseries.csv")
    assert len(legacy_rows) == 4
    assert legacy_rows[0]["Sn_semantics"] == "operational_S_NAPL_color_proxy"
    assert legacy_rows[0]["AdapterWarning"] == "not_endpoint_validated_physical_Sn"
    assert legacy_rows[0]["MeanCircularity"] == "NaN"
    for column in [
        "Sn",
        "SnNorm",
        "DissolutionRate_per_min",
        "ValidStructure",
        "DissolutionStage",
        "InterfaceArea",
        "a_i_2D",
        "MaxBlobFlowFrac",
    ]:
        assert column in legacy_rows[0]

    qc_rows = read_csv(out_dir / "analysis_qc_summary.csv")
    qc = {row["metric"]: row["value"] for row in qc_rows}
    assert qc["legacy_adapter_schema_ready"] == "true"
    assert qc["legacy_plot_timeseries_ready"] == "false"
    assert qc["legacy_adapter_nonfinite_required_value_count"] == "28"
    assert qc["pv_ready"] == "false"
    assert qc["pixel_size_ready"] == "false"
    assert qc["true_fingering_ready"] == "false"

    alignment_rows = read_csv(out_dir / "research_parameter_alignment.csv")
    alignment = {row["parameter"]: row for row in alignment_rows}
    assert alignment["Sn"]["status"] == "aligned_proxy"
    assert alignment["DissolutionRate_per_min"]["status"] == "aligned_proxy"
    assert alignment["PV"]["status"] == "missing_metadata"
    assert alignment["TOA"]["status"] == "not_computable"
    assert alignment["pixel_size_um"]["status"] == "missing_metadata"
    assert alignment["AreaGini"]["status"] == "not_computable"
    assert alignment["DissolutionRate_mass_kg_per_s"]["status"] == "missing_metadata"
    assert alignment["true_fingering"]["status"] == "not_computable"


def test_branch_c_analysis_package_applies_trusted_physical_metadata(tmp_path: Path) -> None:
    timeline_dir = tmp_path / "timeline"
    residual_dir = tmp_path / "residual"
    out_dir = tmp_path / "analysis_package"
    metadata_path = tmp_path / "physical_metadata.json"
    timeline_dir.mkdir()
    residual_dir.mkdir()
    write_timeline_inputs(timeline_dir)
    write_residual_inputs(residual_dir)
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "trusted": True,
                "processing_scale_factor": 3,
                "pixel_size_um": 2.0,
                "flow_rate_ul_min": 6.0,
                "pore_volume_ul": 3.0,
                "channel_width_um": 1000.0,
                "channel_depth_um": 100.0,
                "viscosity_Pa_s": 0.001,
                "IFT_mN_m": 30.0,
            }
        ),
        encoding="utf-8",
    )

    provenance = build_package(
        PackageInputs(
            timeline_dir=timeline_dir,
            residual_dir=residual_dir,
            out_dir=out_dir,
            run_label="unit full3585",
            physical_metadata_path=metadata_path,
        )
    )

    assert provenance["physical_metadata"]["status"] == "trusted"
    assert provenance["physical_metadata"]["values"]["processing_scale_factor"] == 3.0
    assert provenance["physical_metadata"]["derived"]["pv_ready"] is True

    derived_rows = read_csv(out_dir / "analysis_timeseries_derived.csv")
    assert derived_rows[0]["processing_scale_factor"] == "3"
    assert derived_rows[0]["pixel_size_um"] == "2"
    assert derived_rows[1]["PV"] == "2"
    assert derived_rows[0]["dnapl_water_length_m"] == "0.0009"
    assert derived_rows[0]["capillary_number"] == "3.33333333333e-05"
    assert derived_rows[1]["DissolutionRate_pv_lr_per_PV"] != "NaN"

    qc_rows = read_csv(out_dir / "analysis_qc_summary.csv")
    qc = {row["metric"]: row["value"] for row in qc_rows}
    assert qc["physical_metadata_trusted"] == "true"
    assert qc["pixel_size_ready"] == "true"
    assert qc["pv_ready"] == "true"
    assert qc["capillary_number_ready"] == "true"

    alignment_rows = read_csv(out_dir / "research_parameter_alignment.csv")
    alignment = {row["parameter"]: row for row in alignment_rows}
    assert alignment["processing_scale_factor"]["status"] == "metadata_recorded"
    assert alignment["pixel_size_um"]["status"] == "metadata_ready"
    assert alignment["PV"]["status"] == "aligned_proxy"
    assert alignment["capillary_number"]["status"] == "metadata_ready"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def base_rows() -> list[dict[str, object]]:
    roles = ["full_napl", "full_napl", "residual", "residual"]
    labels = ["f1", "f2", "r1", "r2"]
    times = [0.0, 1.0, 2.0, 3.0]
    return [
        {
            "frame_index": idx + 1,
            "label": labels[idx],
            "role": roles[idx],
            "Time_min": times[idx],
            "RealTime_s": times[idx] * 60,
            "Interval_s": 60,
        }
        for idx in range(4)
    ]


def write_timeline_inputs(timeline_dir: Path) -> None:
    rows = base_rows()
    primary = []
    sensitivity = []
    comparison = []
    xzone = []
    mask = []
    blob = []
    for idx, row in enumerate(rows):
        s_a = [0.95, 1.0, 0.2, 0.18][idx]
        s_b = s_a - 0.01
        area = [0.45, 0.5, 0.1, 0.09][idx]
        water = area * 1000
        solid = area * 20
        primary.append({**row, "S_NAPL_color": s_a})
        sensitivity.append({**row, "S_NAPL_color": s_b})
        comparison.append(
            {
                **row,
                "S_NAPL_color_B_minus_A": s_b - s_a,
                "abs_endpoint_sensitivity": abs(s_b - s_a),
            }
        )
        xzone.append(
            {
                **row,
                "S_x_inlet": s_a * 0.9,
                "S_x_mid": s_a,
                "S_x_outlet": s_a * 1.1,
                "S_x_inlet_outlet_asymmetry": s_a * 0.9 - s_a * 1.1,
                "active_bin_fraction_ge_0p2": 1.0 if s_a >= 0.2 else 0.0,
                "active_bin_fraction_ge_0p5": 1.0 if s_a >= 0.5 else 0.0,
                "napl_extent_fraction_ge_0p2": 1.0 if s_a >= 0.2 else 0.0,
                "napl_extent_fraction_ge_0p5": 1.0 if s_a >= 0.5 else 0.0,
                "outlet_zone_ge_0p2": 1.0 if s_a * 1.1 >= 0.2 else 0.0,
                "outlet_zone_ge_0p5": 1.0 if s_a * 1.1 >= 0.5 else 0.0,
            }
        )
        mask_row = {
            **row,
            "red_mask_area_px": area * 10000,
            "domain_area_px": 10000,
            "red_mask_area_fraction": area,
            "num_blobs": [2, 2, 25, 30][idx],
            "component_count": [2, 2, 25, 30][idx],
            "mean_blob_size": 10,
            "max_blob_frac": [0.9, 0.85, 0.2, 0.18][idx],
            "largest_component_fraction": [0.9, 0.85, 0.2, 0.18][idx],
            "dnapl_water_length_px": water,
            "dnapl_solid_length_px": solid,
            "dnapl_water_length_m": "NaN",
            "dnapl_solid_length_m": "NaN",
            "InterfaceArea": water,
            "solid_contact_fraction": solid / (water + solid),
            "a_i_2D_proxy": water / (area * 10000),
            "interface_semantics": "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area",
        }
        mask.append(mask_row)
        blob.append(mask_row.copy())

    write_csv(timeline_dir / "S_NAPL_color_primary_A_realtime.csv", primary)
    write_csv(timeline_dir / "S_NAPL_color_sensitivity_B_realtime.csv", sensitivity)
    write_csv(timeline_dir / "S_NAPL_color_A_B_sensitivity_comparison_realtime.csv", comparison)
    write_csv(timeline_dir / "S_NAPL_color_xzones_primary_A_realtime.csv", xzone)
    write_csv(timeline_dir / "red_mask_timeseries_realtime.csv", mask)
    write_csv(timeline_dir / "red_blob_summary_timeseries_realtime.csv", blob)


def write_residual_inputs(residual_dir: Path) -> None:
    timeseries = []
    for row in base_rows():
        residual = row["role"] == "residual"
        s_a = 0.2 if residual else 1.0
        water = 100.0 if residual else 400.0
        solid = 3.0 if residual else 10.0
        timeseries.append(
            {
                **row,
                "S_NAPL_color_A": s_a,
                "S_NAPL_color_B": s_a - 0.01,
                "red_mask_retention_ratio": 0.2 if residual else 1.0,
                "L_ow_retention_ratio": 0.25 if residual else 1.0,
                "solid_contact_fraction": solid / (water + solid),
                "a_i_2D_proxy": 0.3,
                "structure_proxy": "ganglia-rich" if residual else "pool-like",
            }
        )
    write_csv(residual_dir / "residual_trapping_timeseries.csv", timeseries)
    write_csv(
        residual_dir / "residual_trapping_summary.csv",
        [{"section": "counts", "metric": "rows", "value": 4, "units": "rows", "notes": ""}],
    )
    summary = {
        "status": "pass",
        "row_counts": {"primary_rows": 4, "full_role_rows": 2, "residual_role_rows": 2},
        "missing_label_counts": {"mask": 0, "sensitivity": 0, "comparison": 0, "blob": 0, "xzone": 0},
        "summary_metrics": {
            "residual.S_NAPL_color_A_median": "0.2",
            "residual.red_mask_area_fraction_median": "0.1",
            "residual.red_mask_retention_ratio_median": "0.2",
            "residual.L_ow_retention_ratio_median": "0.25",
            "residual.solid_contact_fraction_median": "0.03",
            "residual.a_i_2D_proxy_median": "0.3",
            "residual.ganglia_area_fraction_median": "0.9",
            "final_residual.label": "r2",
            "final_residual.RealTime_s": "180",
        },
    }
    (residual_dir / "residual_trapping_summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
