from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from residual_postprocess_common import timestamp, write_json  # noqa: E402


NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")

FIELD_ORDER = [
    "pixel_size_um",
    "pixel_size_m",
    "chip_geometric_volume_m3",
    "pore_volume_m3",
    "pore_area_px",
    "channel_depth_m",
    "flow_domain_width_m",
    "frame_time_available",
    "real_time_available",
    "frame_interval_s",
    "frame_count",
    "surfactant_type",
    "surfactant_concentration",
    "surfactant_concentration_unit",
    "surfactant_concentration_basis",
    "active_displacement_fluid",
    "active_flow_rate_ul_min",
    "residual_formation_displacement_fluid",
    "residual_formation_flow_rate_ul_min",
    "pump_rate_ul_min",
    "flow_rate",
    "velocity",
    "nominal_velocity_m_s",
    "viscosity",
    "displacing_phase_viscosity",
    "napl_viscosity",
    "interfacial_tension",
    "capillary_number_nominal",
    "log10_capillary_number_nominal",
    "temperature",
    "diffusion_coefficient",
]

UNITS = {
    "pixel_size_um": "um/px",
    "pixel_size_m": "m/px",
    "chip_geometric_volume_m3": "m^3",
    "pore_volume_m3": "m^3",
    "pore_area_px": "px^2",
    "channel_depth_m": "m",
    "flow_domain_width_m": "m",
    "frame_time_available": "boolean",
    "real_time_available": "boolean",
    "frame_interval_s": "s",
    "frame_count": "frames",
    "surfactant_type": "",
    "surfactant_concentration": "unknown",
    "surfactant_concentration_unit": "",
    "surfactant_concentration_basis": "",
    "active_displacement_fluid": "",
    "active_flow_rate_ul_min": "uL/min",
    "residual_formation_displacement_fluid": "",
    "residual_formation_flow_rate_ul_min": "uL/min",
    "pump_rate_ul_min": "uL/min",
    "flow_rate": "m^3/s",
    "velocity": "",
    "nominal_velocity_m_s": "m/s",
    "viscosity": "Pa*s",
    "displacing_phase_viscosity": "Pa*s",
    "napl_viscosity": "Pa*s",
    "interfacial_tension": "N/m",
    "capillary_number_nominal": "",
    "log10_capillary_number_nominal": "",
    "temperature": "C",
    "diffusion_coefficient": "m^2/s",
}

TRANSPORT_FIELDS = [
    "flow_rate",
    "velocity",
    "viscosity",
    "displacing_phase_viscosity",
    "interfacial_tension",
    "temperature",
]


def latest_by_mtime(paths):
    paths = [Path(p) for p in paths if Path(p).exists()]
    if not paths:
        return None
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))


def normalized_column_map(columns):
    return {re.sub(r"[^a-z0-9]+", "", str(col).lower()): col for col in columns}


def as_float(value):
    if value is None:
        return None
    try:
        numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric) or not np.isfinite(float(numeric)):
        return None
    return float(numeric)


def as_bool(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0", "", "nan", "none"}:
        return False
    return bool(text)


def first_number(text):
    match = NUMBER_RE.search(str(text))
    if not match:
        return None
    return as_float(match.group(0))


def field_record(name, value=None, availability="unavailable", source="", confidence="none", notes=""):
    return {
        "key": name,
        "value": value,
        "unit": UNITS.get(name, ""),
        "availability": availability,
        "source": source,
        "confidence": confidence,
        "notes": notes,
    }


def parse_analysis_report(path):
    values = {}
    if path is None or not Path(path).exists():
        return values
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        label = line.lower()
        if "pixel size" in label:
            values["pixel_size_um"] = first_number(line)
        elif "chip geometric volume" in label:
            values["chip_geometric_volume_m3"] = first_number(line)
        elif "flow domain pore volume" in label or "pore volume" in label:
            values["pore_volume_m3"] = first_number(line)
    return {key: value for key, value in values.items() if value is not None}


def read_latest_saturation(output_root):
    path = latest_by_mtime(Path(output_root).glob("saturation_*.csv"))
    if path is None:
        return None, {}
    df = pd.read_csv(path)
    if df.empty:
        return path, {}
    columns = normalized_column_map(df.columns)
    aliases = {
        "chip_geometric_volume_m3": ["chipvolumem3", "chipgeometricvolumem3"],
        "pore_volume_m3": ["porevolumem3", "flowdomainporevolumem3"],
        "pore_area_px": ["poreareapx", "poreareapx2", "flowdomainporeareapx"],
    }
    values = {}
    row = df.iloc[0]
    for key, names in aliases.items():
        column = next((columns[name] for name in names if name in columns), None)
        if column is not None:
            value = as_float(row[column])
            if value is not None:
                values[key] = value
    return path, values


def read_latest_timeline(output_root):
    path = latest_by_mtime(Path(output_root).glob("frame_timeline_*.csv"))
    if path is None:
        return None, {"available": False}
    df = pd.read_csv(path)
    columns = normalized_column_map(df.columns)
    real_col = columns.get("realtimes")
    interval_col = columns.get("intervals")
    frame_time_col = columns.get("frametime")
    values = {"available": False, "frame_count": int(len(df))}

    if interval_col is not None:
        intervals = pd.to_numeric(df[interval_col], errors="coerce")
        finite = intervals[np.isfinite(intervals) & (intervals > 0)]
        if len(finite):
            values["available"] = True
            values["frame_interval_s"] = float(finite.median())

    if real_col is not None:
        real_time = pd.to_numeric(df[real_col], errors="coerce")
        finite = real_time[np.isfinite(real_time)]
        if len(finite):
            values["available"] = True
            values["real_time_available"] = bool(finite.nunique() > 1 or len(finite) == 1)
            if "frame_interval_s" not in values and len(finite) > 1:
                diffs = finite.sort_values().diff().dropna()
                diffs = diffs[diffs > 0]
                if len(diffs):
                    values["frame_interval_s"] = float(diffs.median())

    if frame_time_col is not None and not values["available"]:
        frame_time = pd.to_numeric(df[frame_time_col], errors="coerce")
        finite = frame_time[np.isfinite(frame_time)]
        if len(finite):
            values["available"] = True
            values["real_time_available"] = False

    values.setdefault("real_time_available", False)
    return path, values


def find_latest_audit_csv(output_root):
    candidates = list(Path(output_root).glob("**/experiment_metadata_audit.csv"))
    return latest_by_mtime(candidates)


def read_audit_rows(path):
    if path is None or not Path(path).exists():
        return []
    df = pd.read_csv(path)
    rows = []
    for _, row in df.iterrows():
        key = str(row.get("metadata_key", "")).strip()
        if not key:
            continue
        rows.append(
            {
                "metadata_key": key,
                "found": as_bool(row.get("found", False)),
                "source_file": str(row.get("source_file", "")),
                "value_preview": str(row.get("value_preview", "")),
                "unit": str(row.get("unit", "")),
                "required_for": str(row.get("required_for", "")),
            }
        )
    return rows


def parse_treatment_from_folder(output_root):
    text = " ".join(str(part) for part in Path(output_root).parts)
    found_tween = re.search(r"twe(?:en|em)[\s_-]*80", text, flags=re.IGNORECASE) is not None
    concentration = None
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:%|pct|percent)(?![a-z0-9])", text, flags=re.IGNORECASE)
    if match:
        concentration = float(match.group(1))
    return found_tween, concentration


def find_manual_metadata_json(output_root, postprocess_dir, manual_metadata_json=None):
    if manual_metadata_json:
        path = Path(manual_metadata_json)
        return path if path.exists() else None
    candidates = [
        Path(postprocess_dir) / "experiment_metadata_manual.json",
        Path(output_root) / "experiment_metadata_manual.json",
    ]
    return next((path for path in candidates if path.exists()), None)


def read_manual_metadata(path):
    if path is None:
        return {}
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    fields = payload.get("fields", payload)
    if not isinstance(fields, dict):
        raise ValueError(f"manual metadata JSON fields must be an object: {path}")
    return fields


def manual_record_value(record):
    if isinstance(record, dict) and "value" in record:
        return record.get("value")
    return record


def manual_record_attr(record, key, default=""):
    if isinstance(record, dict):
        return record.get(key, default)
    return default


def set_manual_field(fields, provenance, key, value, source_key, source_file, record, unit=None, transform=None):
    if value is None:
        return
    if transform is not None:
        value = transform(value)
    fields[key] = field_record(
        key,
        value,
        manual_record_attr(record, "availability", "manual"),
        manual_record_attr(record, "source", source_file.name),
        manual_record_attr(record, "confidence", "medium"),
        manual_record_attr(record, "notes", ""),
    )
    if unit is not None:
        fields[key]["unit"] = unit
    add_provenance(
        provenance,
        key,
        source_file.name,
        source_key,
        value,
        fields[key]["confidence"],
        fields[key]["notes"],
    )


def apply_manual_metadata(fields, provenance, manual_fields, manual_path):
    if not manual_fields:
        return
    manual_path = Path(manual_path)

    for source_key in ["active_displacement_fluid", "residual_formation_displacement_fluid"]:
        record = manual_fields.get(source_key)
        value = manual_record_value(record)
        if value is not None:
            set_manual_field(fields, provenance, source_key, str(value), f"fields.{source_key}", manual_path, record)

    residual_record = manual_fields.get("residual_formation_flow_rate_ul_min")
    residual_rate = as_float(manual_record_value(residual_record))
    if residual_rate is not None:
        set_manual_field(
            fields,
            provenance,
            "residual_formation_flow_rate_ul_min",
            residual_rate,
            "fields.residual_formation_flow_rate_ul_min",
            manual_path,
            residual_record,
            unit="uL/min",
        )

    active_record = manual_fields.get("active_flow_rate_ul_min")
    active_rate_ul_min = as_float(manual_record_value(active_record))
    if active_rate_ul_min is not None:
        set_manual_field(
            fields,
            provenance,
            "active_flow_rate_ul_min",
            active_rate_ul_min,
            "fields.active_flow_rate_ul_min",
            manual_path,
            active_record,
            unit="uL/min",
        )
        fields["pump_rate_ul_min"] = field_record(
            "pump_rate_ul_min",
            active_rate_ul_min,
            manual_record_attr(active_record, "availability", "manual"),
            manual_record_attr(active_record, "source", manual_path.name),
            manual_record_attr(active_record, "confidence", "medium"),
            "Alias of active_flow_rate_ul_min for the analyzed solubilization/displacement stage.",
        )
        add_provenance(
            provenance,
            "pump_rate_ul_min",
            manual_path.name,
            "alias:active_flow_rate_ul_min",
            active_rate_ul_min,
            fields["pump_rate_ul_min"]["confidence"],
            fields["pump_rate_ul_min"]["notes"],
        )
        flow_rate = active_rate_ul_min * 1e-9 / 60.0
        fields["flow_rate"] = field_record(
            "flow_rate",
            flow_rate,
            manual_record_attr(active_record, "availability", "manual"),
            manual_record_attr(active_record, "source", manual_path.name),
            manual_record_attr(active_record, "confidence", "medium"),
            "Derived from active_flow_rate_ul_min using 1 uL = 1e-9 m^3.",
        )
        add_provenance(
            provenance,
            "flow_rate",
            manual_path.name,
            "derived:fields.active_flow_rate_ul_min*1e-9/60",
            flow_rate,
            fields["flow_rate"]["confidence"],
            fields["flow_rate"]["notes"],
        )

    pump_record = manual_fields.get("pump_rate_ul_min")
    pump_rate_ul_min = as_float(manual_record_value(pump_record))
    if pump_rate_ul_min is not None and fields["pump_rate_ul_min"]["value"] is None:
        set_manual_field(
            fields,
            provenance,
            "pump_rate_ul_min",
            pump_rate_ul_min,
            "fields.pump_rate_ul_min",
            manual_path,
            pump_record,
            unit="uL/min",
        )
        flow_rate = pump_rate_ul_min * 1e-9 / 60.0
        fields["flow_rate"] = field_record(
            "flow_rate",
            flow_rate,
            manual_record_attr(pump_record, "availability", "manual"),
            manual_record_attr(pump_record, "source", manual_path.name),
            manual_record_attr(pump_record, "confidence", "medium"),
            "Derived from pump_rate_ul_min using 1 uL = 1e-9 m^3.",
        )
        add_provenance(
            provenance,
            "flow_rate",
            manual_path.name,
            "derived:fields.pump_rate_ul_min*1e-9/60",
            flow_rate,
            fields["flow_rate"]["confidence"],
            fields["flow_rate"]["notes"],
        )

    flow_m3_record = manual_fields.get("flow_rate_m3_s")
    flow_m3_s = as_float(manual_record_value(flow_m3_record))
    if flow_m3_s is not None:
        set_manual_field(fields, provenance, "flow_rate", flow_m3_s, "fields.flow_rate_m3_s", manual_path, flow_m3_record, unit="m^3/s")

    flow_record = manual_fields.get("flow_rate")
    flow_value = as_float(manual_record_value(flow_record))
    if flow_value is not None:
        unit = str(manual_record_attr(flow_record, "unit", "")).strip().lower()
        if unit in {"ul/min", "ul min-1", "microliter/min", "microliters/min"}:
            if fields["pump_rate_ul_min"]["value"] is None:
                set_manual_field(fields, provenance, "pump_rate_ul_min", flow_value, "fields.flow_rate", manual_path, flow_record, unit="uL/min")
            flow_value = flow_value * 1e-9 / 60.0
        set_manual_field(fields, provenance, "flow_rate", flow_value, "fields.flow_rate", manual_path, flow_record, unit="m^3/s")

    direct_mapping = {
        "surfactant_concentration_basis": ("surfactant_concentration_basis", None, ""),
        "temperature_c": ("temperature", as_float, "C"),
        "channel_depth_m": ("channel_depth_m", as_float, "m"),
        "flow_domain_width_m": ("flow_domain_width_m", as_float, "m"),
        "viscosity_pa_s": ("viscosity", as_float, "Pa*s"),
        "displacing_phase_viscosity_pa_s": ("displacing_phase_viscosity", as_float, "Pa*s"),
        "water_viscosity_pa_s": ("displacing_phase_viscosity", as_float, "Pa*s"),
        "napl_viscosity_pa_s": ("napl_viscosity", as_float, "Pa*s"),
        "oil_viscosity_pa_s": ("napl_viscosity", as_float, "Pa*s"),
        "interfacial_tension_n_m": ("interfacial_tension", as_float, "N/m"),
    }
    for source_key, (target_key, transform, unit) in direct_mapping.items():
        record = manual_fields.get(source_key)
        if record is None:
            continue
        value = manual_record_value(record)
        if transform is not None:
            value = transform(value)
        set_manual_field(fields, provenance, target_key, value, f"fields.{source_key}", manual_path, record, unit=unit)

    for source_key, target_key in [
        ("channel_depth_um", "channel_depth_m"),
        ("flow_domain_width_um", "flow_domain_width_m"),
        ("nominal_flow_domain_width_um", "flow_domain_width_m"),
        ("W_domain_um", "flow_domain_width_m"),
    ]:
        record = manual_fields.get(source_key)
        value_um = as_float(manual_record_value(record))
        if value_um is None:
            continue
        set_manual_field(
            fields,
            provenance,
            target_key,
            value_um * 1e-6,
            f"fields.{source_key}*1e-6",
            manual_path,
            record,
            unit="m",
        )

    viscosity_record = manual_fields.get("viscosity_mpa_s")
    viscosity_mpa_s = as_float(manual_record_value(viscosity_record))
    if viscosity_mpa_s is not None:
        set_manual_field(
            fields,
            provenance,
            "viscosity",
            viscosity_mpa_s * 1e-3,
            "fields.viscosity_mpa_s*1e-3",
            manual_path,
            viscosity_record,
            unit="Pa*s",
        )

    for source_key, target_key in [
        ("displacing_phase_viscosity_mpa_s", "displacing_phase_viscosity"),
        ("water_viscosity_mpa_s", "displacing_phase_viscosity"),
        ("napl_viscosity_mpa_s", "napl_viscosity"),
        ("oil_viscosity_mpa_s", "napl_viscosity"),
    ]:
        record = manual_fields.get(source_key)
        value_mpa_s = as_float(manual_record_value(record))
        if value_mpa_s is None:
            continue
        set_manual_field(
            fields,
            provenance,
            target_key,
            value_mpa_s * 1e-3,
            f"fields.{source_key}*1e-3",
            manual_path,
            record,
            unit="Pa*s",
        )

    if fields["displacing_phase_viscosity"]["value"] is not None and fields["viscosity"]["value"] is None:
        fields["viscosity"] = field_record(
            "viscosity",
            fields["displacing_phase_viscosity"]["value"],
            fields["displacing_phase_viscosity"]["availability"],
            fields["displacing_phase_viscosity"]["source"],
            fields["displacing_phase_viscosity"]["confidence"],
            "Alias of displacing_phase_viscosity for transport readiness and Ca_nom.",
        )
        add_provenance(
            provenance,
            "viscosity",
            manual_path.name,
            "alias:displacing_phase_viscosity",
            fields["viscosity"]["value"],
            fields["viscosity"]["confidence"],
            fields["viscosity"]["notes"],
        )

    ift_record = manual_fields.get("interfacial_tension_mn_m")
    ift_mn_m = as_float(manual_record_value(ift_record))
    if ift_mn_m is not None:
        set_manual_field(
            fields,
            provenance,
            "interfacial_tension",
            ift_mn_m * 1e-3,
            "fields.interfacial_tension_mn_m*1e-3",
            manual_path,
            ift_record,
            unit="N/m",
        )

    diffusion_record = manual_fields.get("diffusion_coefficient") or manual_fields.get("diffusion_coefficient_m2_s")
    diffusion_value = as_float(manual_record_value(diffusion_record))
    if diffusion_value is not None:
        availability = manual_record_attr(diffusion_record, "availability", "literature_default")
        fields["diffusion_coefficient"] = field_record(
            "diffusion_coefficient",
            diffusion_value,
            availability,
            manual_record_attr(diffusion_record, "source", manual_path.name),
            manual_record_attr(diffusion_record, "confidence", "low"),
            manual_record_attr(diffusion_record, "notes", "Not treated as measured unless availability is measured."),
        )
        add_provenance(
            provenance,
            "diffusion_coefficient",
            manual_path.name,
            "fields.diffusion_coefficient",
            diffusion_value,
            fields["diffusion_coefficient"]["confidence"],
            fields["diffusion_coefficient"]["notes"],
        )

    derive_nominal_transport(fields, provenance, manual_path)


def derive_nominal_transport(fields, provenance, source_file):
    flow_rate = fields["flow_rate"]["value"]
    width = fields["flow_domain_width_m"]["value"]
    depth = fields["channel_depth_m"]["value"]
    if flow_rate is not None and width not in (None, 0) and depth not in (None, 0):
        nominal_velocity = float(flow_rate) / (float(width) * float(depth))
        fields["nominal_velocity_m_s"] = field_record(
            "nominal_velocity_m_s",
            nominal_velocity,
            "derived",
            "derived:flow_rate/(flow_domain_width_m*channel_depth_m)",
            "medium",
            "Nominal flow-domain velocity for global comparison, not local pore-throat velocity.",
        )
        fields["velocity"] = field_record(
            "velocity",
            nominal_velocity,
            "derived",
            "alias:nominal_velocity_m_s",
            "medium",
            "Alias of nominal_velocity_m_s for dimensionless-number readiness.",
        )
        add_provenance(
            provenance,
            "nominal_velocity_m_s",
            source_file.name if source_file else "",
            "derived:flow_rate/(flow_domain_width_m*channel_depth_m)",
            nominal_velocity,
            "medium",
            fields["nominal_velocity_m_s"]["notes"],
        )
        add_provenance(
            provenance,
            "velocity",
            source_file.name if source_file else "",
            "alias:nominal_velocity_m_s",
            nominal_velocity,
            "medium",
            fields["velocity"]["notes"],
        )

    velocity = fields["velocity"]["value"]
    viscosity = fields["viscosity"]["value"]
    sigma = fields["interfacial_tension"]["value"]
    if velocity is not None and viscosity is not None and sigma not in (None, 0):
        ca = float(viscosity) * float(velocity) / float(sigma)
        fields["capillary_number_nominal"] = field_record(
            "capillary_number_nominal",
            ca,
            "derived",
            "derived:viscosity*nominal_velocity_m_s/interfacial_tension",
            "medium",
            "Nominal Ca based on flow-domain W_domain and H from the peer-review draft.",
        )
        fields["log10_capillary_number_nominal"] = field_record(
            "log10_capillary_number_nominal",
            float(np.log10(ca)) if ca > 0 else None,
            "derived",
            "derived:log10(capillary_number_nominal)",
            "medium",
            "Nominal log10(Ca) for comparison with the peer-review draft.",
        )
        add_provenance(
            provenance,
            "capillary_number_nominal",
            source_file.name if source_file else "",
            "derived:viscosity*nominal_velocity_m_s/interfacial_tension",
            ca,
            "medium",
            fields["capillary_number_nominal"]["notes"],
        )
        add_provenance(
            provenance,
            "log10_capillary_number_nominal",
            source_file.name if source_file else "",
            "derived:log10(capillary_number_nominal)",
            fields["log10_capillary_number_nominal"]["value"],
            "medium",
            fields["log10_capillary_number_nominal"]["notes"],
        )


def make_output_dir(postprocess_dir, output_dir=None, overwrite=False):
    postprocess_dir = Path(postprocess_dir)
    if not postprocess_dir.exists():
        raise FileNotFoundError(f"postprocess directory does not exist: {postprocess_dir}")
    if output_dir:
        path = Path(output_dir)
        if not path.is_absolute():
            path = postprocess_dir / path
        if path.exists() and any(path.iterdir()) and not overwrite:
            raise FileExistsError(f"metadata recovery output directory already exists and is not empty: {path}")
        if not path.exists():
            if not path.parent.exists():
                raise FileNotFoundError(f"metadata recovery output parent does not exist: {path.parent}")
            path.mkdir()
        return path
    path = postprocess_dir / f"metadata_recovery_{timestamp()}"
    path.mkdir()
    return path


def add_provenance(provenance, key, source_file, source_detail, value, confidence, notes=""):
    provenance.append(
        {
            "field": key,
            "source_file": source_file,
            "source_detail": source_detail,
            "value": value,
            "confidence": confidence,
            "notes": notes,
        }
    )


def recover_fields(output_root, postprocess_dir, manual_metadata_json=None):
    output_root = Path(output_root)
    report_path = output_root / "analysis_report.txt"
    report_values = parse_analysis_report(report_path)
    saturation_path, saturation_values = read_latest_saturation(output_root)
    timeline_path, timeline_values = read_latest_timeline(output_root)
    audit_path = find_latest_audit_csv(output_root)
    audit_rows = read_audit_rows(audit_path)
    manual_path = find_manual_metadata_json(output_root, postprocess_dir, manual_metadata_json)
    manual_fields = read_manual_metadata(manual_path) if manual_path else {}

    fields = {name: field_record(name) for name in FIELD_ORDER}
    provenance = []

    for key in ["pixel_size_um", "chip_geometric_volume_m3", "pore_volume_m3"]:
        if key in report_values:
            fields[key] = field_record(key, report_values[key], "measured", "analysis_report.txt", "high")
            add_provenance(provenance, key, "analysis_report.txt", str(report_path), report_values[key], "high")

    for key in ["chip_geometric_volume_m3", "pore_volume_m3", "pore_area_px"]:
        if key in saturation_values and fields[key]["availability"] == "unavailable":
            source = saturation_path.name if saturation_path else ""
            fields[key] = field_record(key, saturation_values[key], "measured", source, "high")
            add_provenance(provenance, key, source, str(saturation_path), saturation_values[key], "high")
        elif key == "pore_area_px" and key in saturation_values:
            source = saturation_path.name if saturation_path else ""
            fields[key] = field_record(key, saturation_values[key], "measured", source, "high")
            add_provenance(provenance, key, source, str(saturation_path), saturation_values[key], "high")

    if fields["pixel_size_um"]["value"] is not None:
        pixel_size_m = float(fields["pixel_size_um"]["value"]) * 1e-6
        fields["pixel_size_m"] = field_record(
            "pixel_size_m",
            pixel_size_m,
            "derived",
            "derived:pixel_size_um*1e-6",
            "high",
        )
        add_provenance(provenance, "pixel_size_m", "analysis_report.txt", "derived:pixel_size_um*1e-6", pixel_size_m, "high")

    pixel_size_m = fields["pixel_size_m"]["value"]
    pore_volume = fields["pore_volume_m3"]["value"]
    pore_area_px = fields["pore_area_px"]["value"]
    if pixel_size_m is not None and pore_volume is not None and pore_area_px not in (None, 0):
        channel_depth = float(pore_volume) / (float(pore_area_px) * float(pixel_size_m) ** 2)
        fields["channel_depth_m"] = field_record(
            "channel_depth_m",
            channel_depth,
            "derived",
            "derived:pore_volume_m3/(pore_area_px*pixel_size_m^2)",
            "medium",
        )
        add_provenance(
            provenance,
            "channel_depth_m",
            saturation_path.name if saturation_path else "",
            "derived:pore_volume_m3/(pore_area_px*pixel_size_m^2)",
            channel_depth,
            "medium",
        )

    if timeline_values.get("available"):
        source = timeline_path.name if timeline_path else ""
        fields["frame_time_available"] = field_record("frame_time_available", True, "measured", source, "high")
        fields["real_time_available"] = field_record(
            "real_time_available",
            bool(timeline_values.get("real_time_available", False)),
            "measured",
            source,
            "high",
        )
        fields["frame_count"] = field_record("frame_count", timeline_values.get("frame_count"), "measured", source, "high")
        add_provenance(provenance, "frame_time_available", source, str(timeline_path), True, "high")
        if "frame_interval_s" in timeline_values:
            fields["frame_interval_s"] = field_record(
                "frame_interval_s",
                timeline_values["frame_interval_s"],
                "measured",
                source,
                "high",
            )
            add_provenance(provenance, "frame_interval_s", source, str(timeline_path), timeline_values["frame_interval_s"], "high")
    else:
        fields["frame_time_available"] = field_record("frame_time_available", False, "unavailable", "", "none")
        fields["real_time_available"] = field_record("real_time_available", False, "unavailable", "", "none")

    found_tween, concentration = parse_treatment_from_folder(output_root)
    if found_tween:
        fields["surfactant_type"] = field_record(
            "surfactant_type",
            "Tween 80",
            "inferred",
            "folder_name",
            "medium",
            "Inferred from output-root folder name.",
        )
        add_provenance(provenance, "surfactant_type", "folder_name", str(output_root), "Tween 80", "medium")
    if concentration:
        fields["surfactant_concentration"] = field_record(
            "surfactant_concentration",
            concentration,
            "inferred",
            "folder_name",
            "medium",
            "Concentration unit is unknown; percent-like token inferred from folder name.",
        )
        fields["surfactant_concentration"]["display_value"] = f"{concentration:g}%"
        fields["surfactant_concentration_unit"] = field_record(
            "surfactant_concentration_unit",
            "percent_unknown_basis",
            "inferred",
            "folder_name",
            "medium",
            "Folder name contains a percent token, but mass/volume basis is unknown.",
        )
        add_provenance(provenance, "surfactant_concentration", "folder_name", str(output_root), concentration, "medium")
        add_provenance(
            provenance,
            "surfactant_concentration_unit",
            "folder_name",
            str(output_root),
            "percent_unknown_basis",
            "medium",
        )

    for name in TRANSPORT_FIELDS:
        fields[name] = field_record(name, None, "unavailable", "", "none", "Required transport/fluid property metadata was not found.")

    diffusion_candidate = next((row for row in audit_rows if row["metadata_key"] == "diffusion_coefficient" and row["found"]), None)
    if diffusion_candidate is not None:
        fields["diffusion_coefficient"] = field_record(
            "diffusion_coefficient",
            first_number(diffusion_candidate["value_preview"]),
            "candidate_default",
            "experiment_metadata_audit.csv",
            "low",
            "Audit indicates a possible config/default candidate; not treated as measured.",
        )

    for row in audit_rows:
        add_provenance(
            provenance,
            row["metadata_key"],
            "experiment_metadata_audit.csv",
            row["source_file"],
            row["value_preview"],
            "low" if row["found"] else "none",
            f"Audit found={row['found']}; required_for={row['required_for']}",
        )

    apply_manual_metadata(fields, provenance, manual_fields, manual_path) if manual_path else None

    inputs = {
        "output_root": str(output_root),
        "postprocess_dir": str(postprocess_dir),
        "analysis_report": str(report_path) if report_path.exists() else "",
        "saturation_csv": str(saturation_path) if saturation_path else "",
        "frame_timeline_csv": str(timeline_path) if timeline_path else "",
        "metadata_audit_csv": str(audit_path) if audit_path else "",
        "manual_metadata_json": str(manual_path) if manual_path else "",
    }
    return fields, provenance, inputs


def build_readiness(fields):
    pixel_ready = fields["pixel_size_m"]["value"] is not None
    time_ready = bool(fields["frame_time_available"]["value"])
    treatment_partial = fields["surfactant_type"]["value"] is not None or fields["surfactant_concentration"]["value"] is not None
    concentration_basis_ready = fields["surfactant_concentration_basis"]["value"] is not None
    flow_ready = fields["flow_rate"]["value"] is not None
    velocity_ready = fields["velocity"]["value"] is not None
    fluid_for_ca_ready = fields["viscosity"]["value"] is not None and fields["interfacial_tension"]["value"] is not None
    ca_ready = velocity_ready and fluid_for_ca_ready
    ca_partial = (flow_ready or velocity_ready) and fluid_for_ca_ready
    pe_ready = velocity_ready and fields["diffusion_coefficient"]["availability"] == "measured"
    sh_ready = pe_ready
    base_rows = [
        {
            "readiness_key": "physical_length_area",
            "metric": "physical_length_area",
            "ready": bool(pixel_ready),
            "status": "ready" if pixel_ready else "not_ready",
            "missing": "" if pixel_ready else "pixel_size_m",
            "reason": "pixel_size_m recovered" if pixel_ready else "pixel_size_m unavailable",
        },
        {
            "readiness_key": "sn_rate_per_time",
            "metric": "sn_rate_per_time",
            "ready": bool(time_ready),
            "status": "ready" if time_ready else "not_ready",
            "missing": "" if time_ready else "frame time",
            "reason": "frame_timeline provides real/frame time" if time_ready else "frame_timeline_*.csv unavailable or lacks time columns",
        },
        {
            "readiness_key": "treatment_comparison",
            "metric": "treatment_comparison",
            "ready": False,
            "status": "partial" if treatment_partial else "not_ready",
            "missing": (
                "multi-folder treatment table or replicate design"
                if treatment_partial and concentration_basis_ready
                else "measured concentration basis"
                if treatment_partial
                else "surfactant metadata"
            ),
            "reason": (
                "surfactant metadata is available for this folder, but comparison requires matched treatment groups"
                if treatment_partial and concentration_basis_ready
                else "surfactant inferred from folder name"
                if treatment_partial
                else "surfactant metadata unavailable"
            ),
        },
        {
            "readiness_key": "capillary_number",
            "metric": "capillary_number",
            "ready": bool(ca_ready),
            "status": "ready" if ca_ready else "partial" if ca_partial else "not_ready",
            "missing": "" if ca_ready else "velocity or flow-to-velocity geometry" if ca_partial else "flow or velocity; viscosity; interfacial tension",
            "reason": "requires velocity, viscosity, and interfacial tension; pump rate alone needs a geometry conversion to velocity",
        },
        {
            "readiness_key": "peclet_number",
            "metric": "peclet_number",
            "ready": bool(pe_ready),
            "status": "ready" if pe_ready else "not_ready",
            "missing": "" if pe_ready else "flow or velocity; measured diffusion coefficient",
            "reason": "requires flow/velocity and a measured diffusion coefficient",
        },
        {
            "readiness_key": "sherwood_proxy",
            "metric": "sherwood_proxy",
            "ready": bool(sh_ready),
            "status": "ready" if sh_ready else "not_ready",
            "missing": "" if sh_ready else "transport properties; measured diffusion coefficient",
            "reason": "requires transport properties and a measured diffusion coefficient",
        },
        {
            "readiness_key": "sherwood_number",
            "metric": "sherwood_number",
            "ready": bool(sh_ready),
            "status": "ready" if sh_ready else "not_ready",
            "missing": "" if sh_ready else "transport properties; measured diffusion coefficient",
            "reason": "requires transport properties and a measured diffusion coefficient",
        },
    ]
    return base_rows


def fields_to_dataframe(fields):
    rows = []
    for key in FIELD_ORDER:
        record = fields[key].copy()
        record["field"] = record.pop("key")
        rows.append(record)
    return pd.DataFrame(rows, columns=["field", "value", "unit", "availability", "source", "confidence", "notes"])


def write_markdown_report(path, fields, readiness_rows, inputs):
    ready = {row["metric"]: row["status"] for row in readiness_rows}
    lines = [
        "# Experiment Metadata Recovery",
        "",
        "## Inputs",
        "",
        f"- output_root: `{inputs['output_root']}`",
        f"- postprocess_dir: `{inputs['postprocess_dir']}`",
        f"- analysis_report: `{inputs['analysis_report']}`",
        f"- saturation_csv: `{inputs['saturation_csv']}`",
        f"- frame_timeline_csv: `{inputs['frame_timeline_csv']}`",
        f"- metadata_audit_csv: `{inputs['metadata_audit_csv']}`",
        f"- manual_metadata_json: `{inputs.get('manual_metadata_json', '')}`",
        "",
        "## Key Recovered Fields",
        "",
        f"- pixel_size_um: {fields['pixel_size_um']['value']} ({fields['pixel_size_um']['availability']})",
        f"- pixel_size_m: {fields['pixel_size_m']['value']} ({fields['pixel_size_m']['availability']})",
        f"- pore_volume_m3: {fields['pore_volume_m3']['value']} ({fields['pore_volume_m3']['availability']})",
        f"- channel_depth_m: {fields['channel_depth_m']['value']} ({fields['channel_depth_m']['availability']})",
        f"- flow_domain_width_m: {fields['flow_domain_width_m']['value']} ({fields['flow_domain_width_m']['availability']})",
        f"- surfactant_type: {fields['surfactant_type']['value']} ({fields['surfactant_type']['availability']})",
        f"- surfactant_concentration: {fields['surfactant_concentration']['value']} ({fields['surfactant_concentration']['availability']})",
        f"- surfactant_concentration_basis: {fields['surfactant_concentration_basis']['value']} ({fields['surfactant_concentration_basis']['availability']})",
        f"- active_displacement_fluid: {fields['active_displacement_fluid']['value']} ({fields['active_displacement_fluid']['availability']})",
        f"- active_flow_rate_ul_min: {fields['active_flow_rate_ul_min']['value']} ({fields['active_flow_rate_ul_min']['availability']})",
        f"- residual_formation_displacement_fluid: {fields['residual_formation_displacement_fluid']['value']} ({fields['residual_formation_displacement_fluid']['availability']})",
        f"- residual_formation_flow_rate_ul_min: {fields['residual_formation_flow_rate_ul_min']['value']} ({fields['residual_formation_flow_rate_ul_min']['availability']})",
        f"- pump_rate_ul_min: {fields['pump_rate_ul_min']['value']} ({fields['pump_rate_ul_min']['availability']})",
        f"- flow_rate: {fields['flow_rate']['value']} ({fields['flow_rate']['availability']})",
        f"- nominal_velocity_m_s: {fields['nominal_velocity_m_s']['value']} ({fields['nominal_velocity_m_s']['availability']})",
        f"- displacing_phase_viscosity: {fields['displacing_phase_viscosity']['value']} ({fields['displacing_phase_viscosity']['availability']})",
        f"- napl_viscosity: {fields['napl_viscosity']['value']} ({fields['napl_viscosity']['availability']})",
        f"- interfacial_tension: {fields['interfacial_tension']['value']} ({fields['interfacial_tension']['availability']})",
        f"- capillary_number_nominal: {fields['capillary_number_nominal']['value']} ({fields['capillary_number_nominal']['availability']})",
        f"- log10_capillary_number_nominal: {fields['log10_capillary_number_nominal']['value']} ({fields['log10_capillary_number_nominal']['availability']})",
        f"- diffusion_coefficient: {fields['diffusion_coefficient']['value']} ({fields['diffusion_coefficient']['availability']})",
        "",
        "## Readiness",
        "",
    ]
    for metric, status in ready.items():
        lines.append(f"- {metric}: {status}")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Flow rate and pump rate are experiment-folder specific and must not be reused across folders.",
            "- Diffusion coefficients from config/audit/manual defaults are not treated as measured unless explicitly marked measured.",
        ]
    )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_recovery(args):
    output_root = Path(args.output_root)
    if not output_root.exists():
        raise FileNotFoundError(f"output root does not exist: {output_root}")
    postprocess_dir = Path(args.postprocess_dir)
    output_dir = make_output_dir(postprocess_dir, args.output_dir, overwrite=args.overwrite)

    fields, provenance, inputs = recover_fields(output_root, postprocess_dir, args.manual_metadata_json)
    payload = {
        "output_root": str(output_root),
        "postprocess_dir": str(postprocess_dir),
        "output_dir": str(output_dir),
        "inputs": inputs,
        "fields": {key: fields[key] for key in FIELD_ORDER},
        "readiness": build_readiness(fields),
    }
    readiness_rows = payload["readiness"]

    write_json(output_dir / "experiment_metadata_recovered.json", payload)
    fields_to_dataframe(fields).to_csv(output_dir / "experiment_metadata_recovered.csv", index=False)
    pd.DataFrame(provenance, columns=["field", "source_file", "source_detail", "value", "confidence", "notes"]).to_csv(
        output_dir / "metadata_provenance.csv",
        index=False,
    )
    pd.DataFrame(readiness_rows).to_csv(output_dir / "physical_unit_readiness.csv", index=False)
    write_markdown_report(output_dir / "metadata_recovery_report.md", fields, readiness_rows, inputs)
    return output_dir


def build_parser():
    parser = argparse.ArgumentParser(description="Recover experiment metadata from existing postprocess outputs.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--postprocess-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--manual-metadata-json", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    output_dir = run_recovery(args)
    print(f"Metadata recovery directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
