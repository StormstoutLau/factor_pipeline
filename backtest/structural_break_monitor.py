# -*- coding: utf-8 -*-
"""结构突变监控 (v3.4.0 ADR, 暂用号 ADR-042).

输入: AR(1) 中位数路径 (FactorFingerprinter.compute_ar1_path).
输出: 只读告警字典; 不参与路由/不修改因子值.

方法:
- 'sup_f': 未知断点 sup-F 型统计量 (Andrews 1993), 零分布用 AR(1) 代理自助.
- 'cusum': Inclán-Tiao (1994) ICSS 思路的工程化变体, 同一自助框架.

方法学注记 (设计 §3.7 / m10, 实现与实现文档一致):
- sup-F 统计量只报 SSR 比值, 省略 F 自由度归一化 — p 值完全由自助零分布
  提供, 不依赖渐近 F 分布, 故无需 df 校正;
- 分母下限 1e-12 防近常数段 (SSR1(k)≈0) 比值爆炸产生虚假 sup;
- trim=0.15 → 候选 k ∈ [⌈0.15n⌉, n−⌈0.15n⌉], 符合 Andrews (1993)
  Π=[0.15, 0.85] 截断惯例 (k 取 0/n 端点被排除, 保证两段各有观测);
- AR(1) 代理自助替代渐近临界值, 为设计自行补充的工程化选择 (设计 m10,
  非 Andrews 原文方法): IC 路径强自相关使标准 sup-F 渐近零分布失效;
- CUSUM 为 Inclán-Tiao (1994) ICSS 工程化变体: 用 (y−ȳ)² 而非残差平方
  (路径已是 AR(1) 中位数序列, 无逐期残差可得);
- 自助 p 值 p = (1 + #{stat_b >= observed}) / (B + 1) (标准保守形式).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class BreakMonitorConfig:
    """断点监控配置 (默认值与 PipelineV2Config.break_monitor_* 对齐)."""
    method: str = 'sup_f'
    window: int = 250
    stride: int = 20
    min_points: int = 20
    trim: float = 0.15
    alpha: float = 0.05
    n_bootstrap: int = 400
    random_state: int = 42


class StructuralBreakMonitor:
    """只读结构突变监控器 (sup-F / CUSUM, AR(1) 代理自助 p 值)."""

    def __init__(self, config: Optional[BreakMonitorConfig] = None):
        self.config = config or BreakMonitorConfig()
        if self.config.method not in ('sup_f', 'cusum'):
            raise ValueError(
                f"method 必须为 'sup_f' 或 'cusum', 实际: {self.config.method!r}"
            )
        if not (0.0 < self.config.trim < 0.5):
            raise ValueError(
                f"trim 必须在 (0, 0.5) 开区间内, 实际: {self.config.trim!r}"
            )
        if self.config.alpha <= 0.0 or self.config.alpha >= 0.5:
            raise ValueError(
                f"alpha 必须在 (0, 0.5) 开区间内, 实际: {self.config.alpha!r}"
            )
        if self.config.n_bootstrap < 50:
            raise ValueError(
                f"n_bootstrap 必须 >= 50, 实际: {self.config.n_bootstrap!r}"
            )

    # ------------------------------------------------------------------
    # 统计量
    # ------------------------------------------------------------------

    def _sup_f_stat(self, y: np.ndarray, trim: float) -> Tuple[float, Optional[int]]:
        """未知断点 sup-F 型统计量 (两段均值模型, SSR 比值, 无 df 归一化).

        Returns:
            (stat, argmax_k) — argmax_k 为路径位置 (0-based); 无候选点时 (0.0, None).
        """
        n = len(y)
        k_lo = int(np.ceil(n * trim))
        k_hi = n - int(np.ceil(n * trim))
        if k_hi <= k_lo:
            return 0.0, None

        total_var = float(np.var(y))
        ssr0 = total_var * n  # 零模型 (单均值) 的 SSR
        best_stat, best_k = 0.0, None
        # 闭区间候选 [ceil(n*trim), n-ceil(n*trim)] (EXEC §7.1 要点 2)
        for k in range(k_lo, k_hi + 1):
            mu1 = float(np.mean(y[:k]))
            mu2 = float(np.mean(y[k:]))
            ssr1 = float(np.sum((y[:k] - mu1) ** 2) + np.sum((y[k:] - mu2) ** 2))
            denom = max(ssr1, 1e-12)  # 近常数段守卫 (1e-12 下限)
            stat = (ssr0 - ssr1) / denom
            if stat > best_stat:
                best_stat, best_k = stat, k
        return best_stat, best_k

    def _cusum_stat(self, y: np.ndarray) -> Tuple[float, Optional[int]]:
        """Inclán-Tiao (1994) ICSS 工程化变体: (y−ȳ)² 累积离差 D 统计量.

        Returns:
            (stat, argmax_k); s <= 1e-12 (近常数段) 时返回 (0.0, None).
        """
        n = len(y)
        z = (y - float(np.mean(y))) ** 2
        s = float(np.sum(z))
        if s <= 1e-12:
            return 0.0, None
        d = np.cumsum(z) / s
        stat_seq = np.abs(d - np.arange(1, n + 1) / n) * np.sqrt(n)
        k = int(np.argmax(stat_seq))
        return float(stat_seq[k]), k

    # ------------------------------------------------------------------
    # 零分布 (AR(1) 代理自助, 设计 m10)
    # ------------------------------------------------------------------

    def _bootstrap_pvalue(self, y: np.ndarray, observed_stat: float) -> float:
        """AR(1) 代理自助 p 值: p = (1 + #{stat_b >= observed}) / (B + 1)."""
        cfg = self.config
        rng = np.random.default_rng(cfg.random_state)
        n = len(y)

        # OLS 拟合 y_t = c + φ y_{t-1} + e_t → 保留自相关的代理生成参数
        y_lag, y_cur = y[:-1], y[1:]
        x = np.column_stack([np.ones(len(y_lag)), y_lag])
        try:
            beta = np.linalg.lstsq(x, y_cur, rcond=None)[0]
        except Exception:
            beta = np.array([float(np.mean(y)), 0.0])
        c, phi = float(beta[0]), float(beta[1])
        # |φ| >= 1 时平稳初值 c/(1-φ) 与 AR 递归会发散 → 截断到平稳域
        phi = float(np.clip(phi, -0.99, 0.99))
        resid = y_cur - (c + phi * y_lag)
        resid = resid - float(np.mean(resid))
        if len(resid) == 0 or float(np.std(resid)) <= 0.0:
            resid = np.ones(1)

        burn_in = 50
        count_ge = 0
        for _ in range(cfg.n_bootstrap):
            e = rng.choice(resid, size=n + burn_in, replace=True)
            sim = np.empty(n + burn_in)
            sim[0] = c / max(1.0 - phi, 1e-6) + e[0]  # 平稳初值近似
            for t in range(1, n + burn_in):
                sim[t] = c + phi * sim[t - 1] + e[t]
            proxy = sim[burn_in:]
            if cfg.method == 'sup_f':
                stat_b, _ = self._sup_f_stat(proxy, cfg.trim)
            else:
                stat_b, _ = self._cusum_stat(proxy)
            if stat_b >= observed_stat:
                count_ge += 1
        return (1.0 + count_ge) / (cfg.n_bootstrap + 1.0)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def detect(self, path: pd.Series) -> Dict[str, Any]:
        """对 AR(1) 路径执行断点检测 (只读, 不修改输入).

        Args:
            path: AR(1) 中位数路径 (compute_ar1_path 输出)

        Returns:
            告警字典; 数据不足时含 reason='insufficient data'.
        """
        if path is None or len(path) == 0:
            return self._insufficient()
        y = path.dropna().astype(float)
        if len(y) < self.config.min_points:
            return self._insufficient()

        if self.config.method == 'sup_f':
            stat, k = self._sup_f_stat(y.to_numpy(), self.config.trim)
        else:
            stat, k = self._cusum_stat(y.to_numpy())

        if stat <= 0.0 or k is None:
            return {
                'detected': False,
                'method': self.config.method,
                'stat': float(stat),
                'p_value': 1.0,
                'break_index': None,
                'break_date': None,
                'n_points': int(len(y)),
                'alpha': float(self.config.alpha),
            }

        p_value = self._bootstrap_pvalue(y.to_numpy(), stat)
        detected = bool(p_value < self.config.alpha)
        idx = int(k)
        return {
            'detected': detected,
            'method': self.config.method,
            'stat': float(stat),
            'p_value': float(p_value),
            'break_index': idx,
            'break_date': str(y.index[idx]),
            'n_points': int(len(y)),
            'alpha': float(self.config.alpha),
        }

    @staticmethod
    def _insufficient() -> Dict[str, Any]:
        return {
            'detected': False,
            'reason': 'insufficient data',
        }
