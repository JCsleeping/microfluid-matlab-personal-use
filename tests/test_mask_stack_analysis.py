import csv
import json
from pathlib import Path

import h5py
import numpy as np

from run_dnapl_branch_c_timeseries_tool import (
    analysis_command,
    build_paths,
    command_text,
    mask_stack_analysis_command,
)
from tools.mask_stack_analysis.analyze_c2_mask_stack import run_analysis


def test_runner_builds_maskanalysis_and_analysis_commands(tmp_path: Path) -> None:
    args = type(
        "Args",
        (),
        {
            "manifest_dir": None,
            "cache_dir": None,
            "matlab_dir": None,
            "segmentation_pilot_dir": None,
            "segmentation_morphology_dir": None,
            "timeline_dir": None,
            "residual_dir": None,
            "mask_stack_analysis_dir": None,
            "analysis_dir": None,
        },
    )()
    config = {
        "run_name": "demo",
        "run_suffix": "full3585",
        "mode": "full",
        "output_root": str(tmp_path),
        "analysis_package": {"run_label": "Demo strict mask"},
    }
    paths = build_paths(args, config)

    assert paths["mask_stack_analysis_dir"] == tmp_path / "mask_stack_analysis" / "demo_full3585"

    maskanalysis_text = command_text(mask_stack_analysis_command(config, paths))
    assert "tools\\mask_stack_analysis\\analyze_c2_mask_stack.py" in maskanalysis_text
    assert str(paths["segmentation_morphology_dir"]) in maskanalysis_text
    assert str(paths["timeline_dir"]) in maskanalysis_text
    assert str(paths["mask_stack_analysis_dir"]) in maskanalysis_text

    analysis_text = command_text(analysis_command(config, paths))
    assert "--mask-analysis-dir" in analysis_text
    assert str(paths["mask_stack_analysis_dir"]) in analysis_text


def test_mask_stack_analysis_writes_toa_front_and_blob_metrics(tmp_path: Path) -> None:
    segmentation_dir = tmp_path / "segmentation"
    timeline_dir = tmp_path / "timeline"
    out_dir = tmp_path / "mask_analysis"
    cache_dir = tmp_path / "cache"
    segmentation_dir.mkdir()
    timeline_dir.mkdir()
    cache_dir.mkdir()

    masks = np.zeros((3, 5, 4), dtype=np.uint8)
    masks[0, 1:4, 0] = 1
    masks[1, 1:4, :2] = 1
    masks[2, 1:4, :4] = 1
    with h5py.File(segmentation_dir / "red_mask_stack.h5", "w") as handle:
        # MATLAB-created stacks are observed by h5py as frame,width,height;
        # the tool must transpose to the manifest processing-grid H/W.
        handle.create_dataset("/red_mask", data=np.transpose(masks, (0, 2, 1)))
    flow_domain = np.ones((5, 4), dtype=np.uint8)
    flow_domain[:, 0] = 0
    with h5py.File(cache_dir / "mask_crop.h5", "w") as handle:
        handle.create_dataset("/flow_domain_mask", data=flow_domain)
    (segmentation_dir / "segmentation_manifest.json").write_text(
        json.dumps(
            {
                "cache_dir": str(cache_dir),
                "interface_solid_dilation": 1,
                "mask_grid": "processing_grid",
                "processing_scale_factor": 3,
            }
        ),
        encoding="utf-8",
    )

    write_csv(
        segmentation_dir / "red_mask_stack_manifest.csv",
        [
            manifest_row(1, "f1", "full_napl", 5, 4, 3),
            manifest_row(2, "r1", "residual", 5, 4, 6),
            manifest_row(3, "r2", "residual", 5, 4, 12),
        ],
    )
    write_csv(
        timeline_dir / "red_mask_timeseries_realtime.csv",
        [
            {"frame_index": 1, "label": "f1", "role": "full_napl", "RealTime_s": 0, "Time_min": 0},
            {"frame_index": 2, "label": "r1", "role": "residual", "RealTime_s": 60, "Time_min": 1},
            {"frame_index": 3, "label": "r2", "role": "residual", "RealTime_s": 120, "Time_min": 2},
        ],
    )
    write_csv(
        segmentation_dir / "red_blob_detail_all_frames.csv",
        [
            blob_row(1, "f1", "full_napl", 10, 2.0, 0.9, 1, "droplet"),
            blob_row(2, "r1", "residual", 4, 3.0, 0.7, 0, "column"),
            blob_row(2, "r1", "residual", 12, 1.5, 0.8, -1, "cluster"),
            blob_row(3, "r2", "residual", 8, 4.0, 0.6, -2, "cluster"),
        ],
    )

    summary = run_analysis(
        type(
            "Args",
            (),
            {
                "segmentation_dir": segmentation_dir,
                "timeline_dir": timeline_dir,
                "out_dir": out_dir,
                "h5_dataset": "/red_mask",
                "column_active_fraction": 0.001,
                "outlet_band_fraction": 0.25,
                "outlet_active_fraction_threshold": 0.1,
                "outlet_active_min_px": 1,
                "leading_front_breakthrough_fraction": 0.95,
                "finger_band_fraction": 0.25,
                "core_flow_min_dist_px": 2.0,
            },
        )()
    )

    assert summary["status"] == "pass"
    assert summary["readiness"]["mask_stack_ready"] is True
    assert summary["readiness"]["toa_ready"] is True
    assert summary["readiness"]["mask_front_fingering_ready"] is True
    assert summary["readiness"]["phase_aware_mask_ready"] is True
    assert summary["readiness"]["geometric_core_edge_ready"] is True
    assert summary["readiness"]["blob_detail_distribution_ready"] is True
    assert summary["phase_aware"]["full_baseline_area_px"] == 3
    assert summary["phase_aware"]["final_residual_retained_from_full_fraction"] == 1.0
    assert (out_dir / "toa_frame_index.npy").is_file()
    assert (out_dir / "full_baseline_union_mask.npy").is_file()
    assert (out_dir / "residual_frequency.npy").is_file()
    assert (out_dir / "phase_retention_class.npy").is_file()
    assert (out_dir / "core_flow_mask.npy").is_file()
    assert (out_dir / "edge_band_mask.npy").is_file()
    assert json.loads((out_dir / "mask_stack_analysis_summary.json").read_text())["status"] == "pass"

    mask_rows = read_csv(out_dir / "mask_stack_analysis_timeseries.csv")
    assert len(mask_rows) == 3
    assert mask_rows[-1]["leading_front_fraction"] == "1"
    assert mask_rows[-1]["outlet_band_breakthrough"] == "true"
    assert mask_rows[-1]["toa_cumulative_arrived_fraction"] == "0.6"

    toa = np.load(out_dir / "toa_frame_index.npy")
    assert toa.shape == (5, 4)
    assert int(toa[2, 0]) == 1
    assert int(toa[2, 3]) == 3
    phase_rows = read_csv(out_dir / "phase_mask_timeseries.csv")
    assert len(phase_rows) == 3
    assert phase_rows[-1]["retained_from_full_fraction"] == "1"
    assert phase_rows[-1]["new_outside_full_px"] == "9"

    retention_class = np.load(out_dir / "phase_retention_class.npy")
    assert int(retention_class[2, 0]) == 3
    assert int(retention_class[2, 3]) == 4
    geometry_rows = read_csv(out_dir / "geometry_core_edge_timeseries.csv")
    assert len(geometry_rows) == 3
    assert geometry_rows[-1]["core_flow_area_px"] == "10"
    assert geometry_rows[-1]["edge_band_area_px"] == "5"
    assert geometry_rows[-1]["core_mask_area_px"] == "6"
    assert geometry_rows[-1]["edge_mask_area_px"] == "3"
    assert geometry_rows[-1]["core_red_mask_fraction"] == "0.6"
    assert geometry_rows[-1]["edge_red_mask_fraction"] == "0.6"

    blob_rows = read_csv(out_dir / "blob_morphology_timeseries.csv")
    by_label = {row["label"]: row for row in blob_rows}
    assert by_label["r1"]["blob_count_detail"] == "2"
    assert float(by_label["r1"]["AreaGini"]) > 0
    assert by_label["r1"]["TopologyType_cluster_count_fraction"] == "0.5"


def manifest_row(frame_index: int, label: str, role: str, height: int, width: int, area: int) -> dict[str, object]:
    return {
        "frame_index": frame_index,
        "label": label,
        "role": role,
        "time_s": "NaN",
        "h5_dataset": "/red_mask",
        "h5_frame_index": frame_index,
        "mask_grid": "processing_grid",
        "mask_height": height,
        "mask_width": width,
        "processing_scale_factor": 3,
        "score_mode": "lab_a",
        "threshold_value": 1.0,
        "threshold_source": "unit",
        "red_mask_area_px": area,
        "domain_area_px": height * width,
    }


def blob_row(
    frame_index: int,
    label: str,
    role: str,
    area: float,
    aspect: float,
    solidity: float,
    euler: float,
    topology: str,
) -> dict[str, object]:
    return {
        "frame_index": frame_index,
        "FrameIndex": frame_index - 1,
        "label": label,
        "role": role,
        "Area": area,
        "Area_processing_px2": area,
        "AspectRatio": aspect,
        "Solidity": solidity,
        "EulerNumber": euler,
        "EulerHoleCount": max(0, 1 - euler),
        "TopologyType": topology,
        "mask_grid": "processing_grid",
        "processing_scale_factor": 3,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
