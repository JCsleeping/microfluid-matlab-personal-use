# Findings: Pipeline Long-Run Crash Investigation

## Evidence Collected (2026-03-12)

### 1. Process state at time of "crash"
- 5 MATLAB processes still alive (1 main + 4 workers)
- Main process: ~5.0 GB private memory
- Workers: 1.3–1.7 GB each
- Workers still consuming CPU (not deadlocked)
- **Conclusion**: Not a hard crash. Frontend became unresponsive / window disappeared.

### 2. Log analysis
- `pipeline_log_20260312_134318.txt`: 531 "Interface analysis:" entries logged, no "Parallel processing complete", no "Pipeline completed"
- `pipeline_log_20260312_133757.txt`: Same pattern — no completion markers
- Both runs entered parallel mode with 4 workers successfully

### 3. Smoke test results
- 6-frame run with 4 workers: **PASS** (completed normally)
- 6-frame run with 2 workers: **PASS** (completed normally)
- Confirms issue is load/duration-dependent, not an immediate logic bug

### 4. Memory estimation
- Single mask: 1821 × 1916 = 3.49 MB
- All 1723 masks: **5.6 GB**
- Machine total RAM: ~16 GB
- Available RAM at idle: ~8 GB
- With 4 workers + masks: estimated peak **12–14 GB** → near capacity

### 5. Key code locations
- Mask storage: `characterize_solubilization_v2.m:123` (`masks_arr{t} = mask_t`)
- Mask release: `characterize_solubilization_v2.m:246-253` (only after ALL frames done)
- Change detection: `characterize_solubilization_v2.m:232-244` (needs all masks)
- Worker config: `config_pipeline.m:129-133`
- Per-frame logging: `correct_illumination.m:45`, `segment_DNAPL_v2.m:41`, `analyze_interfaces.m:89`
