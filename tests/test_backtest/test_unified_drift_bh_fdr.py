# -*- coding: utf-8 -*-
"""unified_drift.py _compute_rolling_structure_drift BH-FDR 修复测试 (v3.0.0 T3.5)

验证 T3.5 修复: 滑动窗口 KS 多重检验校正.

修复前: ~504 次 KS 检验仅 p<0.05 过滤, 假阳性 ~25 个
修复后: 默认 BH-FDR 校正, 假阳性控制

TDD: 测试验证修复后的行为.
"""
import pytest
import numpy as np

from backtest.unified_drift import UnifiedDriftReporter as UnifiedDriftDetector


class TestRollingStructureDriftBHFD:

    def test_01_no_drift_returns_zero_with_bh(self):
        """无漂移数据应返回 0 (BH-FDR 校正后无误报)"""
        np.random.seed(42)
        # 无漂移数据
        ic_series = np.random.normal(0, 0.05, 500)
        detector = UnifiedDriftDetector({
            'rolling_window': 60,
            'rolling_pvalue': 0.05,
            'rolling_correction_method': 'benjamini_hochberg',
        })
        score = detector._compute_rolling_structure_drift(ic_series)
        # 无漂移时, BH 校正后应无显著, score=0
        assert score == 0.0, f"无漂移数据 BH 校正后 score={score} 应为 0"

    def test_02_no_drift_none_correction_may_have_false_positive(self):
        """无漂移数据, correction='none' 可能有假阳性 (旧路径行为)"""
        np.random.seed(42)
        ic_series = np.random.normal(0, 0.05, 500)
        detector = UnifiedDriftDetector({
            'rolling_window': 60,
            'rolling_pvalue': 0.05,
            'rolling_correction_method': 'none',
        })
        score = detector._compute_rolling_structure_drift(ic_series)
        # 旧路径可能有假阳性, 不强制为 0 (只测试不崩溃)
        assert score >= 0.0

    def test_03_real_drift_detected_with_bh(self):
        """真实漂移应被 BH-FDR 检测"""
        np.random.seed(42)
        # 前 250 期 N(0, 0.05), 后 250 期 N(0.15, 0.05) — 明显漂移
        ic_series = np.concatenate([
            np.random.normal(0, 0.05, 250),
            np.random.normal(0.15, 0.05, 250),
        ])
        detector = UnifiedDriftDetector({
            'rolling_window': 60,
            'rolling_pvalue': 0.05,
            'rolling_correction_method': 'benjamini_hochberg',
        })
        score = detector._compute_rolling_structure_drift(ic_series)
        # 真实漂移应被检测
        assert score > 0.0, f"真实漂移 BH 校正后 score={score} 应 > 0"

    def test_04_bh_more_conservative_than_none(self):
        """BH 校正应比 none 更保守 (无漂移数据下 score ≤ none)"""
        np.random.seed(42)
        # 多个 seed 测试
        bh_scores = []
        none_scores = []
        for seed in range(10):
            np.random.seed(seed)
            ic_series = np.random.normal(0, 0.05, 400)
            # BH
            detector_bh = UnifiedDriftDetector({
                'rolling_window': 50,
                'rolling_pvalue': 0.05,
                'rolling_correction_method': 'benjamini_hochberg',
            })
            bh_scores.append(detector_bh._compute_rolling_structure_drift(ic_series))
            # none
            detector_none = UnifiedDriftDetector({
                'rolling_window': 50,
                'rolling_pvalue': 0.05,
                'rolling_correction_method': 'none',
            })
            none_scores.append(detector_none._compute_rolling_structure_drift(ic_series))
        # BH 应更保守: 平均 score ≤ none
        assert np.mean(bh_scores) <= np.mean(none_scores), (
            f"BH 平均 score {np.mean(bh_scores)} 应 ≤ none {np.mean(none_scores)}"
        )

    def test_05_bonferroni_most_conservative(self):
        """Bonferroni 应最保守 (score ≤ BH ≤ none)"""
        np.random.seed(42)
        ic_series = np.random.normal(0, 0.05, 400)
        scores = {}
        for method in ['none', 'benjamini_hochberg', 'bonferroni']:
            detector = UnifiedDriftDetector({
                'rolling_window': 50,
                'rolling_pvalue': 0.05,
                'rolling_correction_method': method,
            })
            scores[method] = detector._compute_rolling_structure_drift(ic_series)
        # Bonferroni ≤ BH ≤ none (在无漂移数据下)
        assert scores['bonferroni'] <= scores['benjamini_hochberg'] + 1e-6, (
            f"Bonferroni {scores['bonferroni']} 应 ≤ BH {scores['benjamini_hochberg']}"
        )
