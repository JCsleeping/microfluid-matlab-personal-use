from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent
DEFAULT_CONFIG = REPO / "configs" / "a1_1bo_6ul_branch_c_timeseries.json"
DEFAULT_STEPS = ("manifest", "cache", "matlab", "segpilot", "segmorph", "validate")
STEPS = DEFAULT_STEPS + ("timeline", "residual", "analysis")
SEGMORPH_INTERFACE_COLUMNS = (
    "dnapl_water_length_px",
    "dnapl_solid_length_px",
    "dnapl_water_length_m",
    "dnapl_solid_length_m",
    "InterfaceArea",
    "solid_contact_fraction",
    "a_i_2D_proxy",
    "interface_semantics",
)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def read_json(path_value: Path) -> dict[str, Any]:
    return json.loads(path_value.read_text(encoding="utf-8"))


def resolve_path(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return path_obj
    return REPO / path_obj


def matlab_quote(path_value: Path) -> str:
    return str(path_value).replace("'", "''")


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def parse_steps(raw_steps: list[str] | None) -> list[str]:
    if raw_steps is None:
        return list(DEFAULT_STEPS)
    parsed: list[str] = []
    for item in raw_steps:
        for step in item.split(","):
            step = step.strip().lower()
            if not step:
                continue
            if step not in STEPS:
                raise ValueError(f"Unsupported step {step!r}; choose from {STEPS}.")
            if step not in parsed:
                parsed.append(step)
    if not parsed:
        raise ValueError("At least one step must be selected.")
    return parsed


def load_effective_config(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(args.config)
    modes = config.pop("modes", {})
    if args.mode not in modes:
        raise ValueError(f"Mode {args.mode!r} is not defined in {args.config}.")
    config = deep_merge(config, modes[args.mode])

    if args.run_name:
        config["run_name"] = args.run_name
    if args.roi_mask:
        config["roi_mask"] = args.roi_mask
    if args.output_root:
        config["output_root"] = args.output_root
    if args.matlab_command:
        config["matlab_command"] = args.matlab_command
    if args.analysis_run_label:
        config.setdefault("analysis_package", {})["run_label"] = args.analysis_run_label
    if args.physical_metadata:
        config["physical_metadata_path"] = args.physical_metadata
    if args.resume_cache is not None:
        config.setdefault("cache", {})["resume"] = args.resume_cache

    config["mode"] = args.mode
    config["steps"] = parse_steps(args.steps)
    config["force"] = bool(args.force)
    config["force_manifest"] = bool(args.force or args.force_manifest)
    config["force_cache"] = bool(args.force or args.force_cache)
    config["allow_lzf"] = bool(args.allow_lzf)
    return config


def build_paths(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Path]:
    run_name = str(config["run_name"])
    run_suffix = str(config.get("run_suffix", config["mode"]))
    run_id = f"{run_name}_{run_suffix}" if run_suffix else run_name
    output_root = resolve_path(config["output_root"])
    assert output_root is not None

    manifest_dir = resolve_path(args.manifest_dir) or output_root / "manifests" / run_id
    cache_dir = resolve_path(args.cache_dir) or output_root / "basicpy_hdf5_cache" / run_id
    matlab_dir = resolve_path(args.matlab_dir) or output_root / "branch_c_timeseries" / run_id
    segmentation_pilot_dir = (
        resolve_path(args.segmentation_pilot_dir)
        or output_root / "segmentation_pilot" / run_id
    )
    segmentation_morphology_dir = (
        resolve_path(args.segmentation_morphology_dir)
        or output_root / "segmentation_morphology" / run_id
    )
    timeline_dir = (
        resolve_path(args.timeline_dir)
        or output_root / "timeline_postprocess" / run_id
    )
    residual_dir = (
        resolve_path(args.residual_dir)
        or output_root / "residual_trapping_postprocess" / run_id
    )
    analysis_dir = (
        resolve_path(args.analysis_dir)
        or output_root / f"analysis_package_{run_suffix or run_name}"
    )
    run_config_dir = output_root / "run_configs"
    return {
        "output_root": output_root,
        "manifest_dir": manifest_dir,
        "cache_dir": cache_dir,
        "matlab_dir": matlab_dir,
        "segmentation_pilot_dir": segmentation_pilot_dir,
        "segmentation_morphology_dir": segmentation_morphology_dir,
        "timeline_dir": timeline_dir,
        "residual_dir": residual_dir,
        "analysis_dir": analysis_dir,
        "run_config_dir": run_config_dir,
    }


def effective_config_path_for(config: dict[str, Any], paths: dict[str, Path]) -> Path:
    run_id = f'{config["run_name"]}_{config.get("run_suffix", config["mode"])}'
    return paths["run_config_dir"] / f"{run_id}_effective.json"


def run_id_for(config: dict[str, Any]) -> str:
    run_suffix = str(config.get("run_suffix", config["mode"]))
    return f'{config["run_name"]}_{run_suffix}' if run_suffix else str(config["run_name"])


def write_effective_config(config: dict[str, Any], paths: dict[str, Path]) -> Path:
    paths["run_config_dir"].mkdir(parents=True, exist_ok=True)
    config_path = effective_config_path_for(config, paths)
    serializable = deepcopy(config)
    serializable["resolved_paths"] = {key: str(value) for key, value in paths.items()}
    config_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    return config_path


def write_endpoint_policy_input(config: dict[str, Any], manifest_dir: Path) -> Path | None:
    endpoint_policy = config.get("endpoint_policy")
    if not endpoint_policy:
        return None
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path_value = manifest_dir / "endpoint_policy_input.json"
    path_value.write_text(json.dumps(endpoint_policy, indent=2), encoding="utf-8")
    return path_value


def write_water_endpoints_input(config: dict[str, Any], manifest_dir: Path) -> Path | None:
    endpoints = config.get("water_endpoints")
    if not endpoints:
        return None
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path_value = manifest_dir / "water_endpoints_input.json"
    path_value.write_text(json.dumps(endpoints, indent=2), encoding="utf-8")
    return path_value


def write_physical_metadata_input(config: dict[str, Any], paths: dict[str, Path]) -> Path | None:
    if config.get("physical_metadata_path"):
        return resolve_path(config["physical_metadata_path"])
    recovery_config = config.get("physical_metadata_recovery") or {}
    recovery_path_value = config.get("physical_metadata_recovery_path") or recovery_config.get("path")
    if recovery_path_value:
        from tools.analysis_package.physical_metadata_manifest import (
            build_physical_metadata_manifest,
            load_recovered_metadata,
        )

        recovery_path = resolve_path(recovery_path_value)
        assert recovery_path is not None
        metadata = build_physical_metadata_manifest(
            load_recovered_metadata(recovery_path),
            processing_scale_factor=recovery_config.get("processing_scale_factor"),
            trusted=recovery_config.get("trusted"),
            metadata_status=recovery_config.get("metadata_status"),
            source_path=recovery_path,
        )
        paths["run_config_dir"].mkdir(parents=True, exist_ok=True)
        path_value = paths["run_config_dir"] / f"{run_id_for(config)}_physical_metadata.json"
        path_value.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return path_value
    metadata = config.get("physical_metadata")
    if not metadata:
        return None
    paths["run_config_dir"].mkdir(parents=True, exist_ok=True)
    path_value = paths["run_config_dir"] / f"{run_id_for(config)}_physical_metadata.json"
    path_value.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path_value


def manifest_command(
    config: dict[str, Any],
    paths: dict[str, Path],
    endpoint_policy_input: Path | None,
    water_endpoints_input: Path | None,
) -> list[str]:
    manifest_config = config.get("manifest", {})
    command = [
        sys.executable,
        str(REPO / "run_a1_1bo_6ul_make_full_frames_manifest.py"),
        "--water-endpoint-dir",
        str(resolve_path(config["water_endpoint_dir"])),
        "--production-dir",
        str(resolve_path(config["production_dir"])),
        "--out-dir",
        str(paths["manifest_dir"]),
        "--page-selection",
        str(manifest_config.get("page_selection", "first")),
        "--fit-sample-stride",
        str(manifest_config.get("fit_sample_stride", 1)),
    ]
    if manifest_config.get("expand_pages", False):
        command.append("--expand-pages")
    if manifest_config.get("max_pages") is not None:
        command.extend(["--max-pages", str(manifest_config["max_pages"])])
    if manifest_config.get("time_step_s") is not None:
        command.extend(["--time-step-s", str(manifest_config["time_step_s"])])
        command.extend(["--time-start-s", str(manifest_config.get("time_start_s", 0.0))])
    if endpoint_policy_input is not None:
        command.extend(["--endpoint-policy", str(endpoint_policy_input)])
    if water_endpoints_input is not None:
        command.extend(["--water-endpoints", str(water_endpoints_input)])
    if config.get("force_manifest", False):
        command.append("--force")
    return command


def cache_command(config: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    cache_config = config.get("cache", {})
    command = [
        sys.executable,
        str(REPO / "run_a1_1bo_6ul_build_basicpy_hdf5_cache.py"),
        "--out",
        str(paths["cache_dir"]),
        "--manifest",
        str(paths["manifest_dir"] / "accepted_frames.csv"),
        "--mask",
        str(resolve_path(config["roi_mask"])),
        "--compression",
        str(cache_config.get("compression", "none")),
        "--batch-size",
        str(cache_config.get("batch_size", 20)),
    ]
    if cache_config.get("resume", True):
        command.append("--resume")
    if config.get("force_cache", False):
        command.append("--force")
    return command


def matlab_command(config: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    endpoint_policy_path = paths["manifest_dir"] / "endpoint_policy.json"
    display_cols = (
        "{'endpoint_short_name','matlab_full_median',"
        "'matlab_residual_median','comparison_available','bridge_pass'}"
    )
    expression = (
        f"cd('{matlab_quote(REPO)}'); "
        "outputs = run_a1_1bo_6ul_hdf5_cache_branch_c_pipeline("
        f"'{matlab_quote(paths['cache_dir'])}', "
        f"'{matlab_quote(paths['matlab_dir'])}', "
        f"'{matlab_quote(endpoint_policy_path)}'); "
        f"disp(outputs.summary(:, {display_cols}));"
    )
    return [str(config.get("matlab_command", "matlab")), "-batch", expression]


def segmentation_command(
    config: dict[str, Any],
    paths: dict[str, Path],
    effective_config_path: Path,
    run_mode: str,
) -> list[str]:
    if run_mode == "pilot":
        out_dir = paths["segmentation_pilot_dir"]
    elif run_mode == "morphology":
        out_dir = paths["segmentation_morphology_dir"]
    else:
        raise ValueError(f"Unsupported segmentation run mode: {run_mode}")
    expression = (
        f"cd('{matlab_quote(REPO)}'); "
        "outputs = run_a1_1bo_6ul_hdf5_cache_segmentation_morphology("
        f"'{matlab_quote(paths['cache_dir'])}', "
        f"'{matlab_quote(out_dir)}', "
        f"'{matlab_quote(effective_config_path)}', "
        f"'{run_mode}'); "
        "disp(outputs);"
    )
    return [str(config.get("matlab_command", "matlab")), "-batch", expression]


def timeline_command(config: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    timeline_config = config.get("timeline_postprocess", {})
    command = [
        sys.executable,
        str(REPO / "tools" / "timeline" / "join_branch_c_realtime.py"),
        "--manifest",
        str(paths["manifest_dir"] / "accepted_frames.csv"),
        "--branch-c-dir",
        str(paths["matlab_dir"]),
        "--segmentation-dir",
        str(paths["segmentation_morphology_dir"]),
        "--out-dir",
        str(paths["timeline_dir"]),
    ]
    if timeline_config.get("gap_policy") is not None:
        command.extend(["--gap-policy", str(timeline_config["gap_policy"])])
    return command


def residual_command(config: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    residual_config = config.get("residual_postprocess", {})
    command = [
        sys.executable,
        str(REPO / "tools" / "residual" / "compute_residual_trapping_metrics.py"),
        "--timeline-dir",
        str(paths["timeline_dir"]),
        "--out-dir",
        str(paths["residual_dir"]),
    ]
    if residual_config.get("full_role") is not None:
        command.extend(["--full-role", str(residual_config["full_role"])])
    if residual_config.get("residual_role") is not None:
        command.extend(["--residual-role", str(residual_config["residual_role"])])
    return command


def analysis_run_label(config: dict[str, Any]) -> str:
    analysis_config = config.get("analysis_package", {})
    if analysis_config.get("run_label"):
        return str(analysis_config["run_label"])
    run_suffix = str(config.get("run_suffix", config["mode"]))
    return f"{config['run_name']} {run_suffix} Branch C/C2"


def analysis_command(
    config: dict[str, Any],
    paths: dict[str, Path],
    physical_metadata_input: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(REPO / "tools" / "analysis_package" / "build_branch_c_analysis_package.py"),
        "--timeline-dir",
        str(paths["timeline_dir"]),
        "--residual-dir",
        str(paths["residual_dir"]),
        "--out-dir",
        str(paths["analysis_dir"]),
        "--run-label",
        analysis_run_label(config),
    ]
    if physical_metadata_input is not None:
        command.extend(["--physical-metadata", str(physical_metadata_input)])
    return command


def run_command(command: list[str], dry_run: bool, commands: list[str]) -> None:
    rendered = command_text(command)
    commands.append(rendered)
    print(rendered)
    if dry_run:
        return
    subprocess.run(command, cwd=REPO, check=True)


def read_csv_rows(path_value: Path) -> list[dict[str, str]]:
    with path_value.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def finite_float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    return lower_value + (upper_value - lower_value) * (position - lower)


def metric_summary(rows: list[dict[str, str]], column: str) -> dict[str, Any]:
    values = [
        value
        for value in (finite_float(row.get(column, "")) for row in rows)
        if value is not None
    ]
    summary: dict[str, Any] = {
        "row_count": len(rows),
        "numeric_count": len(values),
        "nan_or_missing_count": len(rows) - len(values),
    }
    if values:
        summary.update(
            {
                "min": min(values),
                "p05": percentile(values, 5),
                "median": statistics.median(values),
                "p95": percentile(values, 95),
                "max": max(values),
            }
        )
    return summary


def metric_by_role(rows: list[dict[str, str]], column: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get("role", ""), []).append(row)
    return {
        role: metric_summary(role_rows, column)
        for role, role_rows in sorted(grouped.items())
    }


def missing_columns(rows: list[dict[str, str]], columns: tuple[str, ...]) -> list[str]:
    if not rows:
        return list(columns)
    available = set(rows[0])
    return [column for column in columns if column not in available]


def segmorph_interface_quality(rows: list[dict[str, str]]) -> dict[str, Any]:
    missing = missing_columns(rows, SEGMORPH_INTERFACE_COLUMNS)
    quality: dict[str, Any] = {
        "missing_columns": missing,
        "alias_mismatch_count": 0,
        "water_length_nonpositive_with_mask_count": 0,
        "solid_length_negative_count": 0,
        "solid_contact_fraction_out_of_range_count": 0,
        "a_i_2D_proxy_bad_count": 0,
        "interface_semantics_bad_count": 0,
        "metrics": {},
    }
    if missing:
        return quality
    expected_semantics = "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area"
    for row in rows:
        red_area = finite_float(row.get("red_mask_area_px", ""))
        water = finite_float(row.get("dnapl_water_length_px", ""))
        solid = finite_float(row.get("dnapl_solid_length_px", ""))
        interface_area = finite_float(row.get("InterfaceArea", ""))
        solid_fraction = finite_float(row.get("solid_contact_fraction", ""))
        ai_proxy = finite_float(row.get("a_i_2D_proxy", ""))
        if water is not None and interface_area is not None and abs(water - interface_area) > 1e-9:
            quality["alias_mismatch_count"] += 1
        has_red_mask = red_area is not None and red_area > 0
        if has_red_mask:
            if water is None or water <= 0:
                quality["water_length_nonpositive_with_mask_count"] += 1
            if ai_proxy is None or ai_proxy < 0:
                quality["a_i_2D_proxy_bad_count"] += 1
        if solid is None or solid < 0:
            quality["solid_length_negative_count"] += 1
        if has_red_mask and (
            solid_fraction is None or solid_fraction < 0 or solid_fraction > 1
        ):
            quality["solid_contact_fraction_out_of_range_count"] += 1
        if row.get("interface_semantics", "") != expected_semantics:
            quality["interface_semantics_bad_count"] += 1
    quality["metrics"] = {
        "dnapl_water_length_px": metric_summary(rows, "dnapl_water_length_px"),
        "dnapl_solid_length_px": metric_summary(rows, "dnapl_solid_length_px"),
        "dnapl_water_length_m": metric_summary(rows, "dnapl_water_length_m"),
        "dnapl_solid_length_m": metric_summary(rows, "dnapl_solid_length_m"),
        "InterfaceArea": metric_summary(rows, "InterfaceArea"),
        "solid_contact_fraction": metric_summary(rows, "solid_contact_fraction"),
        "a_i_2D_proxy": metric_summary(rows, "a_i_2D_proxy"),
        "dnapl_water_length_px_by_role": metric_by_role(rows, "dnapl_water_length_px"),
        "solid_contact_fraction_by_role": metric_by_role(rows, "solid_contact_fraction"),
        "a_i_2D_proxy_by_role": metric_by_role(rows, "a_i_2D_proxy"),
    }
    return quality


def threshold_slug(value: float) -> str:
    return str(value).replace(".", "p").replace("-", "m")


def write_dict_csv(path_value: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path_value.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path_value.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def finite_float_or_nan(value: str) -> float:
    number = finite_float(value)
    return float("nan") if number is None else number


def weighted_mean(rows: list[dict[str, str]], column: str) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for row in rows:
        value = finite_float(row.get(column, ""))
        weight = finite_float(row.get("x_bin_count", ""))
        if value is None:
            continue
        if weight is None or weight <= 0:
            weight = 1.0
        weighted_sum += value * weight
        weight_sum += weight
    if weight_sum <= 0:
        return float("nan")
    return weighted_sum / weight_sum


def median_or_nan(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return float("nan")
    return float(statistics.median(finite))


def first_event(rows: list[dict[str, Any]], column: str, predicate: str) -> dict[str, Any]:
    for row in rows:
        value = row.get(column)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        if (predicate == "ge" and value >= 1.0) or (predicate == "le" and value <= 1.0):
            return {
                "frame_index": row.get("frame_index"),
                "time_s": row.get("time_s"),
                "label": row.get("label"),
                "role": row.get("role"),
            }
    return {"frame_index": None, "time_s": None, "label": "", "role": ""}


def build_xzone_definition(
    xbin_rows: list[dict[str, str]],
    regional_config: dict[str, Any],
) -> dict[str, Any]:
    x_bins = sorted(
        {
            int(value)
            for value in (finite_float(row.get("x_bin", "")) for row in xbin_rows)
            if value is not None
        }
    )
    if not x_bins:
        raise ValueError("x-bin output has no finite x_bin values.")
    n_bins = max(x_bins)
    terminal_fraction = float(regional_config.get("terminal_zone_fraction", 0.1))
    terminal_count = max(1, int(round(n_bins * terminal_fraction)))
    if terminal_count * 2 >= n_bins:
        terminal_count = max(1, (n_bins - 1) // 2)
    low_bins = list(range(1, terminal_count + 1))
    high_bins = list(range(n_bins - terminal_count + 1, n_bins + 1))
    flow_direction = str(regional_config.get("flow_direction", "left_to_right")).lower()
    if flow_direction == "right_to_left":
        inlet_bins = high_bins
        outlet_bins = low_bins
    elif flow_direction == "left_to_right":
        inlet_bins = low_bins
        outlet_bins = high_bins
    else:
        raise ValueError(
            "regional_metrics.flow_direction must be left_to_right or right_to_left."
        )
    terminal_bins = sorted(set(inlet_bins + outlet_bins))
    mid_bins = [x_bin for x_bin in range(1, n_bins + 1) if x_bin not in terminal_bins]
    if not mid_bins:
        raise ValueError("x-zone mid region is empty; reduce terminal_zone_fraction.")
    return {
        "n_bins": n_bins,
        "terminal_zone_fraction": terminal_fraction,
        "terminal_bin_count": terminal_count,
        "flow_direction": flow_direction,
        "inlet_bins": inlet_bins,
        "mid_bins": mid_bins,
        "outlet_bins": outlet_bins,
        "terminal_bins": terminal_bins,
        "definition": (
            "x-zone proxy: inlet/outlet terminal bins plus mid bins; "
            "not geometric pore-wall core/edge"
        ),
    }


def xbin_group_key(row: dict[str, str]) -> tuple[int, str]:
    frame = finite_float(row.get("frame_index", ""))
    return (int(frame) if frame is not None else 0, row.get("label", ""))


def rows_for_bins(
    rows: list[dict[str, str]],
    bins: list[int],
) -> list[dict[str, str]]:
    wanted = set(bins)
    return [
        row
        for row in rows
        if (finite_float(row.get("x_bin", "")) is not None)
        and int(finite_float(row.get("x_bin", "")) or 0) in wanted
    ]


def build_xzone_rows(
    xbin_rows: list[dict[str, str]],
    regional_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    definition = build_xzone_definition(xbin_rows, regional_config)
    thresholds = [
        float(value)
        for value in regional_config.get("front_thresholds", [0.2, 0.5])
    ]
    grouped: dict[tuple[int, str], list[dict[str, str]]] = {}
    for row in xbin_rows:
        grouped.setdefault(xbin_group_key(row), []).append(row)

    out_rows: list[dict[str, Any]] = []
    for _, frame_rows in sorted(grouped.items(), key=lambda item: item[0]):
        frame_rows = sorted(
            frame_rows,
            key=lambda row: int(finite_float(row.get("x_bin", "")) or 0),
        )
        first = frame_rows[0]
        frame_index = int(finite_float(first.get("frame_index", "")) or 0)
        inlet_value = weighted_mean(
            rows_for_bins(frame_rows, definition["inlet_bins"]),
            "S_NAPL_color_xbin",
        )
        mid_value = weighted_mean(
            rows_for_bins(frame_rows, definition["mid_bins"]),
            "S_NAPL_color_xbin",
        )
        outlet_value = weighted_mean(
            rows_for_bins(frame_rows, definition["outlet_bins"]),
            "S_NAPL_color_xbin",
        )
        terminal_value = weighted_mean(
            rows_for_bins(frame_rows, definition["terminal_bins"]),
            "S_NAPL_color_xbin",
        )
        out: dict[str, Any] = {
            "frame_index": frame_index,
            "time_s": finite_float_or_nan(first.get("time_s", "")),
            "label": first.get("label", ""),
            "role": first.get("role", ""),
            "endpoint_id": first.get("endpoint_id", ""),
            "endpoint_short_name": first.get("endpoint_short_name", ""),
            "water_label": first.get("water_label", ""),
            "napl_label": first.get("napl_label", ""),
            "S_x_inlet": inlet_value,
            "S_x_mid": mid_value,
            "S_x_outlet": outlet_value,
            "S_x_terminal_mean": terminal_value,
            "S_x_inlet_outlet_asymmetry": inlet_value - outlet_value,
            "S_x_mid_minus_terminal": mid_value - terminal_value,
            "xzone_n_bins": definition["n_bins"],
            "xzone_terminal_bin_count": definition["terminal_bin_count"],
            "xzone_flow_direction": definition["flow_direction"],
            "xzone_definition": definition["definition"],
        }
        values_by_bin = {
            int(finite_float(row.get("x_bin", "")) or 0): finite_float(
                row.get("S_NAPL_color_xbin", "")
            )
            for row in frame_rows
        }
        for threshold in thresholds:
            slug = threshold_slug(threshold)
            active = [
                x_bin
                for x_bin, value in values_by_bin.items()
                if value is not None and value >= threshold
            ]
            if active:
                if definition["flow_direction"] == "left_to_right":
                    extent_bin = max(active)
                    extent_fraction = extent_bin / definition["n_bins"]
                else:
                    extent_bin = min(active)
                    extent_fraction = (
                        definition["n_bins"] - extent_bin + 1
                    ) / definition["n_bins"]
            else:
                extent_bin = float("nan")
                extent_fraction = 0.0
            out[f"napl_extent_xbin_ge_{slug}"] = extent_bin
            out[f"napl_extent_fraction_ge_{slug}"] = extent_fraction
            out[f"active_bin_fraction_ge_{slug}"] = len(active) / definition["n_bins"]
            out[f"inlet_zone_ge_{slug}"] = int(
                math.isfinite(inlet_value) and inlet_value >= threshold
            )
            out[f"outlet_zone_ge_{slug}"] = int(
                math.isfinite(outlet_value) and outlet_value >= threshold
            )
            out[f"inlet_zone_le_{slug}"] = int(
                math.isfinite(inlet_value) and inlet_value <= threshold
            )
            out[f"outlet_zone_le_{slug}"] = int(
                math.isfinite(outlet_value) and outlet_value <= threshold
            )
        out_rows.append(out)
    return out_rows, definition


def summarize_xzone_rows(
    xzone_rows: list[dict[str, Any]],
    thresholds: list[float],
) -> dict[str, Any]:
    by_role: dict[str, list[dict[str, Any]]] = {}
    for row in xzone_rows:
        by_role.setdefault(str(row.get("role", "")), []).append(row)

    summary: dict[str, Any] = {
        "row_count": len(xzone_rows),
        "by_role": {},
        "events": {},
    }
    metric_columns = [
        "S_x_inlet",
        "S_x_mid",
        "S_x_outlet",
        "S_x_terminal_mean",
        "S_x_inlet_outlet_asymmetry",
        "S_x_mid_minus_terminal",
    ]
    for role, rows in sorted(by_role.items()):
        summary["by_role"][role] = {
            column: median_or_nan(
                [
                    float(row[column])
                    for row in rows
                    if isinstance(row.get(column), (int, float))
                ]
            )
            for column in metric_columns
        }
    for threshold in thresholds:
        slug = threshold_slug(threshold)
        summary["events"][f"outlet_first_ge_{slug}"] = first_event(
            xzone_rows,
            f"outlet_zone_ge_{slug}",
            "ge",
        )
        summary["events"][f"outlet_first_le_{slug}"] = first_event(
            xzone_rows,
            f"outlet_zone_le_{slug}",
            "ge",
        )
        summary["events"][f"domain_active_fraction_ge_95pct_{slug}"] = first_event(
            [
                {
                    **row,
                    f"domain_active_fraction_ge_95pct_{slug}": int(
                        isinstance(row.get(f"active_bin_fraction_ge_{slug}"), (int, float))
                        and row[f"active_bin_fraction_ge_{slug}"] >= 0.95
                    ),
                }
                for row in xzone_rows
            ],
            f"domain_active_fraction_ge_95pct_{slug}",
            "ge",
        )
        summary["events"][f"domain_active_fraction_le_5pct_{slug}"] = first_event(
            [
                {
                    **row,
                    f"domain_active_fraction_le_5pct_{slug}": int(
                        isinstance(row.get(f"active_bin_fraction_ge_{slug}"), (int, float))
                        and row[f"active_bin_fraction_ge_{slug}"] <= 0.05
                    ),
                }
                for row in xzone_rows
            ],
            f"domain_active_fraction_le_5pct_{slug}",
            "ge",
        )
    return summary


def compare_xzone_rows(
    primary_rows: list[dict[str, Any]],
    sensitivity_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(primary_rows) != len(sensitivity_rows):
        raise ValueError("Primary and sensitivity x-zone row counts differ.")
    columns = [
        "S_x_inlet",
        "S_x_mid",
        "S_x_outlet",
        "S_x_terminal_mean",
        "S_x_inlet_outlet_asymmetry",
        "S_x_mid_minus_terminal",
    ]
    comparison_rows: list[dict[str, Any]] = []
    for row_a, row_b in zip(primary_rows, sensitivity_rows):
        if row_a.get("label") != row_b.get("label"):
            raise ValueError("Primary and sensitivity x-zone labels differ.")
        out: dict[str, Any] = {
            "frame_index": row_a["frame_index"],
            "time_s": row_a["time_s"],
            "label": row_a["label"],
            "role": row_a["role"],
        }
        for column in columns:
            out[f"{column}_A"] = row_a.get(column, float("nan"))
            out[f"{column}_B"] = row_b.get(column, float("nan"))
            out[f"{column}_B_minus_A"] = out[f"{column}_B"] - out[f"{column}_A"]
            out[f"abs_{column}_sensitivity"] = abs(out[f"{column}_B_minus_A"])
        comparison_rows.append(out)
    return comparison_rows


def write_regional_proxy_outputs(
    config: dict[str, Any],
    paths: dict[str, Path],
    xbin_primary: list[dict[str, str]],
    xbin_sensitivity: list[dict[str, str]],
) -> dict[str, Any]:
    regional_config = config.get("regional_metrics", {})
    if not regional_config.get("enabled", True) or not xbin_primary:
        return {}
    if not xbin_sensitivity:
        return {}

    primary_rows, definition = build_xzone_rows(xbin_primary, regional_config)
    sensitivity_rows, sensitivity_definition = build_xzone_rows(
        xbin_sensitivity,
        regional_config,
    )
    if definition["n_bins"] != sensitivity_definition["n_bins"]:
        raise ValueError("Primary and sensitivity x-bin definitions differ.")
    comparison_rows = compare_xzone_rows(primary_rows, sensitivity_rows)

    primary_path = paths["matlab_dir"] / "S_NAPL_color_xzones_primary_A.csv"
    sensitivity_path = paths["matlab_dir"] / "S_NAPL_color_xzones_sensitivity_B.csv"
    comparison_path = (
        paths["matlab_dir"] / "S_NAPL_color_xzone_A_B_sensitivity_comparison.csv"
    )
    summary_path = paths["matlab_dir"] / "S_NAPL_color_regional_proxy_summary.json"
    write_dict_csv(primary_path, primary_rows)
    write_dict_csv(sensitivity_path, sensitivity_rows)
    write_dict_csv(comparison_path, comparison_rows)

    thresholds = [
        float(value)
        for value in regional_config.get("front_thresholds", [0.2, 0.5])
    ]
    summary = {
        "definition": definition,
        "semantics": {
            "x_zones": "flow-direction zones derived from x-bin color-index output",
            "front_breakthrough": (
                "operational proxies from thresholded x-bin S_NAPL_color; "
                "not binary-mask fingering metrics"
            ),
            "core_edge_geom": (
                "not computed here; requires solid_mask/core_flow mask and "
                "uses bwdist(solid_mask) style geometry"
            ),
        },
        "primary": summarize_xzone_rows(primary_rows, thresholds),
        "sensitivity": summarize_xzone_rows(sensitivity_rows, thresholds),
        "paths": {
            "xzone_primary_csv": str(primary_path),
            "xzone_sensitivity_csv": str(sensitivity_path),
            "xzone_comparison_csv": str(comparison_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["paths"]["regional_proxy_summary_json"] = str(summary_path)
    return summary


def validate_outputs(
    config: dict[str, Any],
    paths: dict[str, Path],
    commands: list[str],
) -> dict[str, Any]:
    selected_steps = set(config.get("steps", []))
    segmentation_requested = bool({"segpilot", "segmorph"} & selected_steps)
    branch_c_requested = bool({"matlab"} & selected_steps) or not segmentation_requested
    manifest_summary_path = paths["manifest_dir"] / "accepted_frames_summary.json"
    primary_path = paths["matlab_dir"] / "S_NAPL_color_primary_A.csv"
    sensitivity_path = paths["matlab_dir"] / "S_NAPL_color_sensitivity_B.csv"
    comparison_path = (
        paths["matlab_dir"] / "S_NAPL_color_A_B_sensitivity_comparison.csv"
    )
    xbin_primary_path = paths["matlab_dir"] / "S_NAPL_color_xbins_primary_A.csv"
    xbin_sensitivity_path = (
        paths["matlab_dir"] / "S_NAPL_color_xbins_sensitivity_B.csv"
    )
    segpilot_candidate_path = paths["segmentation_pilot_dir"] / "candidate_summary.csv"
    segpilot_sweep_path = paths["segmentation_pilot_dir"] / "threshold_sweep_all.csv"
    segmorph_timeseries_path = (
        paths["segmentation_morphology_dir"] / "red_mask_timeseries.csv"
    )
    segmorph_summary_path = (
        paths["segmentation_morphology_dir"] / "red_blob_summary_timeseries.csv"
    )
    branch_c_paths = [primary_path, sensitivity_path, comparison_path]
    branch_c_available = all(path_value.is_file() for path_value in branch_c_paths)
    missing = [
        str(path_value)
        for path_value in branch_c_paths
        if not path_value.is_file()
    ]
    if missing and branch_c_requested:
        raise FileNotFoundError(f"Missing validation input(s): {missing}")

    primary = read_csv_rows(primary_path) if primary_path.is_file() else []
    sensitivity = read_csv_rows(sensitivity_path) if sensitivity_path.is_file() else []
    comparison = read_csv_rows(comparison_path) if comparison_path.is_file() else []
    xbin_primary = (
        read_csv_rows(xbin_primary_path) if xbin_primary_path.is_file() else []
    )
    xbin_sensitivity = (
        read_csv_rows(xbin_sensitivity_path) if xbin_sensitivity_path.is_file() else []
    )
    segpilot_candidates = (
        read_csv_rows(segpilot_candidate_path)
        if segpilot_candidate_path.is_file()
        else []
    )
    segpilot_sweep = (
        read_csv_rows(segpilot_sweep_path)
        if segpilot_sweep_path.is_file()
        else []
    )
    segmorph_timeseries = (
        read_csv_rows(segmorph_timeseries_path)
        if segmorph_timeseries_path.is_file()
        else []
    )
    segmorph_summary = (
        read_csv_rows(segmorph_summary_path)
        if segmorph_summary_path.is_file()
        else []
    )
    manifest_summary = (
        read_json(manifest_summary_path) if manifest_summary_path.is_file() else {}
    )
    expected_rows = config.get("validation", {}).get("expected_timeseries_rows")
    if expected_rows is None:
        expected_rows = manifest_summary.get("timeseries_frame_count")

    failures: list[str] = []
    warnings: list[str] = []
    if branch_c_available and expected_rows is not None and len(primary) != int(expected_rows):
        failures.append(
            f"Primary row count {len(primary)} != expected {expected_rows}."
        )
    if branch_c_available and len(primary) != len(sensitivity):
        failures.append("Primary and sensitivity row counts differ.")
    if branch_c_available and len(primary) != len(comparison):
        failures.append("Primary and comparison row counts differ.")

    primary_labels = [row.get("label", "") for row in primary]
    sensitivity_labels = [row.get("label", "") for row in sensitivity]
    comparison_labels = [row.get("label", "") for row in comparison]
    if branch_c_available and primary_labels != sensitivity_labels:
        failures.append("Primary and sensitivity labels differ.")
    if branch_c_available and primary_labels != comparison_labels:
        failures.append("Primary and comparison labels differ.")

    primary_metric = metric_summary(primary, "S_NAPL_color")
    sensitivity_metric = metric_summary(sensitivity, "S_NAPL_color")
    comparison_metric = metric_summary(comparison, "abs_endpoint_sensitivity")
    if branch_c_available and primary_metric["nan_or_missing_count"]:
        failures.append("Primary S_NAPL_color contains NaN or missing values.")
    if branch_c_available and sensitivity_metric["nan_or_missing_count"]:
        failures.append("Sensitivity S_NAPL_color contains NaN or missing values.")
    if branch_c_available and comparison_metric["nan_or_missing_count"]:
        failures.append("Comparison endpoint sensitivity contains NaN or missing values.")
    xbin_primary_metric = (
        metric_summary(xbin_primary, "S_NAPL_color_xbin") if xbin_primary else {}
    )
    xbin_sensitivity_metric = (
        metric_summary(xbin_sensitivity, "S_NAPL_color_xbin")
        if xbin_sensitivity
        else {}
    )
    if xbin_primary_metric and xbin_primary_metric["nan_or_missing_count"]:
        failures.append("Primary x-bin S_NAPL_color_xbin contains NaN or missing values.")
    if xbin_sensitivity_metric and xbin_sensitivity_metric["nan_or_missing_count"]:
        failures.append(
            "Sensitivity x-bin S_NAPL_color_xbin contains NaN or missing values."
        )
    if bool(xbin_primary) != bool(xbin_sensitivity):
        failures.append("Primary and sensitivity x-bin outputs are not both present.")
    if xbin_primary and xbin_sensitivity and len(xbin_primary) != len(xbin_sensitivity):
        failures.append("Primary and sensitivity x-bin row counts differ.")

    regional_proxy: dict[str, Any] = {}
    if xbin_primary and xbin_sensitivity and not failures:
        regional_proxy = write_regional_proxy_outputs(
            config,
            paths,
            xbin_primary,
            xbin_sensitivity,
        )

    if "segpilot" in selected_steps:
        if not segpilot_candidates:
            failures.append("Segmentation pilot candidate_summary.csv is missing or empty.")
        if not segpilot_sweep:
            failures.append("Segmentation pilot threshold_sweep_all.csv is missing or empty.")
    if "segmorph" in selected_steps:
        if not segmorph_timeseries:
            failures.append("Segmentation morphology red_mask_timeseries.csv is missing or empty.")
        if not segmorph_summary:
            failures.append(
                "Segmentation morphology red_blob_summary_timeseries.csv is missing or empty."
            )
        if (
            segmorph_timeseries
            and branch_c_available
            and len(segmorph_timeseries) != len(primary)
        ):
            failures.append(
                "Segmentation morphology row count differs from Branch C primary rows."
            )
        if (
            segmorph_timeseries
            and not branch_c_available
            and expected_rows is not None
            and len(segmorph_timeseries) != int(expected_rows)
        ):
            failures.append(
                "Segmentation morphology row count differs from expected manifest rows."
            )

    segpilot_area_metric = (
        metric_summary(segpilot_sweep, "red_mask_area_fraction")
        if segpilot_sweep
        else {}
    )
    segmorph_area_metric = (
        metric_summary(segmorph_timeseries, "red_mask_area_fraction")
        if segmorph_timeseries
        else {}
    )
    segmorph_blob_metric = (
        metric_summary(segmorph_timeseries, "num_blobs")
        if segmorph_timeseries
        else {}
    )
    segmorph_interface_quality_summary = (
        segmorph_interface_quality(segmorph_timeseries)
        if segmorph_timeseries
        else {}
    )
    if segmorph_area_metric and segmorph_area_metric["nan_or_missing_count"]:
        failures.append(
            "Segmentation morphology red_mask_area_fraction contains NaN or missing values."
        )
    if segmorph_blob_metric and segmorph_blob_metric["nan_or_missing_count"]:
        failures.append("Segmentation morphology num_blobs contains NaN or missing values.")
    if segmorph_interface_quality_summary:
        missing_interface_columns = segmorph_interface_quality_summary["missing_columns"]
        if missing_interface_columns:
            failures.append(
                "Segmentation morphology interface/contact columns are missing: "
                + ", ".join(missing_interface_columns)
            )
        for key, message in (
            ("alias_mismatch_count", "InterfaceArea differs from dnapl_water_length_px."),
            (
                "water_length_nonpositive_with_mask_count",
                "dnapl_water_length_px is nonpositive for rows with red mask.",
            ),
            ("solid_length_negative_count", "dnapl_solid_length_px is negative or missing."),
            (
                "solid_contact_fraction_out_of_range_count",
                "solid_contact_fraction is missing or outside [0, 1].",
            ),
            ("a_i_2D_proxy_bad_count", "a_i_2D_proxy is missing or negative for rows with red mask."),
            ("interface_semantics_bad_count", "interface_semantics has unexpected values."),
        ):
            if segmorph_interface_quality_summary.get(key, 0):
                failures.append(f"{message} Count={segmorph_interface_quality_summary[key]}.")

    threshold = float(config.get("validation", {}).get("full_napl_low_threshold", 0.5))
    low_full_rows = [
        row
        for row in primary
        if row.get("role") == "full_napl"
        and (finite_float(row.get("S_NAPL_color", "")) or 0.0) < threshold
    ]
    if low_full_rows:
        warnings.append(
            f"{len(low_full_rows)} full_napl rows are below {threshold}; "
            "this usually indicates file-level role labels span a transition."
        )

    summary = {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "paths": {
            "manifest_summary": str(manifest_summary_path),
            "cache_dir": str(paths["cache_dir"]),
            "matlab_dir": str(paths["matlab_dir"]),
            "primary_csv": str(primary_path),
            "sensitivity_csv": str(sensitivity_path),
            "comparison_csv": str(comparison_path),
            "xbin_primary_csv": str(xbin_primary_path) if xbin_primary_path.is_file() else "",
            "xbin_sensitivity_csv": str(xbin_sensitivity_path)
            if xbin_sensitivity_path.is_file()
            else "",
            "segmentation_pilot_candidate_summary_csv": str(segpilot_candidate_path)
            if segpilot_candidate_path.is_file()
            else "",
            "segmentation_pilot_threshold_sweep_csv": str(segpilot_sweep_path)
            if segpilot_sweep_path.is_file()
            else "",
            "segmentation_morphology_timeseries_csv": str(segmorph_timeseries_path)
            if segmorph_timeseries_path.is_file()
            else "",
            "segmentation_morphology_summary_csv": str(segmorph_summary_path)
            if segmorph_summary_path.is_file()
            else "",
            **regional_proxy.get("paths", {}),
            "timeline_postprocess_dir": str(paths["timeline_dir"]),
            "residual_trapping_postprocess_dir": str(paths["residual_dir"]),
            "analysis_package_dir": str(paths["analysis_dir"]),
            "analysis_package_provenance_json": str(
                paths["analysis_dir"] / "analysis_package_provenance.json"
            )
            if (paths["analysis_dir"] / "analysis_package_provenance.json").is_file()
            else "",
            "physical_metadata_json": str(
                resolve_path(config.get("physical_metadata_path"))
                or paths["run_config_dir"] / f"{run_id_for(config)}_physical_metadata.json"
            )
            if config.get("physical_metadata_path") or config.get("physical_metadata")
            else "",
        },
        "row_counts": {
            "expected_timeseries_rows": expected_rows,
            "primary": len(primary),
            "sensitivity": len(sensitivity),
            "comparison": len(comparison),
            "xbin_primary": len(xbin_primary),
            "xbin_sensitivity": len(xbin_sensitivity),
            "segmentation_pilot_candidates": len(segpilot_candidates),
            "segmentation_pilot_sweep": len(segpilot_sweep),
            "segmentation_morphology_timeseries": len(segmorph_timeseries),
            "segmentation_morphology_summary": len(segmorph_summary),
        },
        "time_s": metric_summary(primary, "time_s")
        if primary and "time_s" in primary[0]
        else {},
        "primary": {
            "S_NAPL_color": primary_metric,
            "by_role": metric_by_role(primary, "S_NAPL_color"),
            "full_napl_low_count": len(low_full_rows),
            "full_napl_low_sample_labels": [
                row.get("label", "") for row in low_full_rows[:10]
            ],
        },
        "sensitivity": {
            "S_NAPL_color": sensitivity_metric,
            "by_role": metric_by_role(sensitivity, "S_NAPL_color"),
        },
        "xbin_primary": {
            "S_NAPL_color_xbin": xbin_primary_metric,
            "by_role": metric_by_role(xbin_primary, "S_NAPL_color_xbin")
            if xbin_primary
            else {},
        },
        "xbin_sensitivity": {
            "S_NAPL_color_xbin": xbin_sensitivity_metric,
            "by_role": metric_by_role(xbin_sensitivity, "S_NAPL_color_xbin")
            if xbin_sensitivity
            else {},
        },
        "endpoint_sensitivity": comparison_metric,
        "segmentation_pilot": {
            "red_mask_area_fraction": segpilot_area_metric,
        },
        "segmentation_morphology": {
            "red_mask_area_fraction": segmorph_area_metric,
            "num_blobs": segmorph_blob_metric,
            "interface_contact": segmorph_interface_quality_summary,
            "by_role": metric_by_role(segmorph_timeseries, "red_mask_area_fraction")
            if segmorph_timeseries
            else {},
        },
        "regional_proxy": {
            key: value
            for key, value in regional_proxy.items()
            if key != "paths"
        },
        "commands": commands,
    }
    paths["matlab_dir"].mkdir(parents=True, exist_ok=True)
    summary_path = paths["matlab_dir"] / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"RUN_SUMMARY {summary_path}")
    if failures:
        raise RuntimeError("; ".join(failures))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone runner for the DNAPL BasicPy HDF5 Branch C "
            "S_NAPL_color time-series workflow."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    parser.add_argument(
        "--steps",
        nargs="+",
        default=None,
        help=(
            "Steps to run: manifest cache matlab segpilot segmorph validate "
            "timeline residual analysis. "
            "Comma-separated values are also accepted."
        ),
    )
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--roi-mask", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--manifest-dir", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--matlab-dir", default=None)
    parser.add_argument("--segmentation-pilot-dir", default=None)
    parser.add_argument("--segmentation-morphology-dir", default=None)
    parser.add_argument("--timeline-dir", default=None)
    parser.add_argument("--residual-dir", default=None)
    parser.add_argument("--analysis-dir", default=None)
    parser.add_argument("--analysis-run-label", default=None)
    parser.add_argument("--physical-metadata", default=None)
    parser.add_argument("--matlab-command", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-manifest", action="store_true")
    parser.add_argument("--force-cache", action="store_true")
    parser.add_argument("--resume-cache", dest="resume_cache", action="store_true")
    parser.add_argument("--no-resume-cache", dest="resume_cache", action="store_false")
    parser.set_defaults(resume_cache=None)
    parser.add_argument("--allow-lzf", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_effective_config(args)
    paths = build_paths(args, config)
    commands: list[str] = []
    selected_steps = config["steps"]
    effective_config_candidate = effective_config_path_for(config, paths)
    validation_summary: dict[str, Any] | None = None

    compression = str(config.get("cache", {}).get("compression", "none"))
    if "matlab" in selected_steps and compression == "lzf" and not config["allow_lzf"]:
        raise ValueError(
            "HDF5 compression 'lzf' is not MATLAB-compatible in this workflow; "
            "use compression 'none' or pass --allow-lzf only for non-MATLAB diagnostics."
        )
    if (
        ("segpilot" in selected_steps or "segmorph" in selected_steps)
        and compression == "lzf"
        and not config["allow_lzf"]
    ):
        raise ValueError(
            "HDF5 compression 'lzf' is not MATLAB-compatible for segmentation "
            "morphology; use compression 'none'."
        )

    effective_config_path = None
    endpoint_policy_input = None
    water_endpoints_input = None
    physical_metadata_input = None
    if not args.dry_run:
        effective_config_path = write_effective_config(config, paths)
        physical_metadata_input = write_physical_metadata_input(config, paths)
        if "manifest" in selected_steps:
            endpoint_policy_input = write_endpoint_policy_input(
                config,
                paths["manifest_dir"],
            )
            water_endpoints_input = write_water_endpoints_input(
                config,
                paths["manifest_dir"],
            )
    elif "manifest" in selected_steps:
        if config.get("endpoint_policy"):
            endpoint_policy_input = paths["manifest_dir"] / "endpoint_policy_input.json"
        if config.get("water_endpoints"):
            water_endpoints_input = paths["manifest_dir"] / "water_endpoints_input.json"
    elif config.get("physical_metadata_path"):
        physical_metadata_input = resolve_path(config["physical_metadata_path"])
    elif config.get("physical_metadata"):
        physical_metadata_input = paths["run_config_dir"] / f"{run_id_for(config)}_physical_metadata.json"

    if effective_config_path is not None:
        print(f"EFFECTIVE_CONFIG {effective_config_path}")

    if "manifest" in selected_steps:
        run_command(
            manifest_command(
                config,
                paths,
                endpoint_policy_input,
                water_endpoints_input,
            ),
            args.dry_run,
            commands,
        )
    if "cache" in selected_steps:
        run_command(cache_command(config, paths), args.dry_run, commands)
    if "matlab" in selected_steps:
        run_command(matlab_command(config, paths), args.dry_run, commands)
    if "segpilot" in selected_steps:
        run_command(
            segmentation_command(
                config,
                paths,
                effective_config_path or effective_config_candidate,
                "pilot",
            ),
            args.dry_run,
            commands,
        )
    if "segmorph" in selected_steps:
        run_command(
            segmentation_command(
                config,
                paths,
                effective_config_path or effective_config_candidate,
                "morphology",
            ),
            args.dry_run,
            commands,
        )
    if "validate" in selected_steps:
        if args.dry_run:
            print("VALIDATE_SKIPPED_DRY_RUN")
        else:
            validation_summary = validate_outputs(config, paths, commands)
    if "timeline" in selected_steps:
        run_command(timeline_command(config, paths), args.dry_run, commands)
    if "residual" in selected_steps:
        run_command(residual_command(config, paths), args.dry_run, commands)
    if "analysis" in selected_steps:
        run_command(
            analysis_command(config, paths, physical_metadata_input),
            args.dry_run,
            commands,
        )
    if validation_summary is not None and not args.dry_run:
        validation_summary["commands"] = commands
        analysis_provenance = paths["analysis_dir"] / "analysis_package_provenance.json"
        validation_summary.setdefault("paths", {})[
            "analysis_package_provenance_json"
        ] = str(analysis_provenance) if analysis_provenance.is_file() else ""
        summary_path = paths["matlab_dir"] / "run_summary.json"
        summary_path.write_text(json.dumps(validation_summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
