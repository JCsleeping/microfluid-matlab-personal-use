import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import tifffile

from run_a1_1bo_6ul_make_full_frames_manifest import build_rows
from run_a1_1bo_6ul_make_full_frames_manifest import label_for_production
from run_dnapl_branch_c_timeseries_tool import (
    analysis_command,
    build_paths,
    command_text,
    finalize_blob_detail_chunks,
    manifest_command,
    parse_steps,
    run_command,
    residual_command,
    segmorph_artifact_quality,
    segmorph_chunk_complete,
    segmorph_completed_frame,
    segmorph_interface_quality,
    segmentation_commands,
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


def test_manifest_labels_03_water_frames_as_residual() -> None:
    label, role = label_for_production(Path("03 WATER 3 SECONDS_39.tif"))

    assert label == "residual_03_water_3s_39"
    assert role == "residual"


def test_manifest_labels_late_singular_second_water_frames_as_residual() -> None:
    label, role = label_for_production(Path("06 WATER 9 SECOND_37.tif"))

    assert label == "residual_06_water_9s_37"
    assert role == "residual"


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


def test_manifest_build_rows_accepts_external_napl_endpoint(tmp_path) -> None:
    endpoint_dir = tmp_path / "endpoint"
    production_dir = tmp_path / "production"
    endpoint_dir.mkdir()
    production_dir.mkdir()

    tifffile.imwrite(endpoint_dir / "00 NAPL 1 SECONDS.tif", np.zeros((2, 2, 3), dtype=np.uint8))
    tifffile.imwrite(endpoint_dir / "02 WATER 1 SECOND_21.tif", np.zeros((2, 2, 3), dtype=np.uint8))
    tifffile.imwrite(production_dir / "06 WATER 9 SECOND_37.tif", np.zeros((2, 2, 3), dtype=np.uint8))

    water_endpoints_path = tmp_path / "water_endpoints.json"
    napl_endpoints_path = tmp_path / "napl_endpoints.json"
    policy_path = tmp_path / "endpoint_policy.json"
    water_endpoints_path.write_text(
        json.dumps([{"label": "water_ep", "file_name": "00 NAPL 1 SECONDS.tif"}]),
        encoding="utf-8",
    )
    napl_endpoints_path.write_text(
        json.dumps(
            [
                {
                    "label": "full_02_water_1s_21",
                    "file_name": "02 WATER 1 SECOND_21.tif",
                    "role": "full_napl",
                    "include_in_timeseries": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "primary": {
                    "id": "A",
                    "short_name": "A",
                    "water_label": "water_ep",
                    "napl_label": "full_02_water_1s_21",
                },
                "sensitivity": {
                    "id": "B",
                    "short_name": "B",
                    "water_label": "water_ep",
                    "napl_label": "full_02_water_1s_21",
                },
            }
        ),
        encoding="utf-8",
    )

    rows, policy = build_rows(
        endpoint_dir,
        production_dir,
        True,
        None,
        "first",
        1,
        policy_path,
        water_endpoints_path,
        napl_endpoints_path,
    )

    by_label = {row["label"]: row for row in rows}
    assert "full_02_water_1s_21_p001" in by_label
    assert by_label["full_02_water_1s_21_p001"]["role"] == "full_napl"
    assert by_label["full_02_water_1s_21_p001"]["include_in_timeseries"] == 1
    assert by_label["full_02_water_1s_21_p001"]["timeseries_order"] == 1
    assert by_label["residual_06_water_9s_37_p001"]["role"] == "residual"
    assert by_label["residual_06_water_9s_37_p001"]["timeseries_order"] == 2
    assert policy["primary"]["napl_label"] == "full_02_water_1s_21_p001"


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


def test_manifest_command_passes_configured_napl_endpoints(tmp_path) -> None:
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
    napl_endpoints_path = paths["manifest_dir"] / "napl_endpoints_input.json"
    text = command_text(
        manifest_command(config, paths, None, None, napl_endpoints_path)
    )

    assert "--napl-endpoints" in text
    assert str(napl_endpoints_path) in text


def test_segmentation_commands_chunks_morphology_frame_ranges(tmp_path) -> None:
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
        "run_suffix": "full",
        "mode": "full",
        "output_root": str(tmp_path),
        "matlab_command": "matlab",
        "segmentation_metrics": {"chunk_size_frames": 2},
    }
    paths = build_paths(args, config)
    paths["cache_dir"].mkdir(parents=True)
    write_csv(
        paths["cache_dir"] / "manifest.csv",
        [
            {
                "label": f"frame_{idx}",
                "role": "residual",
                "timeseries_order": str(idx),
                "include_in_timeseries": "true",
            }
            for idx in range(1, 6)
        ],
    )

    commands = segmentation_commands(
        config,
        paths,
        paths["run_config_dir"] / "demo_full_effective.json",
        "morphology",
        write_chunk_configs=True,
    )

    assert len(commands) == 3
    chunk_paths = [
        paths["run_config_dir"] / "demo_full_segmorph_000001_000002.json",
        paths["run_config_dir"] / "demo_full_segmorph_000003_000004.json",
        paths["run_config_dir"] / "demo_full_segmorph_000005_000005.json",
    ]
    for command, chunk_path in zip(commands, chunk_paths):
        assert str(chunk_path) in command_text(command)
        assert chunk_path.is_file()

    chunk_configs = [json.loads(path.read_text(encoding="utf-8")) for path in chunk_paths]
    ranges = [
        (
            item["segmentation_metrics"]["frame_start_index"],
            item["segmentation_metrics"]["frame_end_index"],
            item["segmentation_metrics"]["resume_outputs"],
        )
        for item in chunk_configs
    ]
    assert ranges == [(1, 2, False), (3, 4, True), (5, 5, True)]


def test_segmentation_commands_resume_skips_completed_chunks(tmp_path) -> None:
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
        "run_suffix": "full",
        "mode": "full",
        "output_root": str(tmp_path),
        "matlab_command": "matlab",
        "segmentation_metrics": {
            "chunk_size_frames": 2,
            "resume_existing_outputs": True,
        },
    }
    paths = build_paths(args, config)
    paths["cache_dir"].mkdir(parents=True)
    paths["segmentation_morphology_dir"].mkdir(parents=True)
    write_csv(
        paths["cache_dir"] / "manifest.csv",
        [
            {
                "label": f"frame_{idx}",
                "role": "residual",
                "timeseries_order": str(idx),
                "include_in_timeseries": "true",
            }
            for idx in range(1, 6)
        ],
    )
    for name in ["red_mask_timeseries.csv", "red_blob_summary_timeseries.csv"]:
        write_csv(
            paths["segmentation_morphology_dir"] / name,
            [{"frame_index": "1"}, {"frame_index": "2"}],
        )

    commands = segmentation_commands(
        config,
        paths,
        paths["run_config_dir"] / "demo_full_effective.json",
        "morphology",
        write_chunk_configs=True,
    )

    assert len(commands) == 2
    assert "000003_000004" in command_text(commands[0])
    first_resume_config = json.loads(
        (
            paths["run_config_dir"] / "demo_full_segmorph_000003_000004.json"
        ).read_text(encoding="utf-8")
    )
    assert first_resume_config["segmentation_metrics"]["resume_outputs"] is True


def test_segmorph_chunk_complete_requires_incremental_csvs(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    seg_dir.mkdir()
    for name in [
        "red_mask_timeseries.csv",
        "red_blob_summary_timeseries.csv",
        "red_mask_stack_manifest.csv",
    ]:
        write_csv(
            seg_dir / name,
            [
                {"frame_index": "1", "h5_frame_index": "1"},
                {"frame_index": "2", "h5_frame_index": "2"},
            ],
        )
    (seg_dir / "red_mask_stack.h5").write_bytes(b"placeholder")
    (seg_dir / "red_blob_detail_all_frames.csv").write_text(
        "frame_index,label\n1,a\n",
        encoding="utf-8",
    )

    assert segmorph_chunk_complete(
        seg_dir,
        expected_end_frame=2,
        config={"write_mask_stack": True, "write_blob_detail": True},
    )
    assert segmorph_completed_frame(
        seg_dir,
        config={"write_mask_stack": True, "write_blob_detail": True},
    ) == 2
    assert not segmorph_chunk_complete(
        seg_dir,
        expected_end_frame=3,
        config={"write_mask_stack": True, "write_blob_detail": True},
    )


def test_segmorph_chunked_blob_detail_does_not_block_resume_completion(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    seg_dir.mkdir()
    for name in [
        "red_mask_timeseries.csv",
        "red_blob_summary_timeseries.csv",
        "red_mask_stack_manifest.csv",
    ]:
        write_csv(
            seg_dir / name,
            [
                {"frame_index": "1", "h5_frame_index": "1"},
                {"frame_index": "2", "h5_frame_index": "2"},
            ],
        )
    (seg_dir / "red_mask_stack.h5").write_bytes(b"placeholder")
    chunk_dir = seg_dir / "red_blob_detail_chunks"
    chunk_dir.mkdir()
    (chunk_dir / "red_blob_detail_000001_000002.csv").write_text(
        "frame_index,label\n1,a\n",
        encoding="utf-8",
    )
    config = {
        "write_mask_stack": True,
        "write_blob_detail": True,
        "blob_detail_output_mode": "chunked_csv",
    }

    assert segmorph_chunk_complete(seg_dir, expected_end_frame=2, config=config)
    assert segmorph_completed_frame(seg_dir, config=config) == 2


def test_segmorph_chunked_blob_detail_requires_chunk_file(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    seg_dir.mkdir()
    for name in [
        "red_mask_timeseries.csv",
        "red_blob_summary_timeseries.csv",
        "red_mask_stack_manifest.csv",
    ]:
        write_csv(
            seg_dir / name,
            [{"frame_index": "1", "h5_frame_index": "1"}],
        )
    (seg_dir / "red_mask_stack.h5").write_bytes(b"placeholder")
    config = {
        "write_mask_stack": True,
        "write_blob_detail": True,
        "blob_detail_output_mode": "chunked_csv",
    }

    assert not segmorph_chunk_complete(seg_dir, expected_end_frame=1, config=config)
    assert segmorph_completed_frame(seg_dir, config=config) == 0


def test_finalize_blob_detail_chunks_writes_single_merged_csv(tmp_path) -> None:
    seg_dir = tmp_path / "segmentation"
    chunk_dir = seg_dir / "red_blob_detail_chunks"
    chunk_dir.mkdir(parents=True)
    header = "frame_index,blob_id,label,mask_grid,processing_scale_factor\n"
    (chunk_dir / "red_blob_detail_000003_000003.csv").write_text(
        header + "3,1,frame3,processing_grid,3\n",
        encoding="utf-8",
    )
    (chunk_dir / "red_blob_detail_000001_000002.csv").write_text(
        header
        + "1,1,frame1,processing_grid,3\n"
        + "2,1,frame2,processing_grid,3\n",
        encoding="utf-8",
    )

    summary = finalize_blob_detail_chunks(
        seg_dir,
        config={"write_blob_detail": True, "blob_detail_output_mode": "chunked_csv"},
    )

    merged = seg_dir / "red_blob_detail_all_frames.csv"
    assert summary["row_count"] == 3
    assert summary["chunk_count"] == 2
    assert summary["output_csv"] == str(merged)
    assert merged.read_text(encoding="utf-8").splitlines() == [
        "frame_index,blob_id,label,mask_grid,processing_scale_factor",
        "1,1,frame1,processing_grid,3",
        "2,1,frame2,processing_grid,3",
        "3,1,frame3,processing_grid,3",
    ]


def test_run_command_tolerates_nonzero_when_completion_check_passes(monkeypatch) -> None:
    def fake_run(command, cwd, check):
        assert check is False
        return SimpleNamespace(returncode=3221226356, args=command)

    monkeypatch.setattr("run_dnapl_branch_c_timeseries_tool.subprocess.run", fake_run)
    commands = []

    status = run_command(
        ["matlab", "-batch", "done"],
        dry_run=False,
        commands=commands,
        completion_check=lambda: True,
        completion_label="segmorph chunk 1-2",
    )

    assert status == "completed_with_nonzero"
    assert commands


def test_run_command_tolerates_nonzero_when_partial_progress_advances(monkeypatch) -> None:
    def fake_run(command, cwd, check):
        assert check is False
        return SimpleNamespace(returncode=3221226356, args=command)

    monkeypatch.setattr("run_dnapl_branch_c_timeseries_tool.subprocess.run", fake_run)

    status = run_command(
        ["matlab", "-batch", "partial"],
        dry_run=False,
        commands=[],
        partial_progress_check=lambda: True,
        completion_label="segmorph chunk 3-4",
    )

    assert status == "partial_with_nonzero"


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
