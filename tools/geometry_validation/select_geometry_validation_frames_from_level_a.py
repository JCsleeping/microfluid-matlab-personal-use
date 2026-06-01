"""Select validation frames from Level A outputs.

This utility only reads Level A CSVs and a recovered frame timeline, then writes
a selected-frame CSV. It does not run segmentation or geometry extraction.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import OrderedDict

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--timeline-csv", required=True)
    parser.add_argument("--rate5-dir", default="")
    parser.add_argument("--rate20-dir", default="")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--n-frames", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = args.postprocess_dir
    rates = read_frame_csv(os.path.join(base, "dissolution_rates.csv"))
    pop = read_frame_csv(os.path.join(base, "blob_population_morphology_by_frame.csv"))
    arch = read_frame_csv(os.path.join(base, "architecture_vs_time.csv"))
    timeline = read_frame_csv(args.timeline_csv)

    merged = rates[
        [
            "FrameIndex",
            "Sn",
            "SnMonotone",
            "NumBlobs",
            "InterfaceArea",
            "DissolutionRate_Sn_per_min",
        ]
    ].rename(columns={"DissolutionRate_Sn_per_min": "Rate_10min"})
    merged = merged.merge(
        pop[
            [
                "FrameIndex",
                "BlobCount",
                "Area_median",
                "EquivRadius_median",
                "Amax_Atotal",
            ]
        ],
        on="FrameIndex",
        how="left",
    )
    merged = merged.merge(
        arch[["FrameIndex", "ArchitectureType"]], on="FrameIndex", how="left"
    )
    merged = merged.merge(
        timeline[["FrameIndex", "RealTime_s", "TifFile", "PageInTif"]],
        on="FrameIndex",
        how="left",
    )

    if args.rate5_dir:
        rate5 = read_frame_csv(os.path.join(args.rate5_dir, "dissolution_rates.csv"))
        merged = merged.merge(
            rate5[["FrameIndex", "DissolutionRate_Sn_per_min"]].rename(
                columns={"DissolutionRate_Sn_per_min": "Rate_5min"}
            ),
            on="FrameIndex",
            how="left",
        )
    else:
        merged["Rate_5min"] = np.nan
    if args.rate20_dir:
        rate20 = read_frame_csv(os.path.join(args.rate20_dir, "dissolution_rates.csv"))
        merged = merged.merge(
            rate20[["FrameIndex", "DissolutionRate_Sn_per_min"]].rename(
                columns={"DissolutionRate_Sn_per_min": "Rate_20min"}
            ),
            on="FrameIndex",
            how="left",
        )
    else:
        merged["Rate_20min"] = np.nan

    by_frame = {int(row.FrameIndex): row for row in merged.itertuples(index=False)}
    candidates: dict[int, dict[str, object]] = {}

    def add(frame: int | float, reason: str, priority: int, source: str, note: str = "") -> None:
        if not np.isfinite(frame):
            return
        frame_i = int(round(float(frame)))
        if frame_i < 1 or frame_i > len(merged):
            return
        entry = candidates.setdefault(
            frame_i,
            {"reasons": [], "priority": int(priority), "sources": [], "notes": []},
        )
        entry["reasons"].append(reason)
        entry["priority"] = min(int(entry["priority"]), int(priority))
        entry["sources"].append(source)
        if note:
            entry["notes"].append(note)

    def add_neighbors(frame: int, offsets: list[int], reason: str, priority: int, source: str) -> None:
        for offset in offsets:
            suffix = "" if offset == 0 else f"_neighbor{offset:+d}"
            add(frame + offset, reason + suffix, priority + (1 if offset else 0), source)

    add(1, "initial_frame", 1, "frame_timeline")
    add(len(merged), "final_frame_near_depleted", 1, "frame_timeline")

    for target in [0.25, 0.20, 0.15, 0.10, 0.05, 0.02, 0.01, 0.005, 0.001]:
        idx = (rates["SnMonotone"] - target).abs().idxmin()
        frame = int(rates.loc[idx, "FrameIndex"])
        delta = abs(float(rates.loc[idx, "SnMonotone"]) - target)
        add(
            frame,
            f"snmonotone_target_{target:g}",
            9,
            "dissolution_rates",
            f"nearest_abs_delta={delta:.6g}",
        )

    rate_peaks: list[int] = []
    for frame in rates.sort_values("DissolutionRate_Sn_per_min", ascending=False)[
        "FrameIndex"
    ].astype(int):
        if all(abs(int(frame) - other) >= 120 for other in rate_peaks):
            rate_peaks.append(int(frame))
        if len(rate_peaks) >= 5:
            break
    for frame in rate_peaks:
        add_neighbors(frame, [-2, 0, 2], "rate_10min_peak", 10, "dissolution_rates")

    for col, reason in [("NumBlobs", "numblobs_peak"), ("InterfaceArea", "interfacearea_peak")]:
        frame = int(rates.loc[rates[col].idxmax(), "FrameIndex"])
        add_neighbors(frame, [-3, 0, 3], reason, 12, "dissolution_rates")

    late = pop[pop["FrameIndex"] >= int(len(pop) * 0.95)].copy()
    late = late.sort_values(["Area_median", "EquivRadius_median", "FrameIndex"]).head(5)
    for frame in late["FrameIndex"].astype(int):
        add(frame, "late_stage_tiny_blob_candidate", 16, "blob_population_morphology_by_frame")

    if merged["Rate_5min"].notna().any() and merged["Rate_20min"].notna().any():
        sens = merged.copy()
        sens["rate_window_disagreement"] = (sens["Rate_5min"] - sens["Rate_20min"]).abs()
        for frame in sens.sort_values("rate_window_disagreement", ascending=False)[
            "FrameIndex"
        ].head(4).astype(int):
            add(frame, "rate_window_sensitivity_disagreement", 18, "dissolution_rates_5_10_20")

    for frame, prev_label, new_label, prev_len, new_len in persistent_transitions(arch):
        add(
            frame - 1,
            "persistent_architecture_transition_before",
            24,
            "architecture_vs_time",
            f"{prev_label}->{new_label};prev_len={prev_len};new_len={new_len}",
        )
        add(
            frame,
            "persistent_architecture_transition_after",
            24,
            "architecture_vs_time",
            f"{prev_label}->{new_label};prev_len={prev_len};new_len={new_len}",
        )

    transition_frames = timeline.loc[
        timeline["PageInTif"].eq(1) & timeline["FrameIndex"].gt(1), "FrameIndex"
    ].astype(int)
    for frame in spaced_values(transition_frames.tolist(), 4):
        add(frame - 1, "tif_page_transition_before", 14, "frame_timeline")
        add(frame, "tif_page_transition_after", 14, "frame_timeline")

    for frame in spaced_values(chunk_boundary_frames(args.output_root), 3):
        add(frame, "chunk_boundary_end", 22, "blob_detail_chunks")
        add(frame + 1, "chunk_boundary_start_next", 22, "blob_detail_chunks")

    if len(candidates) < args.n_frames:
        for frame in np.linspace(1, len(merged), args.n_frames * 2).round().astype(int):
            add(frame, "uniform_time_fill", 40, "dissolution_rates")
            if len(candidates) >= args.n_frames:
                break

    ranked = sorted(candidates.items(), key=lambda item: (item[1]["priority"], item[0]))
    selected_frames = sorted(frame for frame, _ in ranked[: args.n_frames])
    rows = []
    for frame in selected_frames:
        row = by_frame[frame]
        meta = candidates[frame]
        rows.append(
            {
                "FrameIndex": frame,
                "RealTime_s": getattr(row, "RealTime_s"),
                "SnMonotone": getattr(row, "SnMonotone"),
                "NumBlobs": int(getattr(row, "NumBlobs")),
                "InterfaceArea": getattr(row, "InterfaceArea"),
                "Rate_10min": getattr(row, "Rate_10min"),
                "ArchitectureClass": getattr(row, "ArchitectureType"),
                "TifFile": getattr(row, "TifFile"),
                "PageInTif": int(getattr(row, "PageInTif")),
                "SelectionReason": ";".join(unique_in_order(meta["reasons"])),
                "Priority": int(meta["priority"]),
                "SourceTable": ";".join(unique_in_order(meta["sources"])),
                "Notes": ";".join(unique_in_order(meta["notes"])),
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(args.output_csv, index=False, encoding="utf-8-sig")
    print(args.output_csv)
    print(out[["FrameIndex", "RealTime_s", "SnMonotone", "NumBlobs", "InterfaceArea", "Rate_10min", "ArchitectureClass", "PageInTif", "SelectionReason", "Priority"]].to_string(index=False))
    print(f"n={len(out)} unique={out['FrameIndex'].nunique()}")


def read_frame_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "FrameIndex" in df.columns:
        df["FrameIndex"] = df["FrameIndex"].astype(int)
    return df


def unique_in_order(values: list[str]) -> list[str]:
    return list(OrderedDict((str(value), None) for value in values).keys())


def spaced_values(values: list[int], n: int) -> list[int]:
    if not values:
        return []
    indices = np.linspace(0, len(values) - 1, min(n, len(values))).round().astype(int)
    return [int(values[int(index)]) for index in indices]


def persistent_transitions(arch: pd.DataFrame, min_len: int = 5, max_events: int = 3) -> list[tuple[int, str, str, int, int]]:
    vals = arch["ArchitectureType"].astype(str).to_numpy()
    frames = arch["FrameIndex"].astype(int).to_numpy()
    segments: list[tuple[int, int, str, int]] = []
    start = 0
    for idx in range(1, len(vals) + 1):
        if idx == len(vals) or vals[idx] != vals[start]:
            segments.append((int(frames[start]), int(frames[idx - 1]), vals[start], idx - start))
            start = idx
    transitions = []
    for idx in range(1, len(segments)):
        prev = segments[idx - 1]
        cur = segments[idx]
        if prev[3] >= min_len and cur[3] >= min_len:
            transitions.append((cur[0], prev[2], cur[2], prev[3], cur[3]))
    if not transitions:
        return []
    selected = spaced_values(list(range(len(transitions))), max_events)
    return [transitions[idx] for idx in selected]


def chunk_boundary_frames(output_root: str) -> list[int]:
    chunk_dir = os.path.join(output_root, "blob_detail_chunks")
    if not os.path.isdir(chunk_dir):
        return []
    frames = []
    for name in os.listdir(chunk_dir):
        match = re.match(r"blob_detail_(\d+)_(\d+)\.mat$", name)
        if match:
            frames.append(int(match.group(2)))
    frames = sorted(frame for frame in frames if frame > 0)
    return frames[:-1]


if __name__ == "__main__":
    main()
