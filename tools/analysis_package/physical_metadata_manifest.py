"""Convert recovered experiment metadata into Branch C physical metadata."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


TRUSTED_STATUSES = {
    "trusted",
    "calibrated",
    "validated",
    "physical_metadata_validated",
}


@dataclass(frozen=True)
class RecoveredValue:
    value: object
    source_key: str
    availability: str = ""
    source: str = ""
    confidence: str = ""
    notes: str = ""


def load_recovered_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing recovered metadata JSON: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Recovered metadata must be a JSON object: {path}")
    return payload


def _payload_root(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("physical_metadata"), dict):
        return payload["physical_metadata"]
    return payload


def _fields(payload: dict[str, Any]) -> dict[str, Any]:
    root = _payload_root(payload)
    fields = root.get("fields")
    return fields if isinstance(fields, dict) else root


def _record(payload: dict[str, Any], key: str) -> RecoveredValue | None:
    fields = _fields(payload)
    if key not in fields:
        return None
    raw = fields[key]
    if isinstance(raw, dict):
        return RecoveredValue(
            value=raw.get("value"),
            source_key=key,
            availability=str(raw.get("availability", "")),
            source=str(raw.get("source", "")),
            confidence=str(raw.get("confidence", "")),
            notes=str(raw.get("notes", "")),
        )
    return RecoveredValue(value=raw, source_key=key)


def _as_float(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _positive(value: object) -> float:
    result = _as_float(value)
    return result if math.isfinite(result) and result > 0 else math.nan


def _identity(value: float) -> float:
    return value


def _mul(factor: float) -> Callable[[float], float]:
    return lambda value: value * factor


def _pick_numeric(
    payload: dict[str, Any],
    candidates: list[tuple[str, Callable[[float], float]]],
) -> tuple[float, RecoveredValue | None, str]:
    for key, converter in candidates:
        rec = _record(payload, key)
        if rec is None:
            continue
        value = _positive(rec.value)
        if math.isfinite(value):
            return converter(value), rec, key
    return math.nan, None, ""


def _pick_text(payload: dict[str, Any], candidates: list[str]) -> tuple[str, RecoveredValue | None, str]:
    for key in candidates:
        rec = _record(payload, key)
        if rec is None or rec.value is None:
            continue
        text = str(rec.value).strip()
        if text:
            return text, rec, key
    return "", None, ""


def _add_provenance(
    provenance: dict[str, dict[str, str]],
    output_key: str,
    rec: RecoveredValue | None,
    source_key: str,
    conversion: str,
) -> None:
    if rec is None:
        return
    provenance[output_key] = {
        "source_key": source_key,
        "source": rec.source,
        "availability": rec.availability,
        "confidence": rec.confidence,
        "conversion": conversion,
        "notes": rec.notes,
    }


def _infer_trusted(payload: dict[str, Any], trusted: bool | None) -> bool:
    if trusted is not None:
        return bool(trusted)
    root = _payload_root(payload)
    status = str(root.get("metadata_status", root.get("status", ""))).strip().lower()
    return bool(root.get("trusted", False)) or status in TRUSTED_STATUSES


def build_physical_metadata_manifest(
    recovered_metadata: dict[str, Any],
    *,
    processing_scale_factor: float | int | None = None,
    trusted: bool | None = None,
    metadata_status: str | None = None,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build the manifest consumed by build_branch_c_analysis_package.py."""

    if not isinstance(recovered_metadata, dict):
        raise ValueError("Recovered metadata must be a JSON object.")

    provenance: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "adapter": "tools.analysis_package.physical_metadata_manifest",
        "source": {
            "type": "recovered_experiment_metadata",
            "path": str(source_path) if source_path is not None else "",
        },
    }

    is_trusted = _infer_trusted(recovered_metadata, trusted)
    manifest["trusted"] = is_trusted
    manifest["metadata_status"] = (
        metadata_status if metadata_status else ("calibrated" if is_trusted else "provided_untrusted")
    )

    scale = _positive(processing_scale_factor)
    if not math.isfinite(scale):
        scale, rec, source_key = _pick_numeric(
            recovered_metadata,
            [
                ("processing_scale_factor", _identity),
                ("upscale_factor", _identity),
            ],
        )
        _add_provenance(provenance, "processing_scale_factor", rec, source_key, "identity")
    if math.isfinite(scale):
        manifest["processing_scale_factor"] = scale
        if abs(scale - round(scale)) > 1.0e-9:
            warnings.append("processing_scale_factor should be an integer processing-grid scale.")

    numeric_specs: dict[str, tuple[list[tuple[str, Callable[[float], float]]], str]] = {
        "pixel_size_um": (
            [
                ("pixel_size_um", _identity),
                ("native_pixel_size_um", _identity),
                ("pixel_size_m", _mul(1.0e6)),
                ("native_pixel_size_m", _mul(1.0e6)),
            ],
            "native pixel size in um/px",
        ),
        "processing_pixel_size_um": (
            [
                ("processing_pixel_size_um", _identity),
                ("processing_pixel_size_m", _mul(1.0e6)),
            ],
            "processing-grid pixel size in um/px",
        ),
        "pore_volume_ul": (
            [
                ("pore_volume_ul", _identity),
                ("pore_volume_m3", _mul(1.0e9)),
                ("flow_domain_pore_volume_m3", _mul(1.0e9)),
            ],
            "pore volume converted to uL",
        ),
        "channel_depth_um": (
            [
                ("channel_depth_um", _identity),
                ("channel_depth_m", _mul(1.0e6)),
                ("depth_m", _mul(1.0e6)),
            ],
            "channel depth converted to um",
        ),
        "channel_width_um": (
            [
                ("channel_width_um", _identity),
                ("flow_domain_width_um", _identity),
                ("channel_width_m", _mul(1.0e6)),
                ("flow_domain_width_m", _mul(1.0e6)),
            ],
            "flow-domain/channel width converted to um",
        ),
        "flow_rate_ul_min": (
            [
                ("flow_rate_ul_min", _identity),
                ("active_flow_rate_ul_min", _identity),
                ("pump_rate_ul_min", _identity),
                ("flow_rate", _mul(60.0e9)),
                ("flow_rate_m3_s", _mul(60.0e9)),
            ],
            "flow rate converted to uL/min",
        ),
        "viscosity_Pa_s": (
            [
                ("viscosity_Pa_s", _identity),
                ("viscosity_pa_s", _identity),
                ("viscosity", _identity),
                ("displacing_phase_viscosity", _identity),
                ("displacing_phase_viscosity_pa_s", _identity),
                ("viscosity_mpa_s", _mul(1.0e-3)),
                ("displacing_phase_viscosity_mpa_s", _mul(1.0e-3)),
                ("water_viscosity_mpa_s", _mul(1.0e-3)),
            ],
            "viscosity converted to Pa*s",
        ),
        "IFT_mN_m": (
            [
                ("IFT_mN_m", _identity),
                ("interfacial_tension_mn_m", _identity),
                ("interfacial_tension", _mul(1.0e3)),
                ("interfacial_tension_n_m", _mul(1.0e3)),
            ],
            "interfacial tension converted to mN/m",
        ),
        "temperature_C": (
            [
                ("temperature_C", _identity),
                ("temperature_c", _identity),
                ("temperature", _identity),
            ],
            "temperature in C",
        ),
        "diffusion_coefficient_m2_s": (
            [
                ("diffusion_coefficient_m2_s", _identity),
                ("diffusion_coefficient", _identity),
                ("diffusion_coeff", _identity),
            ],
            "diffusion coefficient in m^2/s",
        ),
    }

    for output_key, (candidates, conversion_note) in numeric_specs.items():
        value, rec, source_key = _pick_numeric(recovered_metadata, candidates)
        if math.isfinite(value):
            manifest[output_key] = value
            _add_provenance(provenance, output_key, rec, source_key, conversion_note)

    if "pixel_size_um" in manifest:
        manifest["native_pixel_size_um"] = manifest["pixel_size_um"]
        provenance.setdefault(
            "native_pixel_size_um",
            {
                "source_key": "pixel_size_um",
                "source": "adapter",
                "availability": "derived",
                "confidence": "",
                "conversion": "alias:pixel_size_um",
                "notes": "",
            },
        )
    if (
        "processing_pixel_size_um" not in manifest
        and "pixel_size_um" in manifest
        and math.isfinite(scale)
    ):
        manifest["processing_pixel_size_um"] = manifest["pixel_size_um"] / scale
        provenance["processing_pixel_size_um"] = {
            "source_key": "pixel_size_um",
            "source": "adapter",
            "availability": "derived",
            "confidence": "",
            "conversion": "pixel_size_um/processing_scale_factor",
            "notes": "",
        }
    if (
        "pixel_size_um" not in manifest
        and "processing_pixel_size_um" in manifest
        and math.isfinite(scale)
    ):
        manifest["pixel_size_um"] = manifest["processing_pixel_size_um"] * scale
        manifest["native_pixel_size_um"] = manifest["pixel_size_um"]
        provenance["pixel_size_um"] = {
            "source_key": "processing_pixel_size_um",
            "source": "adapter",
            "availability": "derived",
            "confidence": "",
            "conversion": "processing_pixel_size_um*processing_scale_factor",
            "notes": "",
        }

    strings: dict[str, str] = {}
    for output_key, candidates in {
        "surfactant_name": ["surfactant_name", "surfactant_type"],
        "surfactant_concentration": ["surfactant_concentration"],
        "surfactant_concentration_unit": ["surfactant_concentration_unit"],
        "surfactant_concentration_basis": ["surfactant_concentration_basis"],
        "notes": ["notes"],
    }.items():
        text, rec, source_key = _pick_text(recovered_metadata, candidates)
        if text:
            strings[output_key] = text
            _add_provenance(provenance, output_key, rec, source_key, "text")
    manifest.update(strings)

    manifest["field_provenance"] = provenance
    manifest["warnings"] = warnings
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert recovered experiment metadata into Branch C physical_metadata.json."
    )
    parser.add_argument("--recovered-metadata", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--processing-scale-factor", type=float, default=None)
    parser.add_argument("--trusted", action="store_true")
    parser.add_argument("--metadata-status", default=None)
    args = parser.parse_args()

    recovered = load_recovered_metadata(args.recovered_metadata)
    manifest = build_physical_metadata_manifest(
        recovered,
        processing_scale_factor=args.processing_scale_factor,
        trusted=True if args.trusted else None,
        metadata_status=args.metadata_status,
        source_path=args.recovered_metadata,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"PHYSICAL_METADATA_MANIFEST {args.out}")


if __name__ == "__main__":
    main()
