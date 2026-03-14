# Progress Log

## Session: 2026-03-12

### 13:37 – User reports pipeline "crash" again
- Investigated running MATLAB processes, log files, memory usage
- Confirmed: not a hard crash, but frontend hang under memory/IO pressure
- Collected evidence: process stats, log tail analysis, smoke tests

### 14:xx – Root cause identified
- Three compounding factors: full mask retention (5.6 GB), 4 workers (high RAM), excessive parfor logging
- Created optimization plan with 4 phases

### Status: Awaiting user decision on optimization approach
