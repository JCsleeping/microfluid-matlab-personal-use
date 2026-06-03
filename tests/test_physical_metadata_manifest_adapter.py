import json
import math
from pathlib import Path

from tools.analysis_package.physical_metadata_manifest import (
    build_physical_metadata_manifest,
)
from run_dnapl_branch_c_timeseries_tool import build_paths, write_physical_metadata_input


def test_adapter_converts_recovered_metadata_units_and_processing_scale() -> None:
    recovered = {
        "fields": {
            "pixel_size_um": {
                "value": 4.1,
                "availability": "measured",
                "source": "analysis_report.txt",
                "confidence": "high",
            },
            "pore_volume_m3": {
                "value": 5.1522e-10,
                "availability": "measured",
                "source": "saturation_csv",
                "confidence": "high",
            },
            "channel_depth_m": {
                "value": 2.0e-5,
                "availability": "derived",
                "source": "derived:pore_volume_m3/(pore_area_px*pixel_size_m^2)",
                "confidence": "high",
            },
            "flow_domain_width_m": {
                "value": 5.9e-3,
                "availability": "manual",
                "source": "manual_metadata",
                "confidence": "medium",
            },
            "active_flow_rate_ul_min": {
                "value": 4.0,
                "availability": "manual",
                "source": "manual_metadata",
                "confidence": "high",
            },
            "viscosity": {
                "value": 0.001,
                "availability": "manual",
                "source": "fluid_table",
                "confidence": "medium",
            },
            "interfacial_tension": {
                "value": 0.0382,
                "availability": "manual",
                "source": "fluid_table",
                "confidence": "medium",
            },
            "temperature": {
                "value": 25.0,
                "availability": "manual",
                "source": "manual_metadata",
                "confidence": "high",
            },
            "diffusion_coefficient": {
                "value": 4.3e-10,
                "availability": "literature_default",
                "source": "literature_estimate",
                "confidence": "low",
            },
        }
    }

    manifest = build_physical_metadata_manifest(
        recovered,
        processing_scale_factor=3,
        trusted=True,
        source_path=Path("recovered_metadata.json"),
    )

    assert manifest["trusted"] is True
    assert manifest["metadata_status"] == "calibrated"
    assert manifest["processing_scale_factor"] == 3
    assert manifest["pixel_size_um"] == 4.1
    assert manifest["native_pixel_size_um"] == 4.1
    assert math.isclose(manifest["processing_pixel_size_um"], 4.1 / 3)
    assert math.isclose(manifest["pore_volume_ul"], 0.51522)
    assert manifest["channel_depth_um"] == 20.0
    assert manifest["channel_width_um"] == 5900.0
    assert manifest["flow_rate_ul_min"] == 4.0
    assert manifest["viscosity_Pa_s"] == 0.001
    assert math.isclose(manifest["IFT_mN_m"], 38.2)
    assert manifest["temperature_C"] == 25.0
    assert manifest["diffusion_coefficient_m2_s"] == 4.3e-10
    assert manifest["field_provenance"]["pore_volume_ul"]["source_key"] == "pore_volume_m3"


def test_runner_writes_physical_manifest_from_recovered_metadata(tmp_path: Path) -> None:
    recovered_path = tmp_path / "recovered_metadata.json"
    recovered_path.write_text(
        json.dumps(
            {
                "fields": {
                    "pixel_size_um": {"value": 4.1, "confidence": "high"},
                    "pore_volume_m3": {"value": 5.1522e-10, "confidence": "high"},
                }
            }
        ),
        encoding="utf-8",
    )
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
            "analysis_dir": None,
        },
    )()
    config = {
        "run_name": "demo",
        "run_suffix": "full3585",
        "mode": "full",
        "output_root": str(tmp_path),
        "physical_metadata_recovery": {
            "path": str(recovered_path),
            "trusted": True,
            "processing_scale_factor": 3,
        },
    }

    paths = build_paths(args, config)
    metadata_path = write_physical_metadata_input(config, paths)

    assert metadata_path == tmp_path / "run_configs" / "demo_full3585_physical_metadata.json"
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved["trusted"] is True
    assert saved["processing_scale_factor"] == 3
    assert saved["pixel_size_um"] == 4.1
    assert math.isclose(saved["processing_pixel_size_um"], 4.1 / 3)
    assert math.isclose(saved["pore_volume_ul"], 0.51522)


def test_runner_recovery_overrides_provenance_only_inline_template(tmp_path: Path) -> None:
    recovered_path = tmp_path / "recovered_metadata.json"
    recovered_path.write_text(
        json.dumps({"fields": {"pixel_size_um": {"value": 4.1}}}),
        encoding="utf-8",
    )
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
            "analysis_dir": None,
        },
    )()
    config = {
        "run_name": "demo",
        "run_suffix": "full3585",
        "mode": "full",
        "output_root": str(tmp_path),
        "physical_metadata": {
            "trusted": False,
            "processing_scale_factor": 3,
            "pixel_size_um": None,
        },
        "physical_metadata_recovery": {
            "path": str(recovered_path),
            "trusted": True,
            "processing_scale_factor": 3,
        },
    }

    paths = build_paths(args, config)
    metadata_path = write_physical_metadata_input(config, paths)
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert saved["trusted"] is True
    assert saved["pixel_size_um"] == 4.1
