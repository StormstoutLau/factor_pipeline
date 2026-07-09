# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E5 — AttributionAnalyzer 测试 (TDD Red)

测试三层归因分析 (指纹×处理×状态交互, 含 BH-FDR).

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 1363-1725

TDD 流程: Red (本文件) → Green (实现) → Review
"""
import pytest
import numpy as np
import pandas as pd

from backtest.attribution_analyzer import (
    AttributionAnalyzer,
    FINGERPRINT_FIELDS,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_logger_dataframe(n_rows: int = 60, n_regimes: int = 2, seed: int = 42) -> pd.DataFrame:
    """构造模拟 E4 FingerprintPerformanceLogger.query() 输出的 DataFrame

    含: 21 指纹字段 + 6 表现字段 + 3 管道权重字段 + factor_name/timestamp/regime
    """
    rng = np.random.default_rng(seed)
    regimes = ['bull', 'bear', 'neutral'][:n_regimes]
    rows = []
    for i in range(n_rows):
        row = {
            'factor_name': f'factor_{i:03d}',
            'timestamp': '2024-01-01',
            'regime': regimes[i % n_regimes],
        }
        # 21 指纹字段 (随机值, 不同方差以避免共线性)
        for j, f in enumerate(FINGERPRINT_FIELDS):
            row[f] = float(rng.standard_normal() * (0.1 + 0.05 * j))
        # 6 表现字段 — ic_mean 与 gpd_shape 强相关 (构造已知关系)
        gpd_val = row['gpd_shape']
        row['ic_mean'] = float(0.05 + 0.3 * gpd_val + 0.01 * rng.standard_normal())
        row['ic_std'] = float(0.1 + 0.02 * rng.standard_normal())
        row['ic_ir'] = float(0.5 + 0.1 * rng.standard_normal())
        row['turnover'] = float(0.3 + 0.05 * rng.standard_normal())
        row['max_drawdown'] = float(-0.15 + 0.03 * rng.standard_normal())
        row['sharpe_ratio'] = float(1.0 + 0.2 * rng.standard_normal())
        # 3 管道权重 (每行归一化到和为 1)
        w_raw = np.array([0.4, 0.3, 0.3]) + 0.05 * rng.standard_normal(3)
        w_raw = np.clip(w_raw, 0.05, 0.9)
        w_raw = w_raw / w_raw.sum()
        row['weight_static'] = float(w_raw[0])
        row['weight_dynamic'] = float(w_raw[1])
        row['weight_mixed'] = float(w_raw[2])
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================
# 测试类: TestAttributionAnalyzer (11 测试)
# ============================================================

class TestAttributionAnalyzer:
    """E5 AttributionAnalyzer TDD 测试"""

    # ---------- 1. fit 接口 ----------

    def test_fit_accepts_dataframe(self, tmp_path):
        """fit() 接受 E4 query() 输出的 DataFrame"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=30)
        # 不报错即可
        analyzer.fit(df, performance_metric='ic_mean')
        assert analyzer._data is not None
        assert len(analyzer._data) == 30

    def test_fit_returns_self(self, tmp_path):
        """fit() 返回 self"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=30)
        result = analyzer.fit(df, performance_metric='ic_mean')
        assert result is analyzer

    # ---------- 2. Layer 1 指纹归因 ----------

    def test_layer1_returns_dict(self, tmp_path):
        """layer1_fingerprint_attribution() 返回 Dict[str, Dict]"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=40)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer1_fingerprint_attribution()
        assert isinstance(results, dict)
        assert len(results) > 0
        for dim, val in results.items():
            assert isinstance(dim, str)
            assert isinstance(val, dict)
            assert 'beta_std' in val

    def test_layer1_contains_all_21_dims(self, tmp_path):
        """Layer 1 含 21 维指纹维度"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=40)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer1_fingerprint_attribution()
        # 所有 21 维都应被分析 (样本充足)
        assert len(results) == 21, (
            f"Layer 1 应返回 21 维, 实际 {len(results)}: {list(results.keys())}"
        )
        for f in FINGERPRINT_FIELDS:
            assert f in results, f"维度 {f} 不在 Layer 1 结果中"

    # ---------- 3. Layer 2 方差归因 ----------

    def test_layer2_returns_dict(self, tmp_path):
        """layer2_variance_attribution() 返回 Dict[str, float]"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=40)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer2_variance_attribution()
        assert isinstance(results, dict)
        assert len(results) > 0
        for k, v in results.items():
            assert isinstance(k, str)
            assert isinstance(v, float)

    def test_layer2_weights_sum_to_one(self, tmp_path):
        """Layer 2 方差贡献归一化 (和为 1)"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=40)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer2_variance_attribution()
        assert 'static' in results
        assert 'dynamic' in results
        assert 'mixed' in results
        total = sum(results.values())
        assert abs(total - 1.0) < 1e-6, f"Layer 2 贡献和应为 1.0, 实际 {total}"

    # ---------- 4. Layer 3 交互归因 ----------

    def test_layer3_returns_dataframe(self, tmp_path):
        """layer3_interaction_attribution() 返回 DataFrame"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=60, n_regimes=2)
        analyzer.fit(df, performance_metric='ic_mean')
        result_df = analyzer.layer3_interaction_attribution()
        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) > 0

    def test_layer3_contains_bh_fdr(self, tmp_path):
        """Layer 3 含 BH-FDR 校正列 ('p_adjusted', 'is_significant')"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=60, n_regimes=2)
        analyzer.fit(df, performance_metric='ic_mean')
        result_df = analyzer.layer3_interaction_attribution()
        assert 'p_adjusted' in result_df.columns, "缺少 p_adjusted 列"
        assert 'is_significant' in result_df.columns, "缺少 is_significant 列"
        # is_significant 应为 bool 类型
        assert result_df['is_significant'].dtype == bool

    # ---------- 5. 诊断 ----------

    def test_get_diagnostics(self, tmp_path):
        """get_diagnostics() 返回 dict 含关键键"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=40)
        analyzer.fit(df, performance_metric='ic_mean')
        analyzer.layer1_fingerprint_attribution()
        diag = analyzer.get_diagnostics()
        assert isinstance(diag, dict)
        assert 'enabled' in diag
        assert 'n_records' in diag
        assert diag['n_records'] == 40
        assert 'performance_metric' in diag

    # ---------- 6. 开关与边界 ----------

    def test_disabled_no_op(self, tmp_path):
        """enable=False 时所有方法返回空"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=False)
        df = _make_logger_dataframe(n_rows=40)
        # fit 仍可调用 (存储数据)
        analyzer.fit(df, performance_metric='ic_mean')
        # 但 layer 方法返回空
        assert analyzer.layer1_fingerprint_attribution() == {}
        assert analyzer.layer2_variance_attribution() == {}
        l3 = analyzer.layer3_interaction_attribution()
        assert isinstance(l3, pd.DataFrame)
        assert len(l3) == 0

    def test_empty_data_handling(self, tmp_path):
        """空数据输入不崩溃"""
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        empty_df = pd.DataFrame()
        analyzer.fit(empty_df, performance_metric='ic_mean')
        # 所有方法返回空, 不报错
        assert analyzer.layer1_fingerprint_attribution() == {}
        assert analyzer.layer2_variance_attribution() == {}
        l3 = analyzer.layer3_interaction_attribution()
        assert isinstance(l3, pd.DataFrame)
        assert len(l3) == 0
        # 诊断也不崩溃
        diag = analyzer.get_diagnostics()
        assert isinstance(diag, dict)
