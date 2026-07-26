# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E5 — AttributionAnalyzer 测试 (TDD Red)

测试三层归因分析 (指纹×处理×状态交互, 含 BH-FDR).

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 1363-1725

TDD 流程: Red (本文件) → Green (实现) → Review
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.backtest.attribution_analyzer import (
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


# ============================================================
# P2 补强测试: TestAttributionP2Strengthened (5 测试)
#
# 目的: 修复 audit §5 "设计约束无测试" — E5 现有测试仅验证接口存在,
#       未验证核心业务逻辑. 补强 5 个非平凡测试覆盖:
#       1. 已知关系识别 (gpd_shape → ic_mean, β=0.3)
#       2. 标准化 β 范围 (|β_std| ≤ 1)
#       3. 零权重零贡献 (Layer 2)
#       4. BH 单调性 (p_adjusted ≥ p_value)
#       5. 显著交互识别 (Layer 3)
# ============================================================

class TestAttributionP2Strengthened:
    """E5 P2 补强: 非平凡业务逻辑验证"""

    def test_P2_layer1_known_relation_gpd_shape(self, tmp_path):
        """P2-1: Layer 1 应识别已知强关系 (gpd_shape → ic_mean, β=0.3)

        _make_logger_dataframe 构造: ic_mean = 0.05 + 0.3 * gpd_shape + 0.01 * noise
        故 gpd_shape 对 ic_mean 的标准化 β 应显著大于其他维度.
        非平凡: 若 Layer 1 实现错误 (如未标准化 / 取错列), gpd_shape 的 β 不会凸显.
        """
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=80, seed=42)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer1_fingerprint_attribution()

        # gpd_shape 的 |beta_std| 应在 top 3
        abs_betas = {dim: abs(v['beta_std']) for dim, v in results.items()}
        sorted_dims = sorted(abs_betas.items(), key=lambda kv: -kv[1])
        top3_dims = {dim for dim, _ in sorted_dims[:3]}
        assert 'gpd_shape' in top3_dims, (
            f"gpd_shape 应在 top 3 (因构造 β=0.3), "
            f"实际 top 3: {top3_dims}, gpd_shape |β|={abs_betas.get('gpd_shape', 0):.4f}"
        )
        # gpd_shape 的 beta_std 应 > 0.3 (信号远大于 0.01 噪声)
        assert results['gpd_shape']['beta_std'] > 0.3, (
            f"gpd_shape beta_std={results['gpd_shape']['beta_std']:.4f} 应 > 0.3 "
            f"(构造关系 0.3 * gpd_shape + 0.01 * noise)"
        )

    def test_P2_layer1_beta_std_in_valid_range(self, tmp_path):
        """P2-2: 标准化回归系数 |beta_std| ≤ 1

        标准化 β = corr(x_std, y_std), 相关系数绝对值必 ≤ 1.
        非平凡: 若实现错误 (如未标准化 / 错误公式), β 可能 > 1.
        """
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=60, seed=42)
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer1_fingerprint_attribution()

        for dim, val in results.items():
            beta = val['beta_std']
            assert -1.0 <= beta <= 1.0, (
                f"维度 {dim} beta_std={beta:.4f} 超出 [-1, 1] "
                f"(标准化相关系数应有界)"
            )

    def test_P2_layer2_zero_weight_zero_contribution(self, tmp_path):
        """P2-3: 若某管道权重全 0, 则其方差贡献应 ≈ 0

        构造 weight_dynamic=0, weight_mixed=0, weight_static=1 的数据,
        Layer 2 应报告 dynamic/mixed 贡献 ≈ 0, static 贡献 ≈ 1.
        非平凡: 若 Layer 2 未正确消费权重, 零权重不会产生零贡献.
        """
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=60, seed=42)
        # 强制 weight_static=1, 其他=0
        df['weight_static'] = 1.0
        df['weight_dynamic'] = 0.0
        df['weight_mixed'] = 0.0
        analyzer.fit(df, performance_metric='ic_mean')
        results = analyzer.layer2_variance_attribution()

        assert results['dynamic'] < 0.01, (
            f"weight_dynamic=0 时贡献应 ≈ 0, 实际 {results['dynamic']:.4f}"
        )
        assert results['mixed'] < 0.01, (
            f"weight_mixed=0 时贡献应 ≈ 0, 实际 {results['mixed']:.4f}"
        )
        # static 应主导 (贡献 ≈ 1, 协方差项吸收舍入误差)
        assert results['static'] > 0.99, (
            f"weight_static=1 时贡献应 ≈ 1, 实际 {results['static']:.4f}"
        )

    def test_P2_layer3_bh_adjusted_ge_raw_pvalue(self, tmp_path):
        """P2-4: BH 校正后 p_adjusted ≥ 原始 p_value

        BH-FDR 公式 p_adj = p * K / rank ≥ p (因 K/rank ≥ 1),
        累积 min 后仍 ≥ p (单调性).
        非平凡: 若 BH 实现错误 (如 rank 反向), p_adjusted 可能 < p_value.
        """
        analyzer = AttributionAnalyzer(alpha=0.05, enable=True)
        df = _make_logger_dataframe(n_rows=80, n_regimes=2, seed=42)
        analyzer.fit(df, performance_metric='ic_mean')
        result_df = analyzer.layer3_interaction_attribution()

        assert len(result_df) > 0, "Layer 3 应返回非空结果"
        for _, row in result_df.iterrows():
            p_raw = float(row['p_value'])
            p_adj = float(row['p_adjusted'])
            assert p_adj >= p_raw - 1e-10, (
                f"BH 校正后 p_adjusted={p_adj:.6f} 应 ≥ 原始 p_value={p_raw:.6f} "
                f"(dim={row['dim']}, weight={row['weight_type']}, regime={row['regime']})"
            )
            # p_adjusted 应在 [0, 1]
            assert 0.0 <= p_adj <= 1.0, (
                f"p_adjusted={p_adj:.6f} 应在 [0, 1]"
            )

    def test_P2_layer3_significant_interaction_detected(self, tmp_path):
        """P2-5: 构造已知强交互效应, Layer 3 应识别为显著

        构造: ic_mean 在 regime='bull' 下与 gpd_shape × weight_static 强正相关,
        在 regime='bear' 下无关系. Layer 3 应在 bull 中识别显著交互.
        非平凡: 若 Layer 3 未正确拟合交互项, 无法区分 regime 内的交互效应.
        """
        rng = np.random.default_rng(123)
        n_per_regime = 40
        rows = []
        for regime in ['bull', 'bear']:
            for i in range(n_per_regime):
                gpd_val = float(rng.standard_normal() * 0.5)
                w_static = float(rng.uniform(0.3, 0.9))
                # bull: ic_mean = 强交互项 (gpd * w * 2.0) + 噪声
                # bear: ic_mean = 纯噪声 (无交互)
                if regime == 'bull':
                    ic_mean = 0.05 + 2.0 * gpd_val * w_static + 0.01 * rng.standard_normal()
                else:
                    ic_mean = 0.05 + 0.01 * rng.standard_normal()
                row = {
                    'factor_name': f'{regime}_{i:03d}',
                    'timestamp': '2024-01-01',
                    'regime': regime,
                    'gpd_shape': gpd_val,
                    'weight_static': w_static,
                    'weight_dynamic': float(1.0 - w_static) * 0.5,
                    'weight_mixed': float(1.0 - w_static) * 0.5,
                    'ic_mean': ic_mean,
                }
                # 填充其余 20 维指纹 (避免缺失)
                for f in FINGERPRINT_FIELDS:
                    if f not in row:
                        row[f] = float(rng.standard_normal() * 0.1)
                # 填充其余表现字段
                row.setdefault('ic_std', 0.1)
                row.setdefault('ic_ir', 0.5)
                row.setdefault('turnover', 0.3)
                row.setdefault('max_drawdown', -0.15)
                row.setdefault('sharpe_ratio', 1.0)
                rows.append(row)
        df = pd.DataFrame(rows)

        analyzer = AttributionAnalyzer(alpha=0.1, enable=True)  # alpha=0.1 提高检测灵敏度
        analyzer.fit(df, performance_metric='ic_mean')
        result_df = analyzer.layer3_interaction_attribution()

        assert len(result_df) > 0, "Layer 3 应返回非空结果"
        # 筛选 gpd_shape × weight_static × bull 的交互项
        target_rows = result_df[
            (result_df['dim'] == 'gpd_shape')
            & (result_df['weight_type'] == 'weight_static')
            & (result_df['regime'] == 'bull')
        ]
        assert len(target_rows) > 0, (
            "应包含 (gpd_shape, weight_static, bull) 交互项"
        )
        # 该交互项应显著 (因构造 β=2.0 强交互)
        sig_row = target_rows.iloc[0]
        assert bool(sig_row['is_significant']), (
            f"bull regime 中 gpd_shape × weight_static 交互应显著 "
            f"(构造 β=2.0), 实际 p_adjusted={sig_row['p_adjusted']:.6f}"
        )
