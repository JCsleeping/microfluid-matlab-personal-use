from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FIGURE_SUFFIXES = ("png", "svg")


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path):
    path = Path(path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as fid:
        return json.load(fid)


def write_json(path, payload):
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fid:
        json.dump(to_json_safe(payload), fid, ensure_ascii=False, indent=2)


def to_json_safe(value):
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value) if not isinstance(value, (str, bytes, dict, list, tuple)) else False:
        return None
    return value


def save_figure(fig, figures_dir, stem, dpi=300):
    figures_dir = ensure_dir(figures_dir)
    paths = []
    for suffix in FIGURE_SUFFIXES:
        path = figures_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi if suffix == "png" else None, facecolor="white", bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def numeric_series(df, column, default=np.nan):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def prepare_time_columns(df):
    out = df.copy()
    if "FrameIndex" not in out.columns:
        if "Time" in out.columns:
            t = pd.to_numeric(out["Time"], errors="coerce")
            if t.notna().all() and np.allclose(t.to_numpy(), np.round(t.to_numpy())):
                out["FrameIndex"] = t.astype(int) + 1
            else:
                out["FrameIndex"] = np.arange(1, len(out) + 1)
        else:
            out["FrameIndex"] = np.arange(1, len(out) + 1)
    else:
        out["FrameIndex"] = pd.to_numeric(out["FrameIndex"], errors="coerce")

    if "RealTime_s" in out.columns:
        out["Time_min"] = pd.to_numeric(out["RealTime_s"], errors="coerce") / 60.0
    elif "Time_min" in out.columns:
        out["Time_min"] = pd.to_numeric(out["Time_min"], errors="coerce")
    elif "Time" in out.columns:
        out["Time_min"] = pd.to_numeric(out["Time"], errors="coerce")
    elif "FrameTime" in out.columns:
        out["Time_min"] = pd.to_numeric(out["FrameTime"], errors="coerce")
    else:
        out["Time_min"] = np.arange(len(out), dtype=float)
    return out


def add_sn_derived_columns(df):
    out = df.copy()
    sn = numeric_series(out, "Sn")
    finite = sn[np.isfinite(sn)]
    sn0 = float(finite.iloc[0]) if len(finite) else np.nan
    if np.isfinite(sn0) and sn0 != 0:
        out["SnNorm"] = sn / sn0
        out["RemovalFraction"] = (sn0 - sn) / sn0
    else:
        out["SnNorm"] = np.nan
        out["RemovalFraction"] = np.nan
    return out


def assign_level_a_stage(sn_norm):
    arr = np.asarray(sn_norm, dtype=float)
    stage = np.full(arr.shape, "unknown", dtype=object)
    finite = np.isfinite(arr)
    stage[finite & (arr >= 0.67)] = "early"
    stage[finite & (arr < 0.67) & (arr >= 0.33)] = "middle"
    stage[finite & (arr < 0.33) & (arr >= 0.05)] = "late"
    stage[finite & (arr < 0.05)] = "near-depleted"
    return stage


def monotone_nonincreasing(values):
    values = np.asarray(values, dtype=float)
    out = np.full(values.shape, np.nan, dtype=float)
    current = np.nan
    for i, value in enumerate(values):
        if not np.isfinite(value):
            continue
        if not np.isfinite(current):
            current = value
        else:
            current = min(current, value)
        out[i] = current
    return out


def compute_rate_per_min(time_min, sn, rate_window_min=20.0, min_points=25, monotone=True):
    x = np.asarray(time_min, dtype=float)
    y = np.asarray(sn, dtype=float)
    if monotone:
        y = monotone_nonincreasing(y)
    rate = np.full(y.shape, np.nan, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 2:
        return pd.Series(rate)
    xf = x[finite]
    yf = y[finite]
    if np.unique(xf).size < 2:
        return pd.Series(rate)
    min_points = max(2, int(min_points))
    half_window = max(float(rate_window_min), 0.0) / 2.0
    local_rate = np.full(yf.shape, np.nan, dtype=float)
    for i, t0 in enumerate(xf):
        if half_window > 0:
            idx = np.where(np.abs(xf - t0) <= half_window)[0]
        else:
            idx = np.array([i], dtype=int)
        if idx.size < min_points:
            nearest = np.argsort(np.abs(xf - t0))[:min(min_points, xf.size)]
            idx = np.sort(nearest)
        if np.unique(xf[idx]).size < 2:
            continue
        centered_x = xf[idx] - t0
        slope, _ = np.polyfit(centered_x, yf[idx], 1)
        local_rate[i] = max(0.0, -float(slope))
    rate[finite] = local_rate
    return pd.Series(rate)


def pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 3:
        return np.nan
    x = x[finite]
    y = y[finite]
    if np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y):
    xs = pd.Series(x, dtype="float64").rank(method="average")
    ys = pd.Series(y, dtype="float64").rank(method="average")
    return pearson(xs, ys)


def finite_stats(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"mean": np.nan, "median": np.nan, "q25": np.nan, "q75": np.nan}
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "q25": float(np.percentile(arr, 25)),
        "q75": float(np.percentile(arr, 75)),
    }
