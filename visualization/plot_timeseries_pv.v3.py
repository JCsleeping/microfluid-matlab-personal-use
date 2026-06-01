"""PV-axis wrapper for the current Nature-style plot_timeseries.py.

Historically this wrapped a stand-alone plot_timeseries.v3.py, but v3 is now a
thin forwarder. We therefore wrap plot_timeseries.py directly so flags such as
--min-time-min, --skip-frames, --no-rebase-time, --smooth-window, etc. are all
recognized.
"""

from __future__ import annotations

from plot_timeseries_pv_common import main_for_original


def main(argv=None):
    return main_for_original("plot_timeseries.py", "plot_timeseries_v3_source", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
