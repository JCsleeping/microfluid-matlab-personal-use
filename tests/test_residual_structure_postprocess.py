import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VIS = ROOT / "visualization"


def load_module(name, filename):
    path = VIS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


architecture = load_module("analyze_architecture_vs_time", "analyze_architecture_vs_time.py")
blob_population = load_module("analyze_blob_population_morphology", "analyze_blob_population_morphology.py")
rate_correlations = load_module("plot_rate_correlations", "plot_rate_correlations.py")
orchestrator = load_module("run_residual_structure_postprocess", "run_residual_structure_postprocess.py")


def write_timeseries(path, realtime=True):
    df = pd.DataFrame(
        {
            "Time": [0, 1, 2, 3, 4],
            "Sn": [0.30, 0.27, 0.22, 0.14, 0.04],
            "NumBlobs": [5, 30, 35, 20, 4],
            "MeanBlobSize": [10, 9, 8, 7, 6],
            "InterfaceArea": [100, 120, 130, 90, 30],
            "MaxBlobFrac": [0.70, 0.20, 0.25, 0.40, 0.90],
            "ReqMedian": [8.0, 7.0, 6.0, 4.0, 2.0],
            "ReqMean": [10.0, 9.0, 8.0, 6.0, 3.0],
            "ReqStd": [1.0, 1.1, 1.2, 1.3, 1.4],
            "MeanCircularity": [0.8, 0.75, 0.7, 0.65, 0.6],
            "a_i_2D": [2.0e4, 8.0e4, 8.5e4, 4.0e4, 1.0e4],
            "nDroplets": [1, 10, 12, 8, 1],
            "nColumns": [1, 8, 8, 6, 1],
            "nClusters": [3, 12, 15, 6, 2],
            "fracDroplets": [0.2, 0.3, 0.35, 0.4, 0.25],
            "fracColumns": [0.2, 0.2, 0.2, 0.3, 0.25],
            "fracClusters": [0.6, 0.5, 0.45, 0.3, 0.5],
            "MassDissolvedKg": [0, 1, 2, 3, 4],
        }
    )
    if realtime:
        df["RealTime_s"] = [0, 60, 120, 180, 240]
        df["Interval_s"] = [60, 60, 60, 60, 60]
    df.to_csv(path, index=False)
    return df


def write_blob_csv(path):
    df = pd.DataFrame(
        {
            "FrameIndex": [1, 1, 1, 2, 2, 2, 3, 3],
            "FrameTime": [0, 0, 0, 1, 1, 1, 2, 2],
            "BlobID": [1, 2, 3, 1, 2, 3, 1, 2],
            "Area": [10, 30, 60, 20, 40, 80, 50, 150],
            "Perimeter": [10, 20, 30, 15, 25, 35, 22, 44],
            "Circularity": [0.8, 0.9, 1.1, 0.7, 0.6, 0.5, 0.4, 0.3],
            "AspectRatio": [1.0, 2.0, 4.0, 1.5, 2.5, 3.5, 2.0, 6.0],
            "Solidity": [0.5, 0.8, 1.0, 0.7, 0.8, 0.9, 0.6, 0.95],
            "EquivRadius": [1.0, 2.0, 4.0, 1.5, 2.5, 4.5, 3.0, 6.0],
            "EulerNumber": [1, 1, 0, 1, 0, -1, 1, 0],
            "Centroid_X": [1, 2, 3, 2, 3, 4, 3, 4],
            "Centroid_Y": [1, 2, 3, 2, 3, 4, 3, 4],
            "GangliaType": ["droplet", "column", "cluster", "droplet", "column", "cluster", "cluster", "cluster"],
            "TopologyType": ["droplet", "column", "cluster", "droplet", "column", "cluster", "cluster", "cluster"],
        }
    )
    df.to_csv(path, index=False)
    return df


class ResidualPostprocessTests(unittest.TestCase):
    def test_architecture_scoring_matches_matlab_thresholds(self):
        row = pd.Series({"MaxBlobFrac": 0.70, "NumBlobs": 5, "a_i_2D": 2.0e4})
        scored = architecture.classify_architecture_row(row)
        self.assertEqual(scored["ArchitectureType"], "pool-like")
        self.assertEqual(scored["PoolScore"], 3)
        self.assertEqual(scored["GangliaScore"], 0)

        row = pd.Series({"MaxBlobFrac": 0.20, "NumBlobs": 80, "a_i_2D": 8.0e4})
        scored = architecture.classify_architecture_row(row)
        self.assertEqual(scored["ArchitectureType"], "ganglia-rich")
        self.assertEqual(scored["PoolScore"], 0)
        self.assertEqual(scored["GangliaScore"], 3)

    def test_realtime_timeseries_is_selected_before_plain_timeseries(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            plain = output_root / "timeseries_older.csv"
            realtime = output_root / "timeseries_realtime_newer.csv"
            write_timeseries(plain, realtime=False)
            write_timeseries(realtime, realtime=True)
            self.assertEqual(orchestrator.find_timeseries_csv(output_root), realtime)

    def test_chunked_blob_population_renames_circularity2d_and_separates_topology_fractions(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob_csv = Path(tmp) / "blob_detail_all_frames.csv"
            write_blob_csv(blob_csv)
            frame_summary, topology, slopes = blob_population.analyze_blob_population(
                blob_csv,
                chunksize=2,
                min_slope_points=2,
            )

            self.assertIn("Circularity2D_area_weighted_mean", frame_summary.columns)
            self.assertNotIn("Roundness_mean", frame_summary.columns)

            row = topology.loc[topology["FrameIndex"] == 2].iloc[0]
            self.assertAlmostEqual(row["countFracClusters"], 1.0 / 3.0)
            self.assertAlmostEqual(row["areaFracClusters"], 80.0 / 140.0)

            slope_row = slopes.loc[slopes["FrameIndex"] == 1].iloc[0]
            self.assertLess(slope_row["Slope_logN_gt_Req_vs_logReq"], 0)
            self.assertEqual(slope_row["FractalProxyOnly"], True)

    def test_dissolution_rate_uses_realtime_seconds(self):
        df = pd.DataFrame({"RealTime_s": [0, 60, 120], "Sn": [0.30, 0.24, 0.18]})
        enriched = rate_correlations.compute_dissolution_rates(df)
        np.testing.assert_allclose(enriched["DissolutionRate_Sn_per_min"], [0.06, 0.06, 0.06])
        np.testing.assert_allclose(enriched["RemovalFraction"], [0.0, 0.2, 0.4])

    def test_dissolution_rate_monotone_smoothing_suppresses_negative_jitter_rate(self):
        df = pd.DataFrame({"RealTime_s": [0, 60, 120, 180], "Sn": [1.0, 0.90, 0.95, 0.80]})
        enriched = rate_correlations.compute_dissolution_rates(df, rate_window_min=2.0, rate_min_points=2)
        self.assertTrue((enriched["DissolutionRate_Sn_per_min"].dropna() >= -1e-12).all())
        self.assertIn("SnMonotone", enriched.columns)
        np.testing.assert_allclose(enriched["SnMonotone"], [1.0, 0.90, 0.90, 0.80])

    def test_blob_population_rejects_noncontiguous_frame_order_for_streaming(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob_detail_all_frames.csv"
            df = write_blob_csv(path)
            df = pd.concat([df[df["FrameIndex"] == 1], df[df["FrameIndex"] == 2], df[df["FrameIndex"] == 1]])
            df.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "not grouped by FrameIndex"):
                blob_population.analyze_blob_population(path, chunksize=3, min_slope_points=2)

    def test_explicit_nonempty_postprocess_dir_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            write_timeseries(output_root / "timeseries_realtime_20260101_000001.csv", realtime=True)
            write_blob_csv(output_root / "blob_detail_all_frames.csv")
            post_dir = output_root / "postprocess_residual_structure_existing"
            post_dir.mkdir()
            (post_dir / "old.csv").write_text("do not replace", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "already exists and is not empty"):
                orchestrator.main(
                    [
                        "--output-root",
                        str(output_root),
                        "--postprocess-dir",
                        str(post_dir),
                    ]
                )

    def test_orchestrator_writes_postprocess_outputs_without_touching_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            write_timeseries(output_root / "timeseries_20260101_000000.csv", realtime=False)
            timeseries = output_root / "timeseries_realtime_20260101_000001.csv"
            blob_csv = output_root / "blob_detail_all_frames.csv"
            audit_dir = output_root / "audit_blob_morphology_gap_20260101_000000"
            audit_dir.mkdir()
            write_timeseries(timeseries, realtime=True)
            write_blob_csv(blob_csv)
            (audit_dir / "audit_summary.json").write_text(
                json.dumps(
                    {
                        "overall_status": "WARN_GEOMETRY_INCOMPLETE",
                        "tracking_feasibility": "LOW_CONFIDENCE_TRACKING",
                    }
                ),
                encoding="utf-8",
            )

            before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in (timeseries, blob_csv)}
            post_dir = output_root / "postprocess_residual_structure_test"
            exit_code = orchestrator.main(
                [
                    "--output-root",
                    str(output_root),
                    "--postprocess-dir",
                    str(post_dir),
                    "--chunksize",
                    "2",
                    "--dpi",
                    "80",
                    "--overwrite",
                ]
            )
            after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in (timeseries, blob_csv)}

            self.assertEqual(exit_code, 0)
            self.assertEqual(before, after)
            for name in [
                "architecture_vs_time.csv",
                "architecture_transitions.csv",
                "architecture_rate_summary.csv",
                "blob_population_morphology_by_frame.csv",
                "topology_population_by_frame.csv",
                "size_distribution_slope_vs_time.csv",
                "dissolution_rates.csv",
                "rate_metric_associations.csv",
                "rate_metric_binned_summary.csv",
                "postprocess_summary.json",
                "input_file_inventory.csv",
            ]:
                self.assertTrue((post_dir / name).exists(), name)

            summary = json.loads((post_dir / "postprocess_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["analysis_level"], "Level A")
            self.assertEqual(summary["not_computed"]["tracking_metrics"], "requires tracking")
            self.assertEqual(summary["not_computed"]["boundary_metrics"], "requires mask/boundary or raw-frame rerun")
            qc = pd.read_csv(post_dir / "qc_workbooks" / "level_a_output_inventory.csv")
            summary_qc = qc.loc[qc["file_type"] == "postprocess_summary.json"].iloc[0]
            self.assertEqual(bool(summary_qc["exists"]), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
