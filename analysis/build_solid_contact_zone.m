function solid_contact_zone = build_solid_contact_zone(flow_domain, config)
% BUILD_SOLID_CONTACT_ZONE  Precompute the solid-contact mask for Step 4.

    solid_dilation = 1;
    if isfield(config, 'interface') && isfield(config.interface, 'solid_dilation')
        solid_dilation = config.interface.solid_dilation;
    end

    solid_contact_zone = imdilate(~flow_domain, strel('disk', solid_dilation));
end
