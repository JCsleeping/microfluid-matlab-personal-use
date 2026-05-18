function catalog = build_metric_catalog()
% BUILD_METRIC_CATALOG  Static metric feasibility catalog.

    rows = {
        'area_px', 'Pixel area', 'morphology', 'P0', 'Area', 'Area', '', '', '', 'Cavarretta2010_shape_roughness', '';
        'area_physical', 'Physical area', 'morphology', 'P0', 'Area * pixel_size^2', 'Area', '', '', 'pixel_size_um', 'Cavarretta2010_shape_roughness', '';
        'equiv_diameter_2d', 'Equivalent diameter', 'morphology', 'P0', '2*sqrt(Area/pi)', 'Area', '', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'perimeter', 'Perimeter', 'morphology', 'P0', 'Perimeter', 'Perimeter', '', '', '', 'Cavarretta2010_shape_roughness', '';
        'major_axis', 'Major axis', 'morphology', 'P0', 'MajorAxisLength', 'MajorAxisLength', '', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'minor_axis', 'Minor axis', 'morphology', 'P0', 'MinorAxisLength', 'MinorAxisLength', '', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'aspect_ratio', 'Aspect ratio', 'morphology', 'P0', 'MajorAxisLength/MinorAxisLength', 'MajorAxisLength,MinorAxisLength', 'AspectRatio', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'orientation', 'Orientation', 'morphology', 'P1', 'Orientation', 'Orientation', '', '', '', 'Agaoglu2016_NAPL_architecture', '';
        'circularity_2d', 'Circularity2D', 'morphology', 'P0', '4*pi*Area/Perimeter^2', 'Area,Perimeter', 'Circularity2D', '', '', 'Cavarretta2010_shape_roughness', 'Not Wadell roundness.';
        'projected_sphericity_2d', 'Projected sphericity 2D', 'morphology', 'P1', '2*sqrt(pi*Area)/Perimeter', 'Area,Perimeter', '', '', '', 'Cavarretta2010_shape_roughness', '';
        'regularity_2d', 'Regularity proxy 2D', 'morphology', 'P1', '(Circularity2D+ProjectedSphericity2D)/2', 'Area,Perimeter', '', '', '', 'Cavarretta2010_shape_roughness', '';
        'ellipse_perimeter_proxy', 'Ellipse perimeter proxy', 'morphology', 'P1', 'Ramanujan ellipse perimeter', 'MajorAxisLength,MinorAxisLength', 'AspectRatio,Area', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'solidity', 'Solidity', 'morphology', 'P1', 'Area/ConvexArea', 'Area,ConvexArea', 'Solidity', '', '', 'Zhao2015_CT_morphology_fractal', '';
        'convex_perimeter', 'Convex perimeter', 'geometry', 'P1', 'Hull polygon perimeter', '', '', 'ConvexHull or mask', '', 'Zhao2015_CT_morphology_fractal', '';
        'projected_roughness', 'Projected roughness', 'geometry', 'P1', 'Perimeter/ConvexPerimeter', 'Perimeter', '', 'ConvexHull or mask', '', 'Cavarretta2010_shape_roughness', '';
        'angularity_proxy', 'Angularity proxy', 'geometry', 'P1', '(ConvexPerimeter/EllipsePerimeter)^2', '', '', 'ConvexHull or mask', '', 'YangWei2012_combined_roundness', '';
        'boundary_fractal_dimension', 'Boundary fractal dimension', 'geometry', 'P2', 'box-counting on boundary', '', '', 'Boundary or mask', '', 'Zhao2015_CT_morphology_fractal', 'Small blobs need later size threshold.';
        'blob_count', 'Blob count', 'timeseries', 'P0', 'rows per frame', 'FrameIndex', 'nblobs_arr', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'total_area', 'Total area', 'timeseries', 'P0', 'sum(Area) per frame', 'Area,FrameIndex', '', '', '', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'size_distribution_slope', 'Size distribution slope', 'distribution', 'P1', 'log-size distribution slope', 'Area', '', '', '', 'AltuhafiCoop2011_QicPic_distribution', '';
        'population_fractal_dimension', 'Population fractal proxy', 'distribution', 'P2', 'cumulative size-distribution slope', 'Area', '', '', '', 'Zhao2015_CT_morphology_fractal', 'Proxy only; not boundary fractal dimension.';
        'area_weighted_circularity', 'Area-weighted Circularity2D', 'timeseries', 'P1', 'weighted mean', 'Area,Circularity2D', '', '', '', 'YangWei2012_combined_roundness', '';
        'total_area_shrink_rate', 'Total area shrink rate', 'dissolution', 'P0', '-dTotalArea/dt', 'Area,FrameIndex', '', '', 'FrameTime', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'per_blob_area_shrink_rate', 'Per-blob area shrink rate', 'tracking', 'P1', '-dArea_track/dt', 'TrackID,Area,FrameTime', '', '', 'FrameTime', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'normalized_shrink_rate', 'Normalized shrink rate', 'tracking', 'P1', '-(1/A)*dA/dt', 'TrackID,Area,FrameTime', '', '', 'FrameTime', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'centroid_speed', 'Centroid speed', 'tracking', 'P2', 'dCentroid/dt', 'TrackID,CentroidX,CentroidY', '', '', 'FrameTime', 'Agaoglu2016_NAPL_architecture', '';
        'split_merge_events', 'Split/merge events', 'tracking', 'P1', 'IoU/topology events', 'TrackID', '', 'mask preferred', '', 'Agaoglu2016_NAPL_architecture', '';
        'exposed_interface_length', 'Exposed interface length', 'transport', 'P1', 'water-facing boundary', '', '', 'Boundary/mask + pore geometry', 'porous_geometry_mask', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'dead_end_exposure_proxy', 'Dead-end exposure proxy', 'transport', 'P2', 'pore class + blob location', '', '', 'pore geometry', 'porous_geometry_mask', 'Agaoglu2016_NAPL_architecture', '';
        'capillary_number', 'Capillary number', 'transport', 'P2', 'mu*U/gamma', '', '', '', 'viscosity,flow_rate,interfacial_tension', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'peclet_number', 'Peclet number', 'transport', 'P2', 'U*L/D', '', '', '', 'flow_rate,diffusion_coefficient', 'Hu2021_NAPL_interfacial_mass_transfer', '';
        'sherwood_proxy', 'Sherwood proxy', 'transport', 'P3', 'mass transfer relation', '', '', '', 'flow_rate,surfactant_concentration,interfacial area', 'EST2025_Cyrene_microfluidics', ''
        };
    catalog = cell2table(rows, 'VariableNames', {'metric_id', 'metric_name', 'category', ...
        'priority', 'formula', 'required_fields', 'alternative_fields', ...
        'required_geometry_source', 'required_metadata', 'literature_basis', 'notes'});
end
