# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from pandas.io.formats.style import Styler

from ui_formatting import MONEY_COLS, PCT_COLS

# ---------------- Median coloring (weekly + daily tables) ----------------

BAND_PCT = 0.14  # +/-14% around median => no coloring


def _safe_median(series: pd.Series):
    s = pd.to_numeric(series, errors="coerce")
    s = s.mask(s == 0).dropna()
    if s.empty:
        return None
    return float(s.median())


def _median_thresholds(median: float, band_pct: float):
    """
    Return (low, high) bounds for no-color band.
    If median == 0 -> we return (None, None) and do not color (to avoid nonsense).
    """
    if median is None:
        return (None, None)
    if median == 0:
        return (None, None)
    low = median * (1.0 - band_pct)
    high = median * (1.0 + band_pct)
    return (low, high)


def style_median_table(df: pd.DataFrame, metrics_dir: dict[str, str], band_pct: float = BAND_PCT) -> Styler:
    """
    metrics_dir: col -> "higher" (higher is better) or "lower" (lower is better)
    Colors:
      green: deviation from median in good direction > band_pct
      red:   deviation from median in bad direction  > band_pct
      none:  within median +/- band_pct
    """
    if df is None or df.empty:
        return df.style

    medians = {col: _safe_median(df[col]) for col in metrics_dir.keys() if col in df.columns}
    thresholds = {col: _median_thresholds(medians.get(col), band_pct) for col in metrics_dir.keys() if col in df.columns}

    def _cell_style(val, col):
        try:
            v = float(val)
        except Exception:
            return ""

        if col == "cr":
            if v < 3.0:
                return "background-color: rgba(255, 0, 0, 0.12);"
            if v < 6.0:
                return ""
            return "background-color: rgba(0, 200, 0, 0.15);"

        if col == "ctr":
            if v < 1.5:
                return "background-color: rgba(255, 0, 0, 0.12);"
            if v < 2.0:
                return ""
            return "background-color: rgba(0, 200, 0, 0.15);"

        if col == "total_drr_pct":
            if v > 30.0:
                return "background-color: rgba(255, 0, 0, 0.12);"
            if v >= 20.0:
                return ""
            return "background-color: rgba(0, 200, 0, 0.15);"

        if v == 0:
            return ""

        m = medians.get(col)
        low, high = thresholds.get(col, (None, None))

        # if median is None or 0 -> no coloring
        if m is None or low is None or high is None:
            return ""

        direction = metrics_dir.get(col)

        # within band
        if low <= v <= high:
            return ""

        # good/bad zones depend on direction
        if direction == "higher":
            if v > high:
                return "background-color: rgba(0, 200, 0, 0.15);"  # green
            if v < low:
                return "background-color: rgba(255, 0, 0, 0.12);"  # red
        elif direction == "lower":
            if v < low:
                return "background-color: rgba(0, 200, 0, 0.15);"  # green
            if v > high:
                return "background-color: rgba(255, 0, 0, 0.12);"  # red

        return ""

    def _apply_styles(frame: pd.DataFrame):
        styled = pd.DataFrame("", index=frame.index, columns=frame.columns)
        cols_to_style = set(metrics_dir.keys())
        cols_to_style.update({"cr", "ctr", "total_drr_pct"})
        for col in cols_to_style:
            if col not in frame.columns:
                continue
            styled[col] = frame[col].apply(lambda x: _cell_style(x, col))
        return styled

    styler = df.style.apply(_apply_styles, axis=None)

    # (Optional) nicer formatting without breaking numeric types:
    # Styler.format affects display; underlying df stays numeric -> sorting should stay numeric.
    fmt = {}
    for col in df.columns:
        if col in PCT_COLS:
            fmt[col] = lambda x: "" if pd.isna(x) else f"{float(x):.1f}%"
        elif col in {"click_price", "rpc", "target_cpc"}:
            fmt[col] = lambda x: "" if pd.isna(x) else f"{float(x):.1f} ₽"
        elif col == "vpo":
            fmt[col] = lambda x: "" if pd.isna(x) else f"{float(x):.1f}"
        elif col in MONEY_COLS:
            fmt[col] = lambda x: "" if pd.isna(x) else f"{float(x):.0f} ₽"
        elif col in ("views", "views_per_day", "clicks", "clicks_per_day", "ordered_units", "ordered_units_per_day", "days_in_period"):
            fmt[col] = lambda x: "" if pd.isna(x) else f"{int(round(float(x)))}"

    try:
        styler = styler.format(fmt, na_rep="")
    except Exception:
        # if streamlit/pandas version doesn't like the dict of lambdas, keep without format
        pass

    return styler

