from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


def load_timeline_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "timeline"
        / "join_branch_c_realtime.py"
    )
    spec = importlib.util.spec_from_file_location("join_branch_c_realtime", script)
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


def test_build_timeline_uses_filename_interval_and_source_page(tmp_path: Path):
    timeline = load_timeline_module()
    raw = tmp_path / "raw"
    first = raw / "00 WATER 3 SECONDS.tif"
    second = raw / "01 WATER 1 SECONDS.tif"
    first.parent.mkdir()
    first.write_bytes(b"")
    second.write_bytes(b"")
    manifest = tmp_path / "accepted_frames.csv"
    write_csv(
        manifest,
        [
            {
                "label": "full_a_p001",
                "role": "full_napl",
                "frame_order": 1,
                "timeseries_order": 1,
                "source_path": first,
                "source_page": 1,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 1,
            },
            {
                "label": "full_a_p003",
                "role": "full_napl",
                "frame_order": 2,
                "timeseries_order": 2,
                "source_path": first,
                "source_page": 3,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 0,
            },
            {
                "label": "res_b_p002",
                "role": "residual",
                "frame_order": 3,
                "timeseries_order": 3,
                "source_path": second,
                "source_page": 2,
                "time_s": "",
                "include_in_timeseries": 1,
                "fit_sample": 0,
            },
        ],
    )

    entries = timeline.build_timeline(manifest, gap_policy="none")

    assert [entry.real_time_s for entry in entries] == [0.0, 6.0, 10.0]
    assert [entry.interval_s for entry in entries] == [3.0, 3.0, 1.0]
    assert entries[-1].tif_file == "01 WATER 1 SECONDS.tif"


def test_join_csv_repeats_timeline_for_xbin_rows(tmp_path: Path):
    timeline = load_timeline_module()
    entry = timeline.TimelineEntry(
        label="frame_a",
        frame_index=1,
        real_time_s=9.0,
        interval_s=3.0,
        source_path=str(tmp_path / "00 WATER 3 SECONDS.tif"),
        tif_file="00 WATER 3 SECONDS.tif",
        page_in_tif=4,
        timeseries_order=1,
        role="full_napl",
        time_source="filename",
        gap_before_file_s=0.0,
    )
    source = tmp_path / "xbins.csv"
    output = tmp_path / "xbins_realtime.csv"
    write_csv(
        source,
        [
            {"frame_index": 1, "label": "frame_a", "x_bin": 1, "S_NAPL_color_xbin": 0.1},
            {"frame_index": 1, "label": "frame_a", "x_bin": 2, "S_NAPL_color_xbin": 0.2},
        ],
    )

    summary = timeline.join_csv_with_timeline(source, output, {"frame_a": entry})
    rows = read_csv(output)

    assert summary["matched_rows"] == 2
    assert rows[0]["RealTime_s"] == "9"
    assert rows[1]["Time_min"] == "0.15"
    assert rows[0]["PageInTif"] == "4"
    assert rows[0]["TimelineStatus"] == "matched_label"
