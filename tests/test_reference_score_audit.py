from pathlib import Path
import importlib.util
import sys

import numpy as np


def load_audit_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "color_tuning"
        / "audit_reference_scores.py"
    )
    spec = importlib.util.spec_from_file_location("audit_reference_scores", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_candidate_passes_when_high_tracks_napl_and_regions_agree():
    audit = load_audit_module()

    result = audit.classify_candidate(
        endpoint_delta=0.50,
        s_high=0.92,
        s_residual=0.18,
        region_s_high={"left": 0.88, "center": 0.94, "right": 0.91},
        region_s_residual={"left": 0.16, "center": 0.20, "right": 0.17},
        min_endpoint_delta=0.05,
        min_separation=0.35,
        max_region_range=0.20,
    )

    assert result == "pass"


def test_classify_candidate_rejects_inverted_high_residual_order():
    audit = load_audit_module()

    result = audit.classify_candidate(
        endpoint_delta=-0.40,
        s_high=0.05,
        s_residual=0.82,
        region_s_high={"left": 0.06, "center": 0.04, "right": 0.07},
        region_s_residual={"left": 0.78, "center": 0.85, "right": 0.83},
        min_endpoint_delta=0.05,
        min_separation=0.35,
        max_region_range=0.20,
    )

    assert result == "inverted_high_residual"


def test_classify_candidate_rejects_unstable_regions():
    audit = load_audit_module()

    result = audit.classify_candidate(
        endpoint_delta=0.50,
        s_high=0.90,
        s_residual=0.20,
        region_s_high={"left": 0.45, "center": 1.02, "right": 0.92},
        region_s_residual={"left": 0.18, "center": 0.20, "right": 0.23},
        min_endpoint_delta=0.05,
        min_separation=0.35,
        max_region_range=0.20,
    )

    assert result == "unstable_regions"


def test_build_region_masks_partitions_only_selected_mask_pixels():
    audit = load_audit_module()

    base_mask = np.zeros((4, 9), dtype=bool)
    base_mask[1, [0, 1, 2, 6, 7, 8]] = True
    base_mask[2, [0, 1, 2, 6, 7, 8]] = True

    regions = audit.build_region_masks(base_mask)

    assert np.array_equal(regions["all"], base_mask)
    assert not np.any(regions["left"] & ~base_mask)
    assert not np.any(regions["center"] & ~base_mask)
    assert not np.any(regions["right"] & ~base_mask)
    assert sum(np.count_nonzero(regions[name]) for name in ("left", "center", "right")) == np.count_nonzero(base_mask)
    assert max(np.count_nonzero(regions[name]) for name in ("left", "center", "right")) - min(
        np.count_nonzero(regions[name]) for name in ("left", "center", "right")
    ) <= 1


def test_prepare_mask_crops_native_full_mask_and_resizes_with_nearest():
    audit = load_audit_module()

    raw_mask = np.zeros((4, 4), dtype=bool)
    raw_mask[1:3, 1:3] = np.array([[True, False], [False, True]])

    selection = audit.prepare_mask(
        raw_mask,
        target_shape=(4, 4),
        crop=(2, 2, 2, 2),
        mask_id="core_flow",
        mask_source="image",
        mask_source_path=Path("mask.png"),
        mask_variable_name="",
        mask_grid="native_full",
    )

    expected = np.array(
        [
            [True, True, False, False],
            [True, True, False, False],
            [False, False, True, True],
            [False, False, True, True],
        ],
        dtype=bool,
    )
    assert np.array_equal(selection.mask, expected)
    assert selection.provenance.mask_resize_method == "nearest"
    assert selection.provenance.mask_shape_original == (4, 4)
    assert selection.provenance.mask_shape_used == (4, 4)
    assert selection.provenance.mask_pixel_count_all == 8


def test_endpoint_eligibility_rejects_unmasked_diagnostic_rows():
    audit = load_audit_module()

    decision = audit.endpoint_eligibility(
        status="pass",
        mask_id="none",
        self_endpoint_check=False,
        rgb_source="corrected_quantitative",
    )

    assert decision.eligible_for_quantitative_endpoint is False
    assert decision.failure_reason == "unmasked_domain"


def test_endpoint_eligibility_rejects_self_check_even_when_score_passes():
    audit = load_audit_module()

    decision = audit.endpoint_eligibility(
        status="pass",
        mask_id="core_flow",
        self_endpoint_check=True,
        rgb_source="corrected_quantitative",
    )

    assert decision.eligible_for_quantitative_endpoint is False
    assert decision.failure_reason == "self_validation_only"


def test_endpoint_eligibility_rejects_contrast_preview_for_quantitative_audit():
    audit = load_audit_module()

    decision = audit.endpoint_eligibility(
        status="pass",
        mask_id="core_flow",
        self_endpoint_check=False,
        rgb_source="contrast_preview",
    )

    assert decision.eligible_for_quantitative_endpoint is False
    assert decision.failure_reason == "non_quantitative_rgb_source"


def test_endpoint_eligibility_keeps_segmentation_eligibility_separate():
    audit = load_audit_module()

    decision = audit.endpoint_eligibility(
        status="bad_endpoint_delta",
        mask_id="core_flow",
        self_endpoint_check=False,
        rgb_source="corrected_quantitative",
    )

    assert decision.eligible_for_quantitative_endpoint is False
    assert decision.eligible_for_segmentation is True
    assert decision.eligible_for_color_index_timeseries is True


def test_lab_ab_projection_global_is_available_for_masked_audit():
    audit = load_audit_module()

    assert "lab_ab_projection_global" in audit.SCORE_MODES
    assert "lab_ab_projection_pixelwise" in audit.SCORE_MODES

    corrected = {
        "water": np.full((3, 3, 3), [0.45, 0.45, 0.45], dtype=np.float32),
        "napl": np.full((3, 3, 3), [0.85, 0.10, 0.14], dtype=np.float32),
        "high": np.full((3, 3, 3), [0.75, 0.20, 0.22], dtype=np.float32),
        "residual": np.full((3, 3, 3), [0.55, 0.36, 0.36], dtype=np.float32),
    }
    masks = audit.build_region_masks(np.ones((3, 3), dtype=bool))

    values = audit.compute_score_values(corrected, masks, "lab_ab_projection_global")

    assert values["napl"]["all"] > values["water"]["all"]
    assert values["water"]["all"] < values["residual"]["all"] < values["high"]["all"] < values["napl"]["all"]


def test_candidate_provenance_row_records_endpoint_role_and_inputs():
    audit = load_audit_module()
    candidate = audit.CandidateSpec("high_as_endpoint", Path("high.tif"))

    row = audit.candidate_provenance_row(
        candidate,
        water_path=Path("water.tif"),
        high_path=Path("high.tif"),
        residual_path=Path("residual.tif"),
        page=3,
    )

    assert row["endpoint_candidate_role"] == "self_check"
    assert row["napl_ref_path"] == "high.tif"
    assert row["water_reference_path"] == "water.tif"
    assert row["high_validation_path"] == "high.tif"
    assert row["residual_validation_path"] == "residual.tif"
    assert row["page"] == 3


def test_audit_manifest_records_mask_and_input_provenance():
    audit = load_audit_module()
    selection = audit.make_unmasked_selection((3, 4), crop=None)

    manifest = audit.build_audit_manifest(
        water_path=Path("water.tif"),
        high_path=Path("high.tif"),
        residual_path=Path("residual.tif"),
        candidates=[audit.CandidateSpec("napl_A", Path("napl.tif"))],
        config={"correction": "none", "page": 1},
        mask_selection=selection,
        rgb_source="corrected_quantitative",
    )

    assert manifest["inputs"]["water_reference_path"] == "water.tif"
    assert manifest["inputs"]["candidates"][0]["label"] == "napl_A"
    assert manifest["mask"]["mask_id"] == "none"
    assert manifest["rgb_source"] == "corrected_quantitative"
