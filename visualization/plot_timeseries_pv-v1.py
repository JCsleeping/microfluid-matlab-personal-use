"""PV-axis wrapper for plot_timeseries-v1.py."""

from __future__ import annotations

from plot_timeseries_pv_common import main_for_original


def main(argv=None):
    return main_for_original("plot_timeseries-v1.py", "plot_timeseries_v1_source", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
