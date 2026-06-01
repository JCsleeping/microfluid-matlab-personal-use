import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "visualization" / "build_blob_morphology_data_product.py"
SPEC = importlib.util.spec_from_file_location("build_blob_morphology_data_product", MODULE_PATH)
blob_product = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blob_product)


def sidecar_like_rows():
    return pd.DataFrame(
        {
            "FrameIndex": [1, 1, 2],
            "RealTime_s": [0.0, 0.5, 1.0],
            "BlobID_sidecar": [101, 102, 201],
            "Area_px": [100.0, 400.0, 900.0],
            "MajorAxisLength_px": [20.0, 40.0, 0.0],
            "MinorAxisLength_px": [10.0, 20.0, 15.0],
            "ConvexArea_px": [125.0, 500.0, 0.0],
            "Solidity_geometry": [0.8, 0.8, np.nan],
            "Eccentricity": [0.5, 0.6, 0.7],
            "Extent": [0.7, 0.8, 0.9],
            "P_outer_boundary": [40.0, 0.0, 120.0],
            "Pc_outer_boundary": [36.0, 30.0, 0.0],
            "P_total_boundary": [60.0, 80.0, 180.0],
            "ProjectedRoughness_boundary": [1.1, 1.2, 1.3],
            "Circularity2D_boundary": [0.785, 1.1, 0.8],
            "AreaTier": ["tiny", "medium", "large"],
            "BoundaryAvailable": [True, True, True],
            "BoundaryMetricValid": [False, True, True],
            "RoughnessLessThanOne": [False, False, False],
            "CircularityGreaterThan1p05": [False, True, False],
            "TouchesImageBorder": [False, False, True],
            "GeometryQCFlag": ["small", "circularity_gt_1p05", "border"],
        }
    )


class BlobMorphologyDataProductTests(unittest.TestCase):
    def test_sidecar_native_columns_are_normalized_and_derived(self):
        normalized = blob_product.normalize_sidecar_columns(sidecar_like_rows())

        expected_columns = {
            "BlobID",
            "EquivDiameter_px",
            "EquivRadius_px",
            "ProjectedSphericity2D",
            "AspectRatio01",
            "AxisAspectRatio",
            "Solidity2D",
            "ProjectedConvexityPerimeter",
            "PtotalOverPouter",
            "ProjectedRegularity2D",
            "ReliabilityClass",
            "ShapeClass",
            "ShapeClassReason",
            "ShapeValid",
            "ShapeInvalidReason",
        }
        self.assertTrue(expected_columns.issubset(set(normalized.columns)))
        self.assertEqual(list(normalized["BlobID"]), [101, 102, 201])

        row = normalized.loc[normalized["BlobID"] == 101].iloc[0]
        self.assertAlmostEqual(row["EquivRadius_px"], np.sqrt(100.0 / np.pi))
        self.assertAlmostEqual(row["EquivDiameter_px"], 2.0 * np.sqrt(100.0 / np.pi))
        self.assertAlmostEqual(row["ProjectedSphericity2D"], 2.0 * np.sqrt(np.pi * 100.0) / 40.0)
        self.assertAlmostEqual(row["AspectRatio01"], 0.5)
        self.assertAlmostEqual(row["AxisAspectRatio"], 2.0)
        self.assertAlmostEqual(row["Solidity2D"], 0.8)
        self.assertAlmostEqual(row["ProjectedConvexityPerimeter"], 0.9)
        self.assertAlmostEqual(row["PtotalOverPouter"], 1.5)
        self.assertAlmostEqual(
            row["ProjectedRegularity2D"],
            np.nanmean([row["ProjectedSphericity2D"], row["AspectRatio01"], row["Solidity2D"]]),
        )

        zero_perimeter = normalized.loc[normalized["BlobID"] == 102].iloc[0]
        self.assertTrue(np.isnan(zero_perimeter["ProjectedSphericity2D"]))
        self.assertTrue(np.isnan(zero_perimeter["ProjectedConvexityPerimeter"]))
        self.assertTrue(np.isnan(zero_perimeter["PtotalOverPouter"]))

        zero_axis = normalized.loc[normalized["BlobID"] == 201].iloc[0]
        self.assertTrue(np.isnan(zero_axis["AspectRatio01"]))
        self.assertTrue(np.isnan(zero_axis["Solidity2D"]))

    def test_reliability_and_shape_class_rules_are_ordered(self):
        rows = pd.DataFrame(
            {
                "BlobID_sidecar": [1, 2, 3, 4, 5, 6, 7, 8],
                "Area_px": [249.0, 300.0, 300.0, 600.0, 700.0, 700.0, 700.0, 700.0],
                "MajorAxisLength_px": [20.0, 20.0, 20.0, 25.0, 80.0, 35.0, 35.0, 40.0],
                "MinorAxisLength_px": [10.0, 10.0, 10.0, 22.0, 10.0, 28.0, 10.0, 25.0],
                "ConvexArea_px": [300.0, 360.0, 360.0, 630.0, 760.0, 1200.0, 1400.0, 760.0],
                "Solidity_geometry": [0.8, 0.8, 0.8, 0.95, 0.92, 0.58, 0.50, 0.92],
                "P_outer_boundary": [60.0, 60.0, 60.0, 65.0, 180.0, 130.0, 250.0, 95.0],
                "Pc_outer_boundary": [55.0, 55.0, 55.0, 63.0, 170.0, 95.0, 140.0, 80.0],
                "P_total_boundary": [80.0, 80.0, 80.0, 70.0, 200.0, 180.0, 380.0, 120.0],
                "ProjectedRoughness_boundary": [1.1, 1.1, 1.1, 1.03, 1.08, 1.45, 1.9, 0.9],
                "Circularity2D_boundary": [0.8, 0.8, 0.8, 0.99, 0.72, 0.55, 0.38, 1.1],
                "AreaTier": ["small", "medium", "medium", "large", "large", "large", "large", "large"],
                "BoundaryMetricValid": [True, False, True, True, True, True, True, True],
                "RoughnessLessThanOne": [False, False, False, False, False, False, False, True],
                "CircularityGreaterThan1p05": [False, False, False, False, False, False, False, True],
            }
        )
        normalized = blob_product.normalize_sidecar_columns(rows)
        thresholds = {
            "ProjectedSphericity2D": {"q25": 0.35, "q50": 0.5, "q75": 0.8, "q90": 0.9},
            "AspectRatio01": {"q25": 0.25, "q50": 0.5, "q75": 0.8, "q90": 0.9},
            "AxisAspectRatio": {"q25": 1.1, "q50": 1.7, "q75": 2.5, "q90": 4.0},
            "Solidity2D": {"q25": 0.65, "q50": 0.8, "q75": 0.9, "q90": 0.95},
            "ProjectedRoughness_boundary": {"q25": 1.0, "q50": 1.1, "q75": 1.3, "q90": 1.6},
            "PtotalOverPouter": {"q25": 1.0, "q50": 1.2, "q75": 1.5, "q90": 1.8},
        }

        classified = blob_product.assign_shape_class(normalized, thresholds)
        classes = dict(zip(classified["BlobID"], classified["ShapeClass"]))
        reliability = dict(zip(classified["BlobID"], classified["ReliabilityClass"]))
        valid = dict(zip(classified["BlobID"], classified["ShapeValid"]))
        reasons = dict(zip(classified["BlobID"], classified["ShapeInvalidReason"]))

        self.assertEqual(reliability[1], "count_only_small")
        self.assertEqual(classes[1], "small_unclassified")
        self.assertEqual(classes[2], "boundary_invalid")
        self.assertEqual(reliability[3], "geometry_valid")
        self.assertEqual(classes[3], "medium_caution")
        self.assertEqual(reliability[4], "high_confidence")
        self.assertEqual(classes[4], "compact_round")
        self.assertEqual(classes[5], "elongated")
        self.assertEqual(classes[6], "concave_lobed")
        self.assertEqual(classes[7], "branched_complex")
        self.assertEqual(classes[8], "compact_irregular")
        self.assertFalse(bool(valid[8]))
        self.assertIn("roughness_lt_1", reasons[8])
        self.assertIn("circularity_gt_1p05", reasons[8])

        tiny_or_small_classes = set(classified.loc[classified["Area_px"] < 250, "ShapeClass"])
        self.assertEqual(tiny_or_small_classes, {"small_unclassified"})

    def test_compute_shape_thresholds_filters_reference_population_deterministically(self):
        rows = pd.DataFrame(
            {
                "Area_px": [100.0, 250.0, 500.0, 1000.0, 2000.0],
                "BoundaryMetricValid": [True, True, True, False, True],
                "ProjectedSphericity2D": [99.0, 0.2, 0.4, 88.0, 0.8],
                "AspectRatio01": [99.0, 0.3, 0.5, 88.0, 0.9],
                "AxisAspectRatio": [99.0, 1.1, 2.0, 88.0, 4.0],
                "Solidity2D": [99.0, 0.6, 0.8, 88.0, 0.95],
                "ProjectedRoughness_boundary": [99.0, 1.0, 1.2, 88.0, 1.8],
                "PtotalOverPouter": [99.0, 1.1, 1.4, 88.0, 2.0],
            }
        )

        first = blob_product.compute_shape_thresholds(rows)
        second = blob_product.compute_shape_thresholds(rows.sample(frac=1.0, random_state=3))

        self.assertEqual(first, second)
        for metric in [
            "ProjectedSphericity2D",
            "AspectRatio01",
            "AxisAspectRatio",
            "Solidity2D",
            "ProjectedRoughness_boundary",
            "PtotalOverPouter",
        ]:
            self.assertEqual(set(first[metric]), {"q25", "q50", "q75", "q90"})

        self.assertAlmostEqual(first["ProjectedSphericity2D"]["q50"], 0.4)
        self.assertLess(first["ProjectedSphericity2D"]["q90"], 1.0)
        self.assertGreater(first["ProjectedSphericity2D"]["q25"], 0.0)

    def test_shape_class_precedence_keeps_earlier_matching_class(self):
        rows = pd.DataFrame(
            {
                "BlobID_sidecar": [10, 11],
                "Area_px": [400.0, 700.0],
                "MajorAxisLength_px": [30.0, 80.0],
                "MinorAxisLength_px": [27.0, 10.0],
                "ConvexArea_px": [420.0, 760.0],
                "Solidity_geometry": [0.95, 0.92],
                "P_outer_boundary": [72.0, 160.0],
                "Pc_outer_boundary": [70.0, 100.0],
                "P_total_boundary": [75.0, 230.0],
                "ProjectedRoughness_boundary": [1.02, 1.7],
                "Circularity2D_boundary": [0.97, 0.72],
                "AreaTier": ["medium", "large"],
                "BoundaryMetricValid": [True, True],
                "RoughnessLessThanOne": [False, False],
                "CircularityGreaterThan1p05": [False, False],
            }
        )
        thresholds = {
            "ProjectedSphericity2D": {"q25": 0.3, "q50": 0.5, "q75": 0.7, "q90": 0.9},
            "AspectRatio01": {"q25": 0.2, "q50": 0.5, "q75": 0.8, "q90": 0.9},
            "AxisAspectRatio": {"q25": 1.1, "q50": 1.5, "q75": 2.0, "q90": 4.0},
            "Solidity2D": {"q25": 0.65, "q50": 0.8, "q75": 0.9, "q90": 0.95},
            "ProjectedRoughness_boundary": {"q25": 1.0, "q50": 1.1, "q75": 1.3, "q90": 1.6},
            "PtotalOverPouter": {"q25": 1.0, "q50": 1.2, "q75": 1.4, "q90": 1.8},
        }

        classified = blob_product.assign_shape_class(
            blob_product.normalize_sidecar_columns(rows),
            thresholds,
        )
        classes = dict(zip(classified["BlobID"], classified["ShapeClass"]))

        self.assertEqual(classes[10], "medium_caution")
        self.assertEqual(classes[11], "elongated")

    def test_missing_or_non_numeric_area_is_invalid_and_not_reliable(self):
        rows = pd.DataFrame(
            {
                "BlobID_sidecar": [20, 21],
                "Area_px": [np.nan, "not_numeric"],
                "MajorAxisLength_px": [30.0, 30.0],
                "MinorAxisLength_px": [20.0, 20.0],
                "ConvexArea_px": [500.0, 500.0],
                "P_outer_boundary": [80.0, 80.0],
                "Pc_outer_boundary": [70.0, 70.0],
                "P_total_boundary": [90.0, 90.0],
                "BoundaryMetricValid": [True, True],
                "RoughnessLessThanOne": [False, False],
                "CircularityGreaterThan1p05": [False, False],
            }
        )

        classified = blob_product.assign_shape_class(blob_product.normalize_sidecar_columns(rows), {})

        self.assertTrue((classified["ReliabilityClass"] == "boundary_invalid").all())
        self.assertTrue((classified["ShapeClass"] == "boundary_invalid").all())
        self.assertTrue((classified["ShapeValid"] == False).all())
        for reason in classified["ShapeInvalidReason"]:
            self.assertIn("area_missing_or_invalid", reason)

    def test_threshold_values_loaded_as_strings_are_coerced_or_defaulted(self):
        rows = pd.DataFrame(
            {
                "BlobID_sidecar": [30],
                "Area_px": [700.0],
                "MajorAxisLength_px": [25.0],
                "MinorAxisLength_px": [23.0],
                "ConvexArea_px": [735.0],
                "P_outer_boundary": [66.0],
                "Pc_outer_boundary": [64.0],
                "P_total_boundary": [70.0],
                "ProjectedRoughness_boundary": [1.05],
                "BoundaryMetricValid": [True],
                "RoughnessLessThanOne": [False],
                "CircularityGreaterThan1p05": [False],
            }
        )
        thresholds = {
            "ProjectedSphericity2D": {"q75": "0.7"},
            "AspectRatio01": {"q75": "0.8"},
            "AxisAspectRatio": {"q75": "2.0", "q90": "not_numeric"},
            "Solidity2D": {"q25": "0.65", "q75": "0.9"},
            "ProjectedRoughness_boundary": {"q75": "1.3", "q90": "1.6"},
            "PtotalOverPouter": {"q75": "1.4"},
        }

        classified = blob_product.assign_shape_class(
            blob_product.normalize_sidecar_columns(rows),
            thresholds,
        )

        self.assertEqual(classified.loc[0, "ShapeClass"], "compact_round")

    def test_validate_sidecar_inputs_parses_long_form_qc_and_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_dir = make_synthetic_sidecar(Path(tmp), include_blob_rows=True)

            validated = blob_product.validate_sidecar_inputs(sidecar_dir)

            self.assertEqual(validated.qc_metrics["OverallStatus"], "PASS")
            self.assertEqual(validated.qc_metrics["ProcessedFrames"], 3)
            self.assertEqual(validated.qc_metrics["GeometryBlobRows"], 6)
            self.assertIn("geometry_by_blob", validated.paths)

    def test_validate_sidecar_inputs_reports_missing_required_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_dir = make_synthetic_sidecar(Path(tmp), include_blob_rows=True)
            (sidecar_dir / "geometry_provenance.json").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "geometry_provenance.json"):
                blob_product.validate_sidecar_inputs(sidecar_dir)

    def test_validate_sidecar_inputs_reports_failed_qc_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_dir = make_synthetic_sidecar(Path(tmp), include_blob_rows=True)
            pd.DataFrame(
                [
                    ("OverallStatus", "FAIL"),
                    ("ProcessedFrames", 3),
                    ("GeometryBlobRows", 6),
                    ("BlobCountPassFrames", 3),
                    ("TotalAreaPassFrames", 3),
                    ("MaxConsecutiveMismatchFrames", 0),
                    ("EmptyGeometryFrames", 0),
                    ("BlockedForInterpretation", "false"),
                ],
                columns=["Metric", "Value"],
            ).to_csv(sidecar_dir / "geometry_qc_summary.csv", index=False)

            with self.assertRaisesRegex(ValueError, "OverallStatus"):
                blob_product.validate_sidecar_inputs(sidecar_dir)

    def test_output_dir_guard_refuses_non_empty_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "existing_output"
            output_dir.mkdir()
            (output_dir / "keep.txt").write_text("do not overwrite", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "overwrite"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=2,
                    overwrite=False,
                )

    def test_dry_run_validates_and_reports_planned_outputs_without_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_dir = make_synthetic_sidecar(Path(tmp), include_blob_rows=False)

            plan = blob_product.build_blob_morphology_data_product(
                sidecar_dir,
                output_dir=Path(tmp) / "planned",
                chunksize=2,
                dry_run=True,
            )

            self.assertTrue(plan["dry_run"])
            self.assertEqual(plan["row_counts"]["GeometryBlobRows"], 6)
            self.assertIn("blob_morphology_by_blob.csv", plan["planned_outputs"])
            self.assertFalse((Path(tmp) / "planned").exists())

    def test_chunksize_must_be_positive_before_output_dir_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "existing_output"
            output_dir.mkdir()
            (output_dir / "keep.txt").write_text("do not overwrite", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "chunksize"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=0,
                    overwrite=True,
                )

            self.assertEqual((output_dir / "keep.txt").read_text(encoding="utf-8"), "do not overwrite")

    def test_overwrite_refuses_non_product_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "analysis_directory"
            output_dir.mkdir()
            (output_dir / "keep.txt").write_text("do not overwrite", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "non-product"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=2,
                    overwrite=True,
                )

            self.assertEqual((output_dir / "keep.txt").read_text(encoding="utf-8"), "do not overwrite")

    def test_first_pass_acceptance_gates_fail_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"
            rewrite_qc_metric(sidecar_dir, "GeometryBlobRows", 7)

            with self.assertRaisesRegex(ValueError, "GeometryBlobRows"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=2,
                )

            self.assertFalse(output_dir.exists())

    def test_first_pass_acceptance_gates_require_contiguous_frame_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"
            rows = pd.read_csv(sidecar_dir / "geometry_by_blob.csv")
            rows.loc[rows["FrameIndex"] == 3, "FrameIndex"] = 4
            rows.to_csv(sidecar_dir / "geometry_by_blob.csv", index=False)

            with self.assertRaisesRegex(ValueError, "FrameIndex"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=2,
                )

            self.assertFalse(output_dir.exists())

    def test_first_pass_acceptance_gates_check_boundary_valid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"
            rewrite_qc_metric(sidecar_dir, "BoundaryMetricValidRows", 4)

            with self.assertRaisesRegex(ValueError, "BoundaryMetricValidRows"):
                blob_product.build_blob_morphology_data_product(
                    sidecar_dir,
                    output_dir=output_dir,
                    chunksize=2,
                )

            self.assertFalse(output_dir.exists())

    def test_split_frame_chunks_use_true_frame_medians_counts_and_scalars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"
            make_split_frame_blob_rows(sidecar_dir)

            blob_product.build_blob_morphology_data_product(
                sidecar_dir,
                output_dir=output_dir,
                chunksize=3,
            )

            by_frame = pd.read_csv(output_dir / "blob_morphology_by_frame.csv")
            frame2 = by_frame.loc[by_frame["FrameIndex"] == 2].iloc[0]
            self.assertEqual(frame2["BlobCount"], 3)
            self.assertAlmostEqual(frame2["AreaSum_px"], 1310.0)
            self.assertAlmostEqual(frame2["AreaMedian_px"], 300.0)
            self.assertAlmostEqual(frame2["Area_px_p10"], 68.0)
            self.assertAlmostEqual(frame2["Area_px_p90"], 860.0)
            self.assertAlmostEqual(frame2["Amax_Atotal"], 1000.0 / 1310.0)
            self.assertAlmostEqual(frame2["A_top3_Atotal"], 1.0)
            self.assertAlmostEqual(frame2["BoundaryMetricValidAreaFraction"], 1300.0 / 1310.0)
            self.assertAlmostEqual(frame2["HighConfidenceAreaFraction"], 1000.0 / 1310.0)
            self.assertEqual(frame2["BorderTouchingCount"], 1)

            by_blob = pd.read_csv(output_dir / "blob_morphology_by_blob.csv")
            frame2_blob = by_blob.loc[(by_blob["FrameIndex"] == 2) & (by_blob["BlobID"] == 203)].iloc[0]
            self.assertAlmostEqual(frame2_blob["A_blob_Atotal"], 1000.0 / 1310.0)

            reliability = pd.read_csv(output_dir / "blob_reliability_summary_by_frame.csv")
            rel2 = reliability.loc[reliability["FrameIndex"] == 2].iloc[0]
            self.assertEqual(rel2["HighConfidenceCount"], 1)
            self.assertEqual(rel2["GeometryValidCount"], 1)
            self.assertEqual(rel2["CountOnlySmallCount"], 1)
            self.assertEqual(rel2["BoundaryInvalidCount"], 0)
            self.assertNotIn("high_confidence_count", reliability.columns)

    def test_all_ineligible_representatives_still_write_stable_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"
            make_all_ineligible_blob_rows(sidecar_dir)

            blob_product.build_blob_morphology_data_product(
                sidecar_dir,
                output_dir=output_dir,
                chunksize=2,
            )

            representatives = pd.read_csv(output_dir / "representative_blob_candidates.csv")
            self.assertTrue(set(blob_product.REPRESENTATIVE_CANDIDATE_COLUMNS).issubset(representatives.columns))
            if not representatives.empty:
                self.assertEqual(set(representatives["ExemplarType"]), {"qc_exclusion_example"})

    def test_chunked_builder_writes_expected_outputs_and_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sidecar_dir = make_synthetic_sidecar(root / "sidecar", include_blob_rows=True)
            output_dir = root / "morphology"

            result = blob_product.build_blob_morphology_data_product(
                sidecar_dir,
                output_dir=output_dir,
                chunksize=2,
            )

            expected_files = set(blob_product.OUTPUT_FILENAMES)
            self.assertEqual(expected_files, {p.name for p in output_dir.iterdir()})
            self.assertEqual(result["row_counts"]["blob_rows"], 6)

            by_blob = pd.read_csv(output_dir / "blob_morphology_by_blob.csv")
            self.assertEqual(len(by_blob), 6)
            for column in [
                "ProjectedSphericity2D",
                "Circularity2D_boundary",
                "AspectRatio01",
                "AxisAspectRatio",
                "Solidity2D",
                "ProjectedRoughness_boundary",
                "PtotalOverPouter",
                "ProjectedRegularity2D",
                "A_blob_Atotal",
            ]:
                self.assertIn(column, by_blob.columns)

            shape_by_blob = pd.read_csv(output_dir / "blob_shape_class_by_blob.csv")
            self.assertEqual(len(shape_by_blob), 6)
            self.assertIn("ShapeClass", shape_by_blob.columns)

            shape_by_frame = pd.read_csv(output_dir / "blob_shape_class_summary_by_frame.csv")
            self.assertIn("ShapeValidCount", shape_by_frame.columns)
            self.assertIn("ShapeInvalidCount", shape_by_frame.columns)
            self.assertGreater(shape_by_frame["ShapeInvalidCount"].sum(), 0)

            by_frame = pd.read_csv(output_dir / "blob_morphology_by_frame.csv")
            self.assertEqual(set(by_frame["FrameIndex"]), {1, 2, 3})

            reliability = pd.read_csv(output_dir / "blob_morphology_reliability_by_tier.csv")
            self.assertTrue({"all", "area_ge_250", "area_ge_500"}.issubset(set(reliability["AreaTierGroup"])))
            self.assertIn("InterpretationTier", reliability.columns)

            representatives = pd.read_csv(output_dir / "representative_blob_candidates.csv")
            self.assertFalse(representatives.empty)
            self.assertTrue(
                {"class_medoid", "high_confidence_exemplar", "shape_extreme", "large_area_exemplar"}.intersection(
                    set(representatives["ExemplarType"])
                )
            )
            self.assertIn("SelectionReason", representatives.columns)
            candidate_validity = representatives.merge(
                shape_by_blob[["FrameIndex", "BlobID", "ShapeValid"]],
                on=["FrameIndex", "BlobID"],
                how="left",
            )
            valid_exemplars = candidate_validity.loc[
                candidate_validity["ExemplarType"] != "qc_exclusion_example",
                "ShapeValid",
            ]
            self.assertTrue(valid_exemplars.astype(bool).all())

            thresholds = json.loads((output_dir / "blob_morphology_thresholds.json").read_text(encoding="utf-8"))
            self.assertEqual(thresholds["reference_filter"]["min_area_px"], 250)
            self.assertIn("ProjectedRegularity2D", thresholds["thresholds"])

            manifest = json.loads((output_dir / "blob_morphology_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scope"], blob_product.SCOPE_LANGUAGE)
            self.assertEqual(manifest["sidecar_qc_metrics"]["OverallStatus"], "PASS")
            for field in [
                "schema_version",
                "input_sidecar_dir",
                "input_file_inventory",
                "sidecar_qc",
                "command_line_args",
                "config",
                "output_file_inventory",
                "no_rerun_statement",
                "git_commit_or_status_note",
            ]:
                self.assertIn(field, manifest)
            self.assertIn("geometry_by_blob.csv", manifest["input_file_inventory"])
            self.assertIn("blob_morphology_by_blob.csv", manifest["output_file_inventory"])
            manifest_size = (output_dir / "blob_morphology_manifest.json").stat().st_size
            self.assertEqual(
                manifest["output_file_inventory"]["blob_morphology_manifest.json"]["bytes"],
                manifest_size,
            )

            qc_md = (output_dir / "blob_morphology_qc_summary.md").read_text(encoding="utf-8")
            self.assertIn("2D exterior-boundary proxy", qc_md)
            self.assertIn("not full NAPL-water interfacial area", qc_md)


def make_synthetic_sidecar(root: Path, include_blob_rows: bool) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    qc_rows = [
        ("OverallStatus", "PASS"),
        ("ProcessedFrames", 3),
        ("GeometryBlobRows", 6),
        ("BlobCountPassFrames", 3),
        ("TotalAreaPassFrames", 3),
        ("MaxConsecutiveMismatchFrames", 0),
        ("EmptyGeometryFrames", 0),
        ("BoundaryMetricValidRows", 5),
        ("BlockedForInterpretation", "false"),
    ]
    pd.DataFrame(qc_rows, columns=["Metric", "Value"]).to_csv(root / "geometry_qc_summary.csv", index=False)
    pd.DataFrame(
        {
            "FrameIndex": [1, 2, 3],
            "BlobCount": [2, 2, 2],
            "TotalArea_px": [900.0, 1600.0, 1200.0],
        }
    ).to_csv(root / "geometry_summary_by_frame.csv", index=False)
    pd.DataFrame({"FrameIndex": [1, 2, 3], "BlobCountMatch": [True, True, True]}).to_csv(
        root / "geometry_level_a_comparison_all_frames.csv",
        index=False,
    )
    pd.DataFrame({"FrameIndex": [1, 2, 3], "Diagnostic": ["ok", "ok", "ok"]}).to_csv(
        root / "geometry_discrepancy_diagnostics_all_frames.csv",
        index=False,
    )
    pd.DataFrame({"File": ["geometry_by_blob.csv"], "Rows": [6]}).to_csv(
        root / "geometry_sidecar_manifest.csv",
        index=False,
    )
    (root / "geometry_provenance.json").write_text(json.dumps({"source": "synthetic"}), encoding="utf-8")

    if include_blob_rows:
        rows = pd.DataFrame(
            {
                "FrameIndex": [1, 1, 2, 2, 3, 3],
                "RealTime_s": [0.0, 0.0, 1.0, 1.0, 2.0, 2.0],
                "BlobID_sidecar": [101, 102, 201, 202, 301, 302],
                "Area_px": [100.0, 800.0, 300.0, 1300.0, 500.0, 700.0],
                "MajorAxisLength_px": [20.0, 35.0, 30.0, 80.0, 50.0, 38.0],
                "MinorAxisLength_px": [10.0, 31.0, 15.0, 10.0, 25.0, 25.0],
                "ConvexArea_px": [125.0, 850.0, 375.0, 1800.0, 900.0, 760.0],
                "Solidity_geometry": [0.8, 0.94, 0.8, 0.72, 0.56, 0.92],
                "P_outer_boundary": [40.0, 100.0, 70.0, 190.0, 140.0, 92.0],
                "Pc_outer_boundary": [36.0, 95.0, 65.0, 150.0, 100.0, 88.0],
                "P_total_boundary": [60.0, 105.0, 92.0, 300.0, 230.0, 108.0],
                "ProjectedRoughness_boundary": [1.1, 1.02, 1.15, 1.7, 1.55, 0.95],
                "Circularity2D_boundary": [0.785, 0.98, 0.77, 0.43, 0.5, 1.08],
                "AreaTier": ["tiny", "large", "medium", "large", "large", "large"],
                "BoundaryMetricValid": [False, True, True, True, True, True],
                "RoughnessLessThanOne": [False, False, False, False, False, True],
                "CircularityGreaterThan1p05": [False, False, False, False, False, True],
                "MaskPath": ["", "mask_102.png", "mask_201.png", "mask_202.png", "", "mask_302.png"],
                "LabelPath": ["", "label_102.png", "label_201.png", "label_202.png", "label_301.png", ""],
            }
        )
        rows.to_csv(root / "geometry_by_blob.csv", index=False)
    else:
        (root / "geometry_by_blob.csv").write_text("", encoding="utf-8")
    return root


def rewrite_qc_metric(sidecar_dir: Path, metric: str, value: object) -> None:
    qc = pd.read_csv(sidecar_dir / "geometry_qc_summary.csv")
    qc.loc[qc["Metric"] == metric, "Value"] = value
    qc.to_csv(sidecar_dir / "geometry_qc_summary.csv", index=False)


def make_split_frame_blob_rows(sidecar_dir: Path) -> None:
    rows = pd.DataFrame(
        {
            "FrameIndex": [1, 1, 2, 2, 2, 3],
            "RealTime_s": [0.0, 0.0, 1.0, 1.0, 1.0, 2.0],
            "BlobID_sidecar": [101, 102, 201, 202, 203, 301],
            "Area_px": [100.0, 800.0, 10.0, 300.0, 1000.0, 700.0],
            "MajorAxisLength_px": [20.0, 35.0, 5.0, 20.0, 70.0, 38.0],
            "MinorAxisLength_px": [10.0, 31.0, 4.0, 10.0, 35.0, 25.0],
            "ConvexArea_px": [125.0, 850.0, 20.0, 125.0, 1200.0, 760.0],
            "Solidity_geometry": [0.8, 0.94, 0.5, 0.8, 0.83, 0.92],
            "P_outer_boundary": [40.0, 100.0, 12.0, 40.0, 150.0, 92.0],
            "Pc_outer_boundary": [36.0, 95.0, 10.0, 36.0, 140.0, 88.0],
            "P_total_boundary": [60.0, 105.0, 18.0, 60.0, 180.0, 108.0],
            "ProjectedRoughness_boundary": [1.1, 1.02, 1.1, 1.2, 1.3, 0.95],
            "Circularity2D_boundary": [0.785, 0.98, 0.75, 0.8, 0.85, 1.08],
            "AreaTier": ["tiny", "large", "tiny", "small", "large", "large"],
            "BoundaryMetricValid": [False, True, False, True, True, True],
            "RoughnessLessThanOne": [False, False, False, False, False, True],
            "CircularityGreaterThan1p05": [False, False, False, False, False, True],
            "TouchesImageBorder": [False, False, False, True, False, False],
            "MaskPath": ["", "mask_102.png", "", "mask_202.png", "mask_203.png", ""],
            "LabelPath": ["", "label_102.png", "", "label_202.png", "label_203.png", "label_301.png"],
        }
    )
    rows.to_csv(sidecar_dir / "geometry_by_blob.csv", index=False)
    rewrite_qc_metric(sidecar_dir, "BoundaryMetricValidRows", 4)


def make_all_ineligible_blob_rows(sidecar_dir: Path) -> None:
    rows = pd.read_csv(sidecar_dir / "geometry_by_blob.csv")
    rows["Area_px"] = [100.0] * len(rows)
    rows["BoundaryMetricValid"] = [False] * len(rows)
    rows["AreaTier"] = ["tiny"] * len(rows)
    rows.to_csv(sidecar_dir / "geometry_by_blob.csv", index=False)
    rewrite_qc_metric(sidecar_dir, "BoundaryMetricValidRows", 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
