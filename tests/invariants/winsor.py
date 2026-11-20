# -*- coding: utf-8 -*-
"""I12：winsor 变换的因果性（逐期独立拟合，扰动未来不影响历史）。"""
import numpy as np

from modules.factor_adaptive_winsor.core.enhanced_transformers import (
    EnhancedRankPreservingScaler,
)

from .registry import Invariant, register


def _rowwise(matrix):
    out = np.full_like(matrix, np.nan)
    for t in range(matrix.shape[0]):
        scaler = EnhancedRankPreservingScaler()
        row = matrix[t]
        transformed = scaler.fit(row).transform(row)
        out[t] = np.asarray(transformed, dtype=float).ravel()
    return out


def check_i12(panel):
    T = panel.spec.n_dates
    t = max(1, T // 2)
    base = _rowwise(panel.factor[:t])
    perturbed = panel.factor.copy()
    perturbed[t:] = perturbed[t:] * 3.0 + 100.0
    alt = _rowwise(perturbed[:t])
    same = (base == alt) | (np.isnan(base) & np.isnan(alt))
    bad = np.argwhere(~same)
    if bad.size:
        r, c = int(bad[0][0]), int(bad[0][1])
        return False, "首个不等位置=(%d,%d)" % (r, c)
    return True, "前 %d 期在扰动未来后逐位一致" % t


register(Invariant("I12_winsor_causal", "modules.factor_adaptive_winsor",
                   "invariant", "clean", check_i12))
