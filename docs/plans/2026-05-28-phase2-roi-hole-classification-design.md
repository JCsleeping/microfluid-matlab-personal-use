# Phase 2 ROI Hole Classification Design

## Purpose

Phase 2 adds a reusable `roi` geometry mode to the DNAPL pipeline. The goal is to recover domain-aware per-blob hole counts without returning to the unstable Phase 0/legacy pattern of allocating a full-frame mask for every blob.

This is a general pipeline feature. It must not depend on G18, G21, a specific output directory, a fixed image size, or a dataset-specific blob population. Any threshold added here must be expressed in config and recorded in schema/provenance output.

## Geometry Modes

- `core_only`: default stable mode from Phase 1. Computes scalar per-blob geometry and Euler-derived hole counts. It does not compute domain-aware hole classification.
- `roi`: Phase 2 mode. Computes scalar geometry as in `core_only`, then performs domain-aware hole classification in a local padded ROI for each blob.
- `legacy_fullframe`: retained only for small regression tests and explicit debugging. It still uses the original per-blob full-frame mask path.

## ROI Semantics

For each blob, Phase 2 builds a local mask from that blob's `PixelIdxList` and a configurable padding width. Hole detection is performed on the padded local mask using the configured 2-D connectivity. Domain classification is then computed using the corresponding local slices of `flow_domain` and `solid_mask`.

The ROI output must explicitly record:

- `GeometryMode`
- `GeometrySchemaVersion`
- `ObjectConnectivity`
- `HoleClassificationComputed`
- `HoleCountSource`
- `EulerHoleCount`
- `RoiFallbackUsed`
- `RoiFallbackReason`
- `TouchesImageBorder`
- `RoiAreaFraction`

If a blob ROI is too large, or if a required domain mask is unavailable or incompatible, the row must fall back to Euler-only semantics for that blob and mark `HoleClassificationComputed=false`. It must not record a domain-aware hole classification when one was not computed.

## Schema

The default schema for `roi` runs is `geometry_v3_roi_holes`. Fresh ROI runs should use a new output directory. Existing Phase 1 `geometry_v2_core_only` chunks must not be silently mixed with `geometry_v3_roi_holes` chunks.

## Validation Scope

Phase 2 validation is limited to synthetic masks and short smoke tests. It should prove:

- `roi` is accepted by config validation.
- ROI domain-aware hole classification matches legacy behavior on small synthetic masks where both definitions are equivalent.
- Domain-aware fields are only populated when `HoleClassificationComputed=true`.
- Large or incompatible ROI cases fall back explicitly.
- The blob-detail schema carries all provenance columns.

Full production runs are a separate operational step after this code path is verified.
