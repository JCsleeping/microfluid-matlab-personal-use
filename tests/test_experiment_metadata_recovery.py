import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VIS = ROOT / "visualization"


def load_module(name, filename):
    path = VIS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metadata = load_module("recover_experiment_metadata", "recover_experiment_metadata.py")


class ExperimentMetadataRecoveryTests(unittest.TestCase):
    def test_recovers_report_values_and_infers_channel_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            write_saturation(output_root)
            write_timeline(output_root)

            out_dir = post_dir / "metadata_recovery_test"
            exit_code = metadata.main(
                [
                    "--output-root",
                    str(output_root),
                    "--postprocess-dir",
                    str(post_dir),
                    "--output-dir",
                    str(out_dir),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))
            fields = payload["fields"]
            self.assertAlmostEqual(fields["pixel_size_um"]["value"], 4.10)
            self.assertAlmostEqual(fields["pixel_size_m"]["value"], 4.10e-6)
            self.assertAlmostEqual(fields["chip_geometric_volume_m3"]["value"], 6.4108e-10, places=14)
            self.assertAlmostEqual(fields["pore_volume_m3"]["value"], 5.1522e-10, places=14)
            self.assertAlmostEqual(fields["channel_depth_m"]["value"], 2.0e-5, delta=1.0e-7)

            provenance = pd.read_csv(out_dir / "metadata_provenance.csv")
            self.assertIn("analysis_report.txt", " ".join(provenance["source_file"].astype(str)))

    def test_infers_surfactant_from_folder_name_with_medium_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp, folder_name="18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE")
            write_analysis_report(output_root)
            write_timeline(output_root)

            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            fields = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))["fields"]
            self.assertEqual(fields["surfactant_type"]["value"], "Tween 80")
            self.assertEqual(fields["surfactant_type"]["confidence"], "medium")
            self.assertEqual(fields["surfactant_concentration"]["value"], 5.0)
            self.assertEqual(fields["surfactant_concentration_unit"]["value"], "percent_unknown_basis")

    def test_infers_surfactant_concentration_from_grandparent_experiment_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            experiment = Path(tmp) / "18 1-BO 4UL 5% TWEEM 80 4UL WATER DISPLACE"
            output_root = experiment / "01 Tween 80" / "output_20260429_225936"
            post_dir = output_root / "postprocess_residual_structure_test"
            post_dir.mkdir(parents=True)
            write_analysis_report(output_root)
            write_timeline(output_root)

            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            fields = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))["fields"]
            self.assertEqual(fields["surfactant_type"]["value"], "Tween 80")
            self.assertEqual(fields["surfactant_concentration"]["value"], 5.0)

    def test_missing_transport_metadata_marks_dimensionless_numbers_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            write_timeline(output_root)

            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            readiness = pd.read_csv(out_dir / "physical_unit_readiness.csv")
            ca = readiness.loc[readiness["readiness_key"] == "capillary_number"].iloc[0]
            pe = readiness.loc[readiness["readiness_key"] == "peclet_number"].iloc[0]
            sh = readiness.loc[readiness["readiness_key"] == "sherwood_proxy"].iloc[0]
            self.assertFalse(bool(ca["ready"]))
            self.assertFalse(bool(pe["ready"]))
            self.assertFalse(bool(sh["ready"]))
            self.assertIn("flow", ca["missing"].lower())

    def test_audit_missing_fields_do_not_block_report_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            write_timeline(output_root)
            audit_dir = output_root / "audit_blob_morphology_gap_20260101_000000"
            audit_dir.mkdir()
            pd.DataFrame(
                {
                    "metadata_key": ["pixel_size_um"],
                    "found": [0],
                    "source_file": [""],
                    "value_preview": [""],
                    "unit": ["um/px"],
                    "required_for": ["physical area"],
                    "missing_impact": ["audit missed this"],
                }
            ).to_csv(audit_dir / "experiment_metadata_audit.csv", index=False)

            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            fields = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))["fields"]
            self.assertAlmostEqual(fields["pixel_size_um"]["value"], 4.10)
            self.assertEqual(fields["pixel_size_um"]["confidence"], "high")

    def test_refuses_nonempty_explicit_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            out_dir = post_dir / "metadata_recovery_test"
            out_dir.mkdir()
            (out_dir / "old.txt").write_text("old", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "already exists and is not empty"):
                metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

    def test_relative_output_dir_resolves_under_postprocess_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            cwd = Path.cwd()
            os.chdir(tmp)
            try:
                metadata.main(
                    [
                        "--output-root",
                        str(output_root),
                        "--postprocess-dir",
                        str(post_dir),
                        "--output-dir",
                        "metadata_relative",
                    ]
                )
            finally:
                os.chdir(cwd)

            self.assertTrue((post_dir / "metadata_relative" / "experiment_metadata_recovered.json").exists())
            self.assertFalse((Path(tmp) / "metadata_relative").exists())

    def test_manual_metadata_json_overrides_transport_and_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            write_timeline(output_root)
            manual = post_dir / "experiment_metadata_manual.json"
            manual.write_text(
                json.dumps(
                    {
                        "fields": {
                            "active_displacement_fluid": {"value": "Tween 80 solution", "source": "manual", "confidence": "high"},
                            "active_flow_rate_ul_min": {"value": 4.0, "source": "manual", "confidence": "high"},
                            "residual_formation_displacement_fluid": {"value": "water", "source": "manual", "confidence": "high"},
                            "residual_formation_flow_rate_ul_min": {"value": 4.0, "source": "manual", "confidence": "high"},
                            "surfactant_concentration_basis": {"value": "w/w", "source": "manual", "confidence": "high"},
                            "viscosity_mpa_s": {"value": 1.40, "source": "peer_review_table", "confidence": "medium"},
                            "interfacial_tension_mn_m": {"value": 38.2, "source": "peer_review_table", "confidence": "medium"},
                            "temperature_c": {"value": 25, "source": "manual", "confidence": "high"},
                            "diffusion_coefficient": {
                                "value": 4.3e-10,
                                "availability": "literature_default",
                                "source": "literature_estimate",
                                "confidence": "low",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            payload = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))
            fields = payload["fields"]
            self.assertEqual(fields["active_displacement_fluid"]["value"], "Tween 80 solution")
            self.assertEqual(fields["active_flow_rate_ul_min"]["value"], 4.0)
            self.assertEqual(fields["residual_formation_displacement_fluid"]["value"], "water")
            self.assertEqual(fields["residual_formation_flow_rate_ul_min"]["value"], 4.0)
            self.assertEqual(fields["pump_rate_ul_min"]["value"], 4.0)
            self.assertAlmostEqual(fields["flow_rate"]["value"], 4.0e-9 / 60.0)
            self.assertEqual(fields["surfactant_concentration_basis"]["value"], "w/w")
            self.assertAlmostEqual(fields["viscosity"]["value"], 0.00140)
            self.assertAlmostEqual(fields["interfacial_tension"]["value"], 0.0382)
            self.assertEqual(fields["temperature"]["value"], 25)
            self.assertEqual(fields["diffusion_coefficient"]["availability"], "literature_default")

            readiness = pd.read_csv(out_dir / "physical_unit_readiness.csv")
            ca = readiness.loc[readiness["readiness_key"] == "capillary_number"].iloc[0]
            pe = readiness.loc[readiness["readiness_key"] == "peclet_number"].iloc[0]
            self.assertFalse(bool(ca["ready"]))
            self.assertEqual(ca["status"], "partial")
            self.assertFalse(bool(pe["ready"]))

    def test_manual_nominal_geometry_derives_velocity_and_capillary_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root, post_dir = make_fixture(tmp)
            write_analysis_report(output_root)
            write_timeline(output_root)
            manual = post_dir / "experiment_metadata_manual.json"
            manual.write_text(
                json.dumps(
                    {
                        "fields": {
                            "active_flow_rate_ul_min": {"value": 4.0, "source": "manual", "confidence": "high"},
                            "flow_domain_width_um": {"value": 5900.0, "source": "peer_review_draft", "confidence": "medium"},
                            "channel_depth_um": {"value": 20.0, "source": "peer_review_draft", "confidence": "medium"},
                            "displacing_phase_viscosity_mpa_s": {"value": 1.00, "source": "peer_review_draft", "confidence": "medium"},
                            "interfacial_tension_mn_m": {"value": 38.2, "source": "peer_review_draft", "confidence": "medium"},
                            "diffusion_coefficient": {
                                "value": 4.3e-10,
                                "availability": "literature_default",
                                "source": "literature_default",
                                "confidence": "low",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            out_dir = post_dir / "metadata_recovery_test"
            metadata.main(["--output-root", str(output_root), "--postprocess-dir", str(post_dir), "--output-dir", str(out_dir)])

            fields = json.loads((out_dir / "experiment_metadata_recovered.json").read_text(encoding="utf-8"))["fields"]
            expected_velocity = (4.0e-9 / 60.0) / (5900.0e-6 * 20.0e-6)
            expected_ca = 0.001 * expected_velocity / 0.0382
            self.assertAlmostEqual(fields["flow_domain_width_m"]["value"], 5900.0e-6)
            self.assertAlmostEqual(fields["channel_depth_m"]["value"], 20.0e-6)
            self.assertAlmostEqual(fields["nominal_velocity_m_s"]["value"], expected_velocity)
            self.assertAlmostEqual(fields["capillary_number_nominal"]["value"], expected_ca)
            self.assertAlmostEqual(fields["log10_capillary_number_nominal"]["value"], -4.83, places=2)

            readiness = pd.read_csv(out_dir / "physical_unit_readiness.csv")
            ca = readiness.loc[readiness["readiness_key"] == "capillary_number"].iloc[0]
            pe = readiness.loc[readiness["readiness_key"] == "peclet_number"].iloc[0]
            self.assertTrue(bool(ca["ready"]))
            self.assertEqual(ca["status"], "ready")
            self.assertFalse(bool(pe["ready"]))


def make_fixture(tmp, folder_name="18 1-BO 4UL 5% TWEEN 80 4UL WATER DISPLACE"):
    root = Path(tmp) / folder_name
    output_root = root / "output_20260429_225936"
    post_dir = output_root / "postprocess_residual_structure_test"
    post_dir.mkdir(parents=True)
    return output_root, post_dir


def write_analysis_report(output_root):
    text = """
==========================================================
  DNAPL ANALYSIS REPORT
==========================================================
  Pixel Size:                              4.10 um/px  (4.10e-06 m/px)
  Chip Geometric Volume:                   6.4108e-10 m^3
  Flow Domain Pore Volume:                 5.1522e-10 m^3
  Duration:                                5123 s (85.4 min)
"""
    (output_root / "analysis_report.txt").write_text(text, encoding="utf-8")


def write_saturation(output_root):
    pd.DataFrame(
        {
            "Sn": [0.296492610927365],
            "Sw": [0.703507389072635],
            "DNAPL_area_px": [454766],
            "Pore_area_px": [1533819],
            "Chip_volume_m3": [6.41078927203065e-10],
            "Pore_volume_m3": [5.15217635018107e-10],
            "DNAPL_volume_m3": [1.52758221802341e-10],
        }
    ).to_csv(output_root / "saturation_20260430_015512.csv", index=False)


def write_timeline(output_root):
    pd.DataFrame(
        {
            "GlobalFrame": [1, 2],
            "RealTime_s": [0, 3],
            "TifFile": ["raw.tif", "raw.tif"],
            "PageInTif": [1, 2],
            "Interval_s": [3, 3],
        }
    ).to_csv(output_root / "frame_timeline_mock.csv", index=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
