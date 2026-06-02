from run_dnapl_branch_c_timeseries_tool import segmorph_interface_quality


def test_segmorph_interface_quality_allows_empty_red_mask() -> None:
    quality = segmorph_interface_quality(
        [
            {
                "red_mask_area_px": "0",
                "dnapl_water_length_px": "0",
                "dnapl_solid_length_px": "0",
                "dnapl_water_length_m": "NaN",
                "dnapl_solid_length_m": "NaN",
                "InterfaceArea": "0",
                "solid_contact_fraction": "NaN",
                "a_i_2D_proxy": "NaN",
                "interface_semantics": "InterfaceArea_legacy_alias_of_dnapl_water_length_px_not_area",
            }
        ]
    )

    assert quality["missing_columns"] == []
    assert quality["alias_mismatch_count"] == 0
    assert quality["water_length_nonpositive_with_mask_count"] == 0
    assert quality["solid_length_negative_count"] == 0
    assert quality["solid_contact_fraction_out_of_range_count"] == 0
    assert quality["a_i_2D_proxy_bad_count"] == 0
    assert quality["interface_semantics_bad_count"] == 0
