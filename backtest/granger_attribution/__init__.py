# -*- coding: utf-8 -*-
"""v3.1.0 E4 (§4): 格兰杰检验 (Toda-Yamamoto 1995) — 独立新模块.

Toda-Yamamoto 方法:
1. ADF 检验确定最高单整阶数 d
2. 估计 VAR(p+d) 模型
3. 对前 p 阶做 Wald 检验 (H0: 因子不 Granger-cause 收益)
4. Wald 统计量 ~ χ²(p)
5. contemporaneous_causality='unidentified' (诚实承认同期因果不可识别)

定位: "伪回归初筛过滤器", 非因果证明工具.
"""
from .toda_yamamoto import TodaYamamotoGrangerTester

__all__ = ['TodaYamamotoGrangerTester']
