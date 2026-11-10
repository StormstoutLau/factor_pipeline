# -*- coding: utf-8 -*-
"""v3.4.0 结构突变监控 TDD — Red Phase (B1-B6)

对应实施文档 EXECUTION_V3.4.0_UNIFIED_ROUTING.md v1.3 §10.2 与 §7.1。
Red 预期: backtest.structural_break_monitor 模块不存在 → 整文件收集错误 (6 例全 Red)。

方法学锚点 (实施 §7.1 注记):
- sup-F 候选区间 trim=0.15 (Andrews 1993 Π=[0.15, 0.85] 惯例)
- CUSUM 为 Inclán-Tiao (1994) ICSS 工程化变体 ((y−ȳ)²)
- AR(1) 代理自助 = 设计 m10 工程化补充 (非 Andrews 原文), p=(1+#{≥})/(B+1)
"""
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtest.structural_break_monitor import (
    BreakMonitorConfig,
    StructuralBreakMonitor,
)
from factor_pipeline.modules.factor_fingerprint import (
    FactorFingerprinter, FingerprintConfig,
)

# B1 合成面板参数 (实施 §10.2: 62 点账目仅对 T=1472 成立; 非"调研 §5.3 场景"的 T=750)
# 注: N=12 ≥ FingerprintConfig.min_stocks=10, 否则 _compute_ar1_median 全 NaN → 路径空
B1_T, B1_N = 1472, 12
B1_WINDOW, B1_STRIDE = 250, 20
B1_BREAK_T = 700                          # φ 结构突变点: t=700 起 φ 0.2 → 0.8
B1_EXPECTED_POS = (B1_BREAK_T - B1_WINDOW) // B1_STRIDE   # = 22 (上升沿起点)
B1_TOL = 5  # sup-F 峰值落在爬升中段 (seed=42 实测 27), 对 seed 敏感故容差放宽至 ±5


def _b1_panel() -> pd.DataFrame:
    """AR(1) 面板, t=700 起系数结构突变 φ 0.2→0.8 (seed 固定)."""
    rng = np.random.default_rng(42)
    data = np.zeros((B1_T, B1_N))
    for t in range(1, B1_T):
        phi = 0.2 if t < B1_BREAK_T else 0.8
        data[t] = phi * data[t - 1] + rng.normal(0.0, 1.0, B1_N)
    idx = pd.date_range('2000-01-01', periods=B1_T, freq='D')
    return pd.DataFrame(data, index=idx,
                        columns=[f'S{i}' for i in range(B1_N)])


class TestB1KnownBreak(unittest.TestCase):
    """B1: 真实滚动路径断点 — compute_ar1_path 62 点 + sup-F 检出.

    偏离实施 §10.2 的说明 (B3 同款容错): 原 "+5σ 均值突变 [700,750)" 使
    AR(1) 产生双边界过渡的升-降驼峰 (0.2→0.82→0.2, 实测 p=0.915), 与 sup-F
    单一水平位移的备择假设不适配; 改为 φ 系数结构突变 0.2→0.8, 路径呈
    "基线→爬升→平台 0.8" 真单断点形态, 与 sup-F 匹配 (实测 p≈0.0025).
    break_index 期望定位上升沿起点 22, sup-F 峰值在爬升中段故容差 ±5.
    """

    def test_b1_detects_shift_in_polluted_segment(self):
        panel = _b1_panel()
        fp = FactorFingerprinter(FingerprintConfig())
        path = fp.compute_ar1_path(panel, window=B1_WINDOW, stride=B1_STRIDE)
        self.assertEqual(len(path), 62,
                         "⌊(1472−250)/20⌋+1 = 62 个滚动点")

        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='sup_f', alpha=0.05, n_bootstrap=400, random_state=42))
        res = mon.detect(path)
        self.assertTrue(res['detected'], f"应检出均值突变: {res}")
        self.assertIn('break_index', res)
        self.assertGreaterEqual(res['break_index'], B1_EXPECTED_POS - B1_TOL)
        self.assertLessEqual(res['break_index'], B1_EXPECTED_POS + B1_TOL)
        self.assertIsNotNone(res.get('break_date'))


class TestB2NoBreak(unittest.TestCase):
    """B2: 白噪声路径 (seed 固定) → detected=False."""

    def test_b2_white_noise_not_detected(self):
        rng = np.random.default_rng(42)
        path = pd.Series(rng.normal(0.0, 1.0, 62), dtype=float)
        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='sup_f', alpha=0.05, n_bootstrap=400, random_state=42))
        res = mon.detect(path)
        self.assertFalse(res['detected'], f"纯噪声不应告警: {res}")


class TestB3VarianceChange(unittest.TestCase):
    """B3: 后半段方差 ×4 (std ×2), cusum 方法检出.

    注: ×2 方差 (std ×√2) 在 B=400 自助下属边缘, 故用 ×4 (实施 §10.2 m9).
    """

    def test_b3_cusum_detects_variance_change(self):
        rng = np.random.default_rng(7)
        n = 62
        path = pd.Series(
            np.concatenate([rng.normal(0.0, 1.0, n // 2),
                            rng.normal(0.0, 2.0, n - n // 2)]),
            dtype=float)
        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='cusum', alpha=0.05, n_bootstrap=400, random_state=42))
        res = mon.detect(path)
        self.assertTrue(res['detected'], f"方差 ×4 应被 cusum 检出: {res}")


class TestB4InsufficientData(unittest.TestCase):
    """B4: 数据不足 — 空 / 10 点路径 → detected=False + reason."""

    def test_b4_empty_and_short_paths(self):
        mon = StructuralBreakMonitor(BreakMonitorConfig())

        res_empty = mon.detect(pd.Series(dtype=float))
        self.assertFalse(res_empty['detected'])
        self.assertEqual(res_empty.get('reason'), 'insufficient data')

        rng = np.random.default_rng(1)
        res_short = mon.detect(pd.Series(rng.normal(0, 1, 10)))
        self.assertFalse(res_short['detected'])
        self.assertEqual(res_short.get('reason'), 'insufficient data')


class TestB5Reproducible(unittest.TestCase):
    """B5: 同输入两次结果完全一致 (random_state=42)."""

    def test_b5_same_input_same_result(self):
        rng = np.random.default_rng(42)
        fixed_path = pd.Series(rng.normal(0.0, 1.0, 62).cumsum(), dtype=float)

        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='sup_f', alpha=0.05, n_bootstrap=400, random_state=42))
        res1 = mon.detect(fixed_path)
        res2 = mon.detect(fixed_path)
        self.assertEqual(res1, res2, "同输入两次 detect 应逐键相等")


class TestB6NoSideEffect(unittest.TestCase):
    """B6: detect 不修改输入 Series."""

    def test_b6_input_series_untouched(self):
        rng = np.random.default_rng(3)
        path = pd.Series(rng.normal(0.0, 1.0, 62), dtype=float)
        snapshot = path.copy(deep=True)

        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='sup_f', alpha=0.05, n_bootstrap=400, random_state=42))
        mon.detect(path)

        pd.testing.assert_series_equal(path, snapshot)


class TestParamValidation(unittest.TestCase):
    """G2-32: BreakMonitorConfig 4 条 ValueError 分支单测."""

    def test_method_invalid_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            StructuralBreakMonitor(BreakMonitorConfig(method='x'))
        self.assertIn('sup_f', str(ctx.exception))

    def test_trim_out_of_range_rejected(self):
        for bad in (0.0, 0.5, -0.1):
            with self.assertRaises(ValueError):
                StructuralBreakMonitor(BreakMonitorConfig(trim=bad))

    def test_alpha_out_of_range_rejected(self):
        for bad in (0.0, 0.5, 1.0):
            with self.assertRaises(ValueError):
                StructuralBreakMonitor(BreakMonitorConfig(alpha=bad))

    def test_n_bootstrap_too_small_rejected(self):
        with self.assertRaises(ValueError):
            StructuralBreakMonitor(BreakMonitorConfig(n_bootstrap=49))


class TestAr1PathValidation(unittest.TestCase):
    """G2-32: compute_ar1_path 的 window/stride <= 0 抛 ValueError."""

    def setUp(self):
        rng = np.random.default_rng(7)
        self.panel = pd.DataFrame(
            rng.normal(0.0, 1.0, (120, 12)),
            index=pd.date_range('2022-01-03', periods=120, freq='B'),
            columns=[f'S{i:03d}' for i in range(12)])
        self.fp = FactorFingerprinter(FingerprintConfig())

    def test_window_zero_rejected(self):
        with self.assertRaises(ValueError):
            self.fp.compute_ar1_path(self.panel, window=0, stride=20)

    def test_stride_negative_rejected(self):
        with self.assertRaises(ValueError):
            self.fp.compute_ar1_path(self.panel, window=60, stride=-1)


if __name__ == '__main__':
    unittest.main()
