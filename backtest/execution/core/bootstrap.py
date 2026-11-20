# -*- coding: utf-8 -*-
"""v3.8.0 自动块长（Politis-White + PPW 修正）。

公式：b = ((2 rho^2) / (1 - rho^2)^2)^(1/3) * N^(1/3)，
并夹到 ``[1, n // 3]``；rho 取 lag-1 自相关（无偏近似）。
"""
import numpy as np

__all__ = ["auto_block_size", "acf1"]


def acf1(x):
    """lag-1 自相关；样本不足或方差为 0 时返回 0.0。"""
    arr = np.asarray(x, dtype=float).ravel()
    if arr.size < 2:
        return 0.0
    arr = arr - arr.mean()
    denom = float(np.dot(arr, arr))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(arr[:-1], arr[1:]) / denom)


def auto_block_size(x, max_lag=10):
    """返回块长 ``b``（int，>=1 且 <= n//3）；``max_lag`` 仅保留签名。"""
    arr = np.asarray(x, dtype=float).ravel()
    n = int(arr.size)
    if n < 3:
        return 1
    rho = acf1(arr)
    rho2 = min(max(rho * rho, 0.0), 0.9999)
    if rho2 < 0.02:
        return 1
    factor = ((2.0 * rho2) / ((1.0 - rho2) ** 2)) ** (1.0 / 3.0)
    raw = factor * (n ** (1.0 / 3.0))
    upper = max(1, n // 3)
    return int(min(max(1, int(round(raw))), upper))
