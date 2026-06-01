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
STEPS = ("manifest", "cache", "matlab", "validate")


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
        return list(STEPS)
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
    run_config_dir = output_root / "run_configs"
    return {
        "output_root": output_root,
        "manifest_dir": manifest_dir,
        "cache_dir": cache_dir,
        "matlab_dir": matlab_dir,
        "run_config_dir": run_config_dir,
    }


def write_effective_config(config: dict[str, Any], paths: dict[str, Path]) -> Path:
    paths["run_config_dir"].mkdir(parents=True, exist_ok=True)
    run_id = f'{config["run_name"]}_{config.get("run_suffix", config["mode"])}'
    config_path = paths["run_config_dir"] / f"{run_id}_effective.json"
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


def manifest_command(
    config: dict[str, Any],
    paths: dict[str, Path],
    endpoint_policy_input: Path | None,
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


def validate_outputs(
    config: dict[str, Any],
    paths: dict[str, Path],
    commands: list[str],
) -> dict[str, Any]:
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
    required_paths = [primary_path, sensitivity_path, comparison_path]
    missing = [str(path_value) for path_value in required_paths if not path_value.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing validation input(s): {missing}")

    primary = read_csv_rows(primary_path)
    sensitivity = read_csv_rows(sensitivity_path)
    comparison = read_csv_rows(comparison_path)
    xbin_primary = (
        read_csv_rows(xbin_primary_path) if xbin_primary_path.is_file() else []
    )
    xbin_sensitivity = (
        read_csv_rows(xbin_sensitivity_path) if xbin_sensitivity_path.is_file() else []
    )
    manifest_summary = (
        read_json(manifest_summary_path) if manifest_summary_path.is_file() else {}
    )
    expected_rows = config.get("validation", {}).get("expected_timeseries_rows")
    if expected_rows is None:
        expected_rows = manifest_summary.get("timeseries_frame_count")

    failures: list[str] = []
    warnings: list[str] = []
    if expected_rows is not None and len(primary) != int(expected_rows):
        failures.append(
            f"Primary row count {len(primary)} != expected {expected_rows}."
        )
    if len(primary) != len(sensitivity):
        failures.append("Primary and sensitivity row counts differ.")
    if len(primary) != len(comparison):
        failures.append("Primary and comparison row counts differ.")

    primary_labels = [row.get("label", "") for row in primary]
    sensitivity_labels = [row.get("label", "") for row in sensitivity]
    comparison_labels = [row.get("label", "") for row in comparison]
    if primary_labels != sensitivity_labels:
        failures.append("Primary and sensitivity labels differ.")
    if primary_labels != comparison_labels:
        failures.append("Primary and comparison labels differ.")

    primary_metric = metric_summary(primary, "S_NAPL_color")
    sensitivity_metric = metric_summary(sensitivity, "S_NAPL_color")
    comparison_metric = metric_summary(comparison, "abs_endpoint_sensitivity")
    if primary_metric["nan_or_missing_count"]:
        failures.append("Primary S_NAPL_color contains NaN or missing values.")
    if sensitivity_metric["nan_or_missing_count"]:
        failures.append("Sensitivity S_NAPL_color contains NaN or missing values.")
    if comparison_metric["nan_or_missing_count"]:
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
        },
        "row_counts": {
            "expected_timeseries_rows": expected_rows,
            "primary": len(primary),
            "sensitivity": len(sensitivity),
            "comparison": len(comparison),
            "xbin_primary": len(xbin_primary),
            "xbin_sensitivity": len(xbin_sensitivity),
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
        help="Steps to run: manifest cache matlab validate. Comma-separated values are also accepted.",
    )
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--roi-mask", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--manifest-dir", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--matlab-dir", default=None)
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

    compression = str(config.get("cache", {}).get("compression", "none"))
    if "matlab" in selected_steps and compression == "lzf" and not config["allow_lzf"]:
        raise ValueError(
            "HDF5 compression 'lzf' is not MATLAB-compatible in this workflow; "
            "use compression 'none' or pass --allow-lzf only for non-MATLAB diagnostics."
        )

    effective_config_path = None
    endpoint_policy_input = None
    if not args.dry_run:
        effective_config_path = write_effective_config(config, paths)
        if "manifest" in selected_steps:
            endpoint_policy_input = write_endpoint_policy_input(
                config,
                paths["manifest_dir"],
            )
    elif "manifest" in selected_steps and config.get("endpoint_policy"):
        endpoint_policy_input = paths["manifest_dir"] / "endpoint_policy_input.json"

    if effective_config_path is not None:
        print(f"EFFECTIVE_CONFIG {effective_config_path}")

    if "manifest" in selected_steps:
        run_command(
            manifest_command(config, paths, endpoint_policy_input),
            args.dry_run,
            commands,
        )
    if "cache" in selected_steps:
        run_command(cache_command(config, paths), args.dry_run, commands)
    if "matlab" in selected_steps:
        run_command(matlab_command(config, paths), args.dry_run, commands)
    if "validate" in selected_steps:
        if args.dry_run:
            print("VALIDATE_SKIPPED_DRY_RUN")
        else:
            validate_outputs(config, paths, commands)


if __name__ == "__main__":
    main()
