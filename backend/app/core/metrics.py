"""Forecast accuracy metrics.

WAPE is the headline metric: unlike MAPE it does not explode on low-volume weeks
and it weights errors by volume, which is what matters for inventory.
"""

from __future__ import annotations

import numpy as np


def _arrays(actual, forecast) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    if a.shape != f.shape:
        raise ValueError("actual and forecast must have the same length")
    return a, f


def wape(actual, forecast) -> float | None:
    a, f = _arrays(actual, forecast)
    denom = np.abs(a).sum()
    return float(np.abs(a - f).sum() / denom * 100) if denom > 0 else None


def mape(actual, forecast) -> float | None:
    a, f = _arrays(actual, forecast)
    mask = a != 0
    return float(np.mean(np.abs((a[mask] - f[mask]) / a[mask])) * 100) if mask.any() else None


def rmse(actual, forecast) -> float | None:
    a, f = _arrays(actual, forecast)
    return float(np.sqrt(np.mean((a - f) ** 2))) if len(a) else None


def mae(actual, forecast) -> float | None:
    a, f = _arrays(actual, forecast)
    return float(np.mean(np.abs(a - f))) if len(a) else None


def bias(actual, forecast) -> float | None:
    """Positive = over-forecasting (too much stock), negative = under-forecasting."""
    a, f = _arrays(actual, forecast)
    denom = np.abs(a).sum()
    return float((f - a).sum() / denom * 100) if denom > 0 else None


def summary(actual, forecast) -> dict[str, float | None]:
    return {
        "wape": wape(actual, forecast),
        "mape": mape(actual, forecast),
        "rmse": rmse(actual, forecast),
        "mae": mae(actual, forecast),
        "bias": bias(actual, forecast),
        "n": len(actual),
    }


def robust_sigma(log_residuals) -> float:
    """Robust std-dev estimate (scaled MAD) so a few anomalies don't widen every interval."""
    r = np.asarray(log_residuals, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 4:
        return 0.15
    mad = np.median(np.abs(r - np.median(r)))
    return float(max(1.4826 * mad, 0.03))
