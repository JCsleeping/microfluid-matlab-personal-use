import json
from types import SimpleNamespace

import numpy as np
import tifffile

from run_a1_1bo_6ul_make_full_frames_manifest import build_rows
from run_dnapl_branch_c_timeseries_tool import (
    analysis_command,
    build_paths,
    command_text,
    manifest_command,
    parse_steps,
    residual_command,
    segmorph_artifact_quality,
    segmorph_interface_quality,
    timeline_command,
    write_physical_metadata_input,
)


def test_segmorph_interface_quality_allows_empty_red_mask() -> None:
    quality = segmorph_interface_quality(
        [
            {
                "red_mask_area_px": "0",
                "dnapl_water_length_px": "0",
                "dnapl_solid_length_px": "0",
                "dnapl_water_length_m": "NaN",
                "dnapl_solid_length_m": "NaN",
                "InterfaceArea": "0",
                "solid_contact_fraction": "NaN",
                "a_i_2D_proxy": "NaN",
                "interface_semantics": "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area",
            }
        ]
    )

    assert quality["missing_columns"] == []
    assert quality["alias_mismatch_count"] == 0
    assert quality["water_length_nonpositive_with_mask_count"] == 0
    assert quality["solid_length_negative_count"] == 0
    assert quality["solid_contact_fraction_out_of_range_count"] == 0
    assert quality["a_i_2D_proxy_bad_count"] == 0
    assert quality["interface_semantics_bad_count"] == 0


def test_runner_builds_timeline_residual_analysis_commands(tmp_path) -> None:
    args = SimpleNamespace(
        manifest_dir=None,
        cache_dir=None,
        matlab_dir=None,
        segmentation_pilot_dir=None,
        segmentation_morphology_dir=None,
        timeline_dir=None,
        residual_dir=None,
        analysis_dir=None,
    )
    config = {
        "run_name": "demo",
        "run_suffix": "full3585",
        "mode": "full",
        "output_root": str(tmp_path),
        "analysis_package": {"run_label": "Demo full Branch C/C2"},
    }

    paths = build_paths(args, config)

    assert paths["timeline_dir"] == tmp_path / "timeline_postprocess" / "demo_full3585"
    assert paths["residual_dir"] == tmp_path / "residual_trapping_postprocess" / "demo_full3585"
    assert paths["analysis_dir"] == tmp_path / "analysis_package_full3585"

    timeline_text = command_text(timeline_command(config, paths))
    assert "tools\\timeline\\join_branch_c_realtime.py" in timeline_text
    assert str(paths["manifest_dir"] / "accepted_frames.csv") in timeline_text
    assert str(paths["matlab_dir"]) in timeline_text
    assert str(paths["segmentation_morphology_dir"]) in timeline_text
    assert str(paths["timeline_dir"]) in timeline_text

    residual_text = command_text(residual_command(config, paths))
    assert "tools\\residual\\compute_residual_trapping_metrics.py" in residual_text
    assert str(paths["timeline_dir"]) in residual_text
    assert str(paths["residual_dir"]) in residual_text

    analysis_text = command_text(analysis_command(config, paths))
    assert "tools\\analysis_package\\build_branch_c_analysis_package.py" in analysis_text
    assert str(paths["timeline_dir"]) in analysis_text
    assert str(paths["residual_dir"]) in analysis_text
    assert str(paths["analysis_dir"]) in analysis_text
    assert "Demo full Branch C/C2" in analysis_text


def test_manifest_build_rows_accepts_configured_water_endpoints(tmp_path) -> None:
    endpoint_dir = tmp_path / "endpoint"
    production_dir = tmp_path / "production"
    endpoint_dir.mkdir()
    production_dir.mkdir()

    for name in [
        "00 NAPL 1 SECONDS.tif",
        "01 NAPL 3 SECONDS.tif",
        "01 WATER 1 SECONDS_3.tif",
        "01 WATER 1 SECONDS_5.tif",
    ]:
        parent = endpoint_dir if "NAPL" in name else production_dir
        tifffile.imwrite(parent / name, np.zeros((2, 2, 3), dtype=np.uint8))

    endpoint_specs = [
        {"label": "water_ep_00_napl_00_1s", "file_name": "00 NAPL 1 SECONDS.tif"},
        {"label": "water_ep_01_napl_3s", "file_name": "01 NAPL 3 SECONDS.tif"},
    ]
    endpoint_policy = {
        "primary": {
            "id": "A",
            "short_name": "A",
            "water_label": "water_ep_00_napl_00_1s",
            "napl_label": "full_01_water_1s_3",
        },
        "sensitivity": {
            "id": "B",
            "short_name": "B",
            "water_label": "water_ep_01_napl_3s",
            "napl_label": "full_01_water_1s_5",
        },
    }
    endpoints_path = tmp_path / "water_endpoints.json"
    policy_path = tmp_path / "endpoint_policy.json"
    endpoints_path.write_text(json.dumps(endpoint_specs), encoding="utf-8")
    policy_path.write_text(json.dumps(endpoint_policy), encoding="utf-8")

    rows, policy = build_rows(
        endpoint_dir,
        production_dir,
        True,
        1,
        "first",
        1,
        policy_path,
        endpoints_path,
    )

    labels = {row["label"] for row in rows}
    assert "water_ep_00_napl_00_1s" in labels
    assert "water_ep_01_napl_3s" in labels
    assert "full_01_water_1s_3_p001" in labels
    assert "full_01_water_1s_5_p001" in labels
    assert policy["primary"]["napl_label"] == "full_01_water_1s_3_p001"
    assert policy["sensitivity"]["napl_label"] == "full_01_water_1s_5_p001"


def test_manifest_command_passes_configured_water_endpoints(tmp_path) -> None:
    args = SimpleNamespace(
        manifest_dir=None,
        cache_dir=None,
        matlab_dir=None,
        segmentation_pilot_dir=None,
        segmentation_morphology_dir=None,
        timeline_dir=None,
        residual_dir=None,
        analysis_dir=None,
    )
    config = {
        "run_name": "demo",
        "run_suffix": "pilot",
        "mode": "pilot",
        "output_root": str(tmp_path),
        "water_endpoint_dir": "endpoint",
        "production_dir": "production",
        "manifest": {},
    }

    paths = build_paths(args, config)
    endpoints_path = paths["manifest_dir"] / "water_endpoints_input.json"
    text = command_text(
        manifest_command(config, paths, None, endpoints_path)
    )

    assert "--water-endpoints" in text
    assert str(endpoints_path) in text


def test_runner_writes_and_passes_physical_metadata_manifest(tmp_path) -> None:
    args = SimpleNamespace(
        manifest_dir=None,
        cache_dir=None,
        matlab_dir=None,
        segmentation_pilot_dir=None,
        segmentation_morphology_dir=None,
        timeline_dir=None,
        residual_dir=None,
        analysis_dir=None,
    )
    config = {
        "run_name": "demo",
        "run_suffix": "full3585",
        "mode": "full",
        "output_root": str(tmp_path),
        "analysis_package": {"run_label": "Demo full Branch C/C2"},
        "physical_metadata": {
            "schema_version": 1,
            "trusted": False,
            "processing_scale_factor": 3,
        },
    }
    paths = build_paths(args, config)

    metadata_path = write_physical_metadata_input(config, paths)

    assert metadata_path == tmp_path / "run_configs" / "demo_full3585_physical_metadata.json"
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["processing_scale_factor"] == 3
    text = command_text(analysis_command(config, paths, metadata_path))
    assert "--physical-metadata" in text
    assert str(metadata_path) in text


def test_parse_steps_accepts_analysis_postprocess_steps() -> None:
    assert parse_steps(["validate,timeline", "residual", "analysis"]) == [
        "validate",
        "timeline",
        "residual",
        "analysis",
    ]


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(rows[0])
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(column, "")) for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_segmorph_artifact_quality_accepts_mask_stack_and_blob_detail(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    seg_dir.mkdir()
    write_csv(
        seg_dir / "red_mask_timeseries.csv",
        [
            {
                "frame_index": "1",
                "label": "frame1",
                "role": "residual",
                "red_mask_area_px": "4",
            }
        ],
    )
    write_csv(
        seg_dir / "red_mask_stack_manifest.csv",
        [
            {
                "frame_index": "1",
                "label": "frame1",
                "role": "residual",
                "h5_dataset": "/red_mask",
                "h5_frame_index": "1",
                "mask_grid": "processing_grid",
                "mask_height": "10",
                "mask_width": "12",
                "processing_scale_factor": "3",
                "score_mode": "lab_a",
                "threshold_value": "13",
                "threshold_source": "unit",
                "red_mask_area_px": "4",
                "domain_area_px": "100",
            }
        ],
    )
    write_csv(
        seg_dir / "red_blob_detail_all_frames.csv",
        [
            {
                "frame_index": "1",
                "label": "frame1",
                "role": "residual",
                "mask_grid": "processing_grid",
                "processing_scale_factor": "3",
                "Area": "4",
                "Area_processing_px2": "4",
                "Area_native_equiv_px2": "0.4444444444",
                "AspectRatio": "1.5",
                "Solidity": "0.9",
                "EulerNumber": "1",
                "TopologyType": "droplet",
            }
        ],
    )
    (seg_dir / "red_mask_stack.h5").write_bytes(b"placeholder")

    quality = segmorph_artifact_quality(
        seg_dir,
        timeseries_row_count=1,
        config={
            "write_mask_stack": True,
            "write_blob_detail": True,
            "processing_scale_factor": 3,
        },
    )

    assert quality["failures"] == []
    assert quality["mask_stack_ready"] is True
    assert quality["blob_detail_ready"] is True


def test_segmorph_artifact_quality_rejects_missing_stack_and_bad_scale(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    seg_dir.mkdir()
    write_csv(
        seg_dir / "red_mask_stack_manifest.csv",
        [
            {
                "frame_index": "1",
                "mask_grid": "processing_grid",
                "processing_scale_factor": "2",
            }
        ],
    )
    write_csv(
        seg_dir / "red_blob_detail_all_frames.csv",
        [
            {
                "frame_index": "1",
                "label": "frame1",
                "role": "residual",
                "mask_grid": "processing_grid",
                "processing_scale_factor": "2",
                "Area": "4",
                "Area_processing_px2": "4",
                "Area_native_equiv_px2": "1",
                "AspectRatio": "1.5",
                "Solidity": "0.9",
                "EulerNumber": "1",
                "TopologyType": "droplet",
            }
        ],
    )

    quality = segmorph_artifact_quality(
        seg_dir,
        timeseries_row_count=1,
        config={
            "write_mask_stack": True,
            "write_blob_detail": True,
            "processing_scale_factor": 3,
        },
    )

    assert any("red_mask_stack.h5" in failure for failure in quality["failures"])
    assert any("processing_scale_factor" in failure for failure in quality["failures"])
