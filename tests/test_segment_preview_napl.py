from pathlib import Path
import importlib.util
import sys

import numpy as np


def load_segment_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "color_tuning"
        / "segment_preview_napl.py"
    )
    spec = importlib.util.spec_from_file_location("segment_preview_napl", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_preview_fixture():
    rgb = np.full((20, 20, 3), [0.15, 0.55, 0.58], dtype=np.float32)
    rgb[4:9, 4:9, :] = [0.95, 0.05, 0.07]
    rgb[13:16, 13:17, :] = [0.85, 0.08, 0.09]
    domain = np.zeros((20, 20), dtype=bool)
    domain[2:18, 2:18] = True
    core = np.zeros((20, 20), dtype=bool)
    core[5:15, 5:15] = True
    return rgb, domain, core


def test_segment_red_napl_does_not_require_endpoint_references():
    segment = load_segment_module()
    rgb, domain, core = make_preview_fixture()

    result = segment.segment_red_napl(
        rgb,
        domain_mask=domain,
        core_mask=core,
        score_mode="excess_red",
        threshold=0.35,
        min_area_px=4,
    )

    assert result.mask.dtype == bool
    assert np.count_nonzero(result.mask) == 37
    assert result.diagnostics["endpoint_dependency"] == "none"
    assert result.diagnostics["segmentation_output"] == "segmentation_mask"
    assert result.diagnostics["red_mask_area_fraction"] > 0
    assert not any("Sn" in key or "sn_final" in key.lower() for key in result.diagnostics)


def test_threshold_sweep_reports_area_components_and_largest_fraction():
    segment = load_segment_module()
    rgb, domain, _ = make_preview_fixture()
    score = segment.score_preview_rgb(rgb, "excess_red")

    rows = segment.threshold_sweep(score, domain, thresholds=[0.2, 0.5])

    assert [row["threshold"] for row in rows] == [0.2, 0.5]
    assert rows[0]["mask_area_fraction"] >= rows[1]["mask_area_fraction"]
    assert rows[0]["component_count"] >= 1
    assert 0 < rows[0]["largest_component_fraction"] <= 1


def test_core_and_edge_area_fractions_are_reported_separately():
    segment = load_segment_module()
    rgb, domain, core = make_preview_fixture()

    result = segment.segment_red_napl(
        rgb,
        domain_mask=domain,
        core_mask=core,
        score_mode="lab_a",
        threshold=15.0,
        min_area_px=1,
    )

    assert result.diagnostics["red_mask_area_fraction_core"] > 0
    assert result.diagnostics["red_mask_area_fraction_edge"] > 0
    assert result.diagnostics["core_flow_area_px"] == int(np.count_nonzero(core))
    assert result.diagnostics["edge_band_area_px"] == int(np.count_nonzero(domain & ~core))


def test_hysteresis_reports_seed_candidate_and_growth_ratio():
    segment = load_segment_module()
    rgb, domain, _ = make_preview_fixture()

    result = segment.segment_red_napl(
        rgb,
        domain_mask=domain,
        score_mode="excess_red",
        seed_threshold=0.75,
        candidate_threshold=0.25,
        min_area_px=1,
    )

    assert result.diagnostics["seed_fraction"] > 0
    assert result.diagnostics["candidate_fraction"] >= result.diagnostics["seed_fraction"]
    assert result.diagnostics["growth_ratio"] >= 1
    assert result.diagnostics["red_mask_area_fraction"] <= result.diagnostics["candidate_fraction"]
