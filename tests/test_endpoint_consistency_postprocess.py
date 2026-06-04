import csv
import json
from pathlib import Path

from tools.reference_audit.endpoint_consistency_postprocess import run_endpoint_consistency


def write_csv(path_value: Path, rows: list[dict[str, object]]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    with path_value.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_endpoint_consistency_flags_expanded_full_pages(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest" / "accepted_frames.csv"
    branch_c_dir = tmp_path / "branch_c"
    out_dir = tmp_path / "endpoint_audit"
    policy = tmp_path / "manifest" / "endpoint_policy.json"
    rows = [
        {
            "label": "full_a_p001",
            "role": "full_napl",
            "source_path": r"G:\demo\full_a.tif",
            "source_page": 1,
        },
        {
            "label": "full_a_p002",
            "role": "full_napl",
            "source_path": r"G:\demo\full_a.tif",
            "source_page": 2,
        },
        {
            "label": "residual_b_p001",
            "role": "residual",
            "source_path": r"G:\demo\residual_b.tif",
            "source_page": 1,
        },
    ]
    write_csv(manifest, rows)
    write_csv(
        branch_c_dir / "S_NAPL_color_primary_A.csv",
        [
            {"frame_index": 1, "label": "full_a_p001", "role": "full_napl", "S_NAPL_color": 0.99},
            {"frame_index": 2, "label": "full_a_p002", "role": "full_napl", "S_NAPL_color": 0.20},
            {"frame_index": 3, "label": "residual_b_p001", "role": "residual", "S_NAPL_color": 0.15},
        ],
    )
    write_csv(
        branch_c_dir / "S_NAPL_color_sensitivity_B.csv",
        [
            {"frame_index": 1, "label": "full_a_p001", "role": "full_napl", "S_NAPL_color": 0.98},
            {"frame_index": 2, "label": "full_a_p002", "role": "full_napl", "S_NAPL_color": 0.19},
            {"frame_index": 3, "label": "residual_b_p001", "role": "residual", "S_NAPL_color": 0.14},
        ],
    )
    write_csv(
        branch_c_dir / "S_NAPL_color_A_B_sensitivity_comparison.csv",
        [
            {
                "frame_index": 1,
                "label": "full_a_p001",
                "S_NAPL_color_B_minus_A": -0.01,
                "abs_endpoint_sensitivity": 0.01,
            },
            {
                "frame_index": 2,
                "label": "full_a_p002",
                "S_NAPL_color_B_minus_A": -0.01,
                "abs_endpoint_sensitivity": 0.01,
            },
            {
                "frame_index": 3,
                "label": "residual_b_p001",
                "S_NAPL_color_B_minus_A": -0.01,
                "abs_endpoint_sensitivity": 0.01,
            },
        ],
    )
    policy.write_text(
        json.dumps({"primary": {"napl_label": "full_a_p001"}}),
        encoding="utf-8",
    )

    summary = run_endpoint_consistency(
        manifest=manifest,
        branch_c_dir=branch_c_dir,
        out_dir=out_dir,
        endpoint_policy=policy,
        full_pass_threshold=0.9,
        residual_max_threshold=0.35,
    )

    assert summary["status"] == "review"
    assert summary["full_napl_below_threshold_count"] == 1
    flags = list(csv.DictReader((out_dir / "endpoint_consistency_flags.csv").open()))
    assert [row["label"] for row in flags] == ["full_a_p002"]
    assert flags[0]["endpoint_consistency_reason"] == "full_napl_below_threshold"

    source_summary = list(
        csv.DictReader((out_dir / "endpoint_consistency_source_summary.csv").open())
    )
    full_source = next(row for row in source_summary if row["source_stem"] == "full_a")
    assert full_source["row_count"] == "2"
    assert full_source["flag_count"] == "1"
    assert full_source["policy_napl_endpoint_count"] == "1"
