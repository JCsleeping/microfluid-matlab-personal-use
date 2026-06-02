from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BRANCH_C_CSV_NAMES = (
    "S_NAPL_color_primary_A.csv",
    "S_NAPL_color_sensitivity_B.csv",
    "S_NAPL_color_A_B_sensitivity_comparison.csv",
    "S_NAPL_color_xbins_primary_A.csv",
    "S_NAPL_color_xbins_sensitivity_B.csv",
    "S_NAPL_color_xzones_primary_A.csv",
    "S_NAPL_color_xzones_sensitivity_B.csv",
    "S_NAPL_color_xzone_A_B_sensitivity_comparison.csv",
)

SEGMENTATION_CSV_NAMES = (
    "red_mask_timeseries.csv",
    "red_blob_summary_timeseries.csv",
)


@dataclass(frozen=True)
class TimelineEntry:
    label: str
    frame_index: int
    real_time_s: float
    interval_s: float
    source_path: str
    tif_file: str
    page_in_tif: int
    timeseries_order: int
    role: str
    time_source: str
    gap_before_file_s: float


def parse_interval_from_name(path_value: str | Path) -> tuple[float | None, str]:
    stem = Path(path_value).stem
    patterns = (
        r"(\d+(?:\.\d+)?)\s*seconds?",
        r"(?:(?<=^)|(?<=\s)|(?<=_))(\d+(?:\.\d+)?)\s*[sS](?=[_\s.]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, stem, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if math.isfinite(value) and value > 0:
                return normalize_interval_seconds(value), "filename"
    return None, ""


def normalize_interval_seconds(value: float) -> float:
    rounded = round(value)
    if abs(value - rounded) < 0.25:
        return float(rounded)
    return float(value)


def load_csv_rows(path_value: Path) -> list[dict[str, str]]:
    with path_value.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_dict_rows(path_value: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    with path_value.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def truthy_csv(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def int_or_none(value: str | int | None) -> int | None:
    try:
        out = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return out


def timeline_source_rows(manifest_rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in manifest_rows if truthy_csv(row.get("include_in_timeseries", ""))]
    if not selected:
        selected = [row for row in manifest_rows if row.get("timeseries_order", "").strip()]
    selected.sort(
        key=lambda row: (
            int_or_none(row.get("timeseries_order")) or int_or_none(row.get("frame_order")) or 10**12,
            int_or_none(row.get("frame_order")) or 10**12,
        )
    )
    return selected


def infer_file_intervals(file_records: list[dict[str, object]]) -> None:
    known = [
        index
        for index, record in enumerate(file_records)
        if isinstance(record.get("interval_s"), float)
    ]
    for index, record in enumerate(file_records):
        if isinstance(record.get("interval_s"), float):
            continue
        previous_values = [
            float(file_records[pos]["interval_s"])
            for pos in known
            if pos < index and isinstance(file_records[pos].get("interval_s"), float)
        ]
        next_values = [
            float(file_records[pos]["interval_s"])
            for pos in known
            if pos > index and isinstance(file_records[pos].get("interval_s"), float)
        ]
        if previous_values and next_values and abs(previous_values[-1] - next_values[0]) < 1e-9:
            record["interval_s"] = previous_values[-1]
            record["interval_source"] = "neighbor_consensus"
        elif previous_values:
            record["interval_s"] = previous_values[-1]
            record["interval_source"] = "prev_neighbor_dt"
        elif next_values:
            record["interval_s"] = next_values[0]
            record["interval_source"] = "next_neighbor_dt"
        else:
            record["interval_s"] = 1.0
            record["interval_source"] = "default_1s"


def manifest_file_records(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    by_path: dict[str, dict[str, object]] = {}
    for row in rows:
        path_text = row.get("source_path", "")
        if not path_text:
            raise ValueError(f"Manifest row lacks source_path for label {row.get('label', '')!r}.")
        page = int_or_none(row.get("source_page"))
        if page is None or page < 1:
            raise ValueError(f"Manifest row has bad source_page for label {row.get('label', '')!r}.")
        if path_text not in by_path:
            interval_s, interval_source = parse_interval_from_name(path_text)
            record: dict[str, object] = {
                "source_path": path_text,
                "tif_file": Path(path_text).name,
                "max_source_page": page,
                "interval_s": interval_s,
                "interval_source": interval_source,
                "mtime": file_mtime(path_text),
                "start_s": 0.0,
                "gap_before_file_s": 0.0,
            }
            records.append(record)
            by_path[path_text] = record
        else:
            record = by_path[path_text]
            record["max_source_page"] = max(int(record["max_source_page"]), page)
    infer_file_intervals(records)
    return records


def file_mtime(path_text: str) -> float | None:
    try:
        return Path(path_text).stat().st_mtime
    except OSError:
        return None


def add_file_start_times(records: list[dict[str, object]], gap_policy: str) -> None:
    offset = 0.0
    for index, record in enumerate(records):
        gap = 0.0
        if index > 0 and gap_policy == "mtime":
            previous = records[index - 1]
            prev_mtime = previous.get("mtime")
            curr_mtime = record.get("mtime")
            if isinstance(prev_mtime, float) and isinstance(curr_mtime, float):
                recording_dur_next = int(record["max_source_page"]) * float(record["interval_s"])
                gap_candidate = float(curr_mtime) - recording_dur_next - float(prev_mtime)
                threshold = 1.5 * float(record["interval_s"])
                if gap_candidate > threshold:
                    gap = gap_candidate
                    offset += gap
        record["gap_before_file_s"] = gap
        record["start_s"] = offset
        offset += int(record["max_source_page"]) * float(record["interval_s"])


def build_timeline(manifest_csv: Path, gap_policy: str = "mtime") -> list[TimelineEntry]:
    manifest_rows = load_csv_rows(manifest_csv)
    rows = timeline_source_rows(manifest_rows)
    if not rows:
        raise ValueError(f"No timeseries rows found in manifest: {manifest_csv}")
    records = manifest_file_records(rows)
    add_file_start_times(records, gap_policy)
    by_path = {str(record["source_path"]): record for record in records}

    entries: list[TimelineEntry] = []
    for frame_index, row in enumerate(rows, start=1):
        source_path = row["source_path"]
        record = by_path[source_path]
        page = int_or_none(row.get("source_page"))
        order = int_or_none(row.get("timeseries_order"))
        if page is None or order is None:
            raise ValueError(f"Bad manifest timing row for label {row.get('label', '')!r}.")
        interval_s = float(record["interval_s"])
        real_time_s = float(record["start_s"]) + (page - 1) * interval_s
        entries.append(
            TimelineEntry(
                label=row.get("label", ""),
                frame_index=frame_index,
                real_time_s=real_time_s,
                interval_s=interval_s,
                source_path=source_path,
                tif_file=str(record["tif_file"]),
                page_in_tif=page,
                timeseries_order=order,
                role=row.get("role", ""),
                time_source=str(record["interval_source"]),
                gap_before_file_s=float(record["gap_before_file_s"]),
            )
        )
    return entries


def timeline_rows(entries: list[TimelineEntry]) -> list[dict[str, object]]:
    return [
        {
            "FrameIndex": entry.frame_index,
            "Label": entry.label,
            "Role": entry.role,
            "RealTime_s": format_float(entry.real_time_s),
            "Time_min": format_float(entry.real_time_s / 60.0),
            "Interval_s": format_float(entry.interval_s),
            "TifFile": entry.tif_file,
            "TifPath": entry.source_path,
            "PageInTif": entry.page_in_tif,
            "TimeseriesOrder": entry.timeseries_order,
            "TimeSource": entry.time_source,
            "GapBeforeFile_s": format_float(entry.gap_before_file_s),
        }
        for entry in entries
    ]


def format_float(value: float) -> str:
    if not math.isfinite(value):
        return "NaN"
    return f"{value:.12g}"


def discover_csv_inputs(branch_c_dir: Path | None, segmentation_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if branch_c_dir is not None:
        paths.extend(branch_c_dir / name for name in BRANCH_C_CSV_NAMES if (branch_c_dir / name).is_file())
    if segmentation_dir is not None:
        paths.extend(segmentation_dir / name for name in SEGMENTATION_CSV_NAMES if (segmentation_dir / name).is_file())
    return paths


def output_path_for(input_path: Path, out_dir: Path | None, suffix: str) -> Path:
    target_dir = out_dir if out_dir is not None else input_path.parent
    return target_dir / f"{input_path.stem}{suffix}{input_path.suffix}"


def join_csv_with_timeline(
    input_path: Path,
    output_path: Path,
    by_label: dict[str, TimelineEntry],
) -> dict[str, object]:
    rows = load_csv_rows(input_path)
    if not rows:
        raise ValueError(f"CSV has no rows: {input_path}")
    original_fields = list(rows[0].keys())
    added_fields = [
        "RealTime_s",
        "Time_min",
        "Interval_s",
        "TifFile",
        "PageInTif",
        "TimelineSource",
        "TimelineStatus",
    ]
    fieldnames = original_fields + [field for field in added_fields if field not in original_fields]

    matched = 0
    output_rows: list[dict[str, object]] = []
    for row in rows:
        out: dict[str, object] = dict(row)
        entry = by_label.get(row.get("label", ""))
        if entry is None:
            set_join_fields(out, None)
        else:
            matched += 1
            set_join_fields(out, entry)
        output_rows.append(out)
    write_dict_rows(output_path, output_rows, fieldnames)
    return {
        "input_csv": str(input_path),
        "output_csv": str(output_path),
        "rows": len(rows),
        "matched_rows": matched,
        "unmatched_rows": len(rows) - matched,
    }


def set_join_fields(row: dict[str, object], entry: TimelineEntry | None) -> None:
    if entry is None:
        values: dict[str, object] = {
            "RealTime_s": "NaN",
            "Time_min": "NaN",
            "Interval_s": "NaN",
            "TifFile": "",
            "PageInTif": "",
            "TimelineSource": "",
            "TimelineStatus": "unmatched_label",
        }
    else:
        values = {
            "RealTime_s": format_float(entry.real_time_s),
            "Time_min": format_float(entry.real_time_s / 60.0),
            "Interval_s": format_float(entry.interval_s),
            "TifFile": entry.tif_file,
            "PageInTif": entry.page_in_tif,
            "TimelineSource": entry.time_source,
            "TimelineStatus": "matched_label",
        }
    row.update(values)


def write_summary(path_value: Path, summary: dict[str, object]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def gap_file_summary(entries: list[TimelineEntry]) -> dict[str, object]:
    gap_by_path: dict[str, float] = {}
    for entry in entries:
        if entry.gap_before_file_s > 0 and entry.source_path not in gap_by_path:
            gap_by_path[entry.source_path] = entry.gap_before_file_s
    return {
        "gap_file_count": len(gap_by_path),
        "total_gap_s": sum(gap_by_path.values()),
        "gap_files": [
            {"source_path": path_value, "gap_before_file_s": gap_s}
            for path_value, gap_s in gap_by_path.items()
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Join physical RealTime_s from accepted_frames.csv into Branch C/C2 CSV outputs. "
            "Original CSVs are not modified."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--csv", action="append", default=[], type=Path, help="CSV to patch; can be repeated.")
    parser.add_argument("--branch-c-dir", type=Path, default=None)
    parser.add_argument("--segmentation-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--suffix", default="_realtime")
    parser.add_argument("--gap-policy", choices=["mtime", "none"], default="mtime")
    parser.add_argument("--timeline-name", default="frame_timeline_manifest.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    entries = build_timeline(args.manifest, gap_policy=args.gap_policy)
    by_label = {entry.label: entry for entry in entries}
    timeline_path = (out_dir or args.manifest.parent) / args.timeline_name
    write_dict_rows(
        timeline_path,
        timeline_rows(entries),
        [
            "FrameIndex",
            "Label",
            "Role",
            "RealTime_s",
            "Time_min",
            "Interval_s",
            "TifFile",
            "TifPath",
            "PageInTif",
            "TimeseriesOrder",
            "TimeSource",
            "GapBeforeFile_s",
        ],
    )

    csv_inputs = list(args.csv) + discover_csv_inputs(args.branch_c_dir, args.segmentation_dir)
    seen: set[Path] = set()
    unique_inputs = []
    for path_value in csv_inputs:
        resolved = path_value.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_inputs.append(path_value)

    joined = [
        join_csv_with_timeline(
            input_path=path_value,
            output_path=output_path_for(path_value, out_dir, args.suffix),
            by_label=by_label,
        )
        for path_value in unique_inputs
    ]
    gaps = gap_file_summary(entries)
    summary = {
        "status": "pass" if all(item["unmatched_rows"] == 0 for item in joined) else "review",
        "manifest_csv": str(args.manifest),
        "timeline_csv": str(timeline_path),
        "timeline_rows": len(entries),
        "gap_policy": args.gap_policy,
        "gap_count": gaps["gap_file_count"],
        "total_gap_s": gaps["total_gap_s"],
        "gap_files": gaps["gap_files"],
        "last_real_time_s": entries[-1].real_time_s if entries else None,
        "joined_files": joined,
    }
    summary_path = (out_dir or args.manifest.parent) / "timeline_join_summary.json"
    write_summary(summary_path, summary)
    print(f"TIMELINE_CSV {timeline_path}")
    print(f"TIMELINE_JOIN_SUMMARY {summary_path}")


if __name__ == "__main__":
    main()
