# -*- coding: utf-8 -*-
"""v3.4.1: 非生产路径解耦器弃用契约 (TDD).

背景: `OptimizedARDecoupler` / `TemporalDecoupler` / `OptimizedCompositeDecoupler`
为零生产调用且使用全样本 AR 拟合 (同类前视, ADR-040 范围外)。
v3.4.1 起保留公开导入但构造即发 DeprecationWarning, 引导至因果实现。
"""
import unittest

import numpy as np
import pandas as pd

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from factor_pipeline.modules.factor_decoupler import (
    OptimizedARDecoupler,
    OptimizedCompositeDecoupler,
    TemporalDecoupler,
    decouple_ar,
)


def _panel(n: int = 60, k: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        rng.normal(size=(n, k)),
        index=pd.date_range('2020-01-01', periods=n, freq='D'),
        columns=[f'S{i}' for i in range(k)],
    )


class TestDeprecatedNonProdDecouplers(unittest.TestCase):
    """构造/调用即告警; 公开导入保持可用."""

    def test_optimized_ar_decoupler_warns(self):
        with self.assertWarns(DeprecationWarning) as cm:
            OptimizedARDecoupler()
        self.assertIn('ARDecoupler', str(cm.warning))

    def test_optimized_composite_decoupler_warns(self):
        with self.assertWarns(DeprecationWarning) as cm:
            OptimizedCompositeDecoupler()
        self.assertIn('CompositeDecoupler', str(cm.warning))

    def test_temporal_decoupler_warns(self):
        with self.assertWarns(DeprecationWarning) as cm:
            TemporalDecoupler()
        self.assertIn('ARDecoupler', str(cm.warning))

    def test_decouple_ar_function_warns(self):
        with self.assertWarns(DeprecationWarning):
            decouple_ar(_panel())


if __name__ == '__main__':
    unittest.main()
