from pathlib import Path
import importlib.util
import sys


def load_tune_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "color_tuning"
        / "tune_light_field.py"
    )
    spec = importlib.util.spec_from_file_location("tune_light_field", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_methods_excludes_basicpy_by_default():
    module = load_tune_module()

    methods = module.build_methods([160])

    names = [method.name for method in methods]
    assert "basicpy_rgb_all" not in names
    assert "basicpy_luma_all" not in names


def test_build_methods_can_include_basicpy_candidates():
    module = load_tune_module()

    methods = module.build_methods([160], include_basicpy=True)

    names = [method.name for method in methods]
    assert "basicpy_rgb_all" in names
    assert "basicpy_luma_all" in names


def test_percentile_contrast_preview_does_not_mutate_source():
    module = load_tune_module()
    rgb = module.np.array(
        [
            [[0.0, 0.1, 0.2], [0.2, 0.3, 0.4]],
            [[0.6, 0.7, 0.8], [0.8, 0.9, 1.0]],
        ],
        dtype=module.np.float32,
    )
    original = rgb.copy()

    preview = module.apply_contrast_preview(
        rgb,
        mode="percentile",
        low_percentile=10,
        high_percentile=90,
    )

    assert module.np.array_equal(rgb, original)
    assert preview.image.shape == rgb.shape
    assert float(preview.image.min()) == 0.0
    assert float(preview.image.max()) == 1.0
    assert preview.clip_low_fraction > 0.0
    assert preview.clip_high_fraction > 0.0


def test_preview_scale_factor_doubles_rgb_shape():
    module = load_tune_module()
    rgb = module.np.zeros((3, 5, 3), dtype=module.np.float32)

    scaled = module.resize_preview(rgb, scale_factor=2, method="bicubic")

    assert scaled.shape == (6, 10, 3)
    assert rgb.shape == (3, 5, 3)
