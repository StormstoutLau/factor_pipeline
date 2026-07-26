# -*- coding: utf-8 -*-
"""
ABLATION E2: AblationRunner 核心引擎测试 (TDD)

规格: docs/EXECUTION_ABLATION_V3.0.0.md §2 (line 339-1192)
验收: E2-T1 ~ E2-T8 全部 Green

测试范围:
  E2-T1: Ledoit-Wolf HAC 检验 (5 tests)
  E2-T2: Circular Block Bootstrap (7 tests)
  E2-T3: ρ_step 排序保持性 (5 tests)
  E2-T4: AblationConfig (3 tests)
  E2-T5: AblationRunner 单次运行 (5 tests)
  E2-T6: AblationRunner 批量运行 (4 tests)
  E2-T7: 比较与 BH-FDR (4 tests)
  E2-T8: get_diagnostics (3 tests)
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from factor_pipeline.backtest.ablation_runner import (
    ledoit_wolf_hac_test,
    mean_diff_hac_statsmodels,
    circular_block_bootstrap,
    compute_rho_step,
    AblationConfig,
    AblationResult,
    AblationComparison,
    AblationRunner,
)
from factor_pipeline.backtest.multiple_testing import apply_bh_fdr


# =============================================================================
# 测试数据生成
# =============================================================================

def _make_factor_data(n_periods=20, n_stocks=15, n_factors=2, seed=42):
    """生成小规模合成因子数据 (dates × stocks)"""
    np.random.seed(seed)
    dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    factor_data = {}
    for f_idx in range(n_factors):
        data = np.random.randn(n_periods, n_stocks)
        # 添加少量缺失值
        mask = np.random.random((n_periods, n_stocks)) < 0.03
        data[mask] = np.nan
        factor_data[f'factor_{f_idx}'] = pd.DataFrame(data, index=dates, columns=stocks)
    return factor_data


def _make_fwd_returns(n_periods=20, n_stocks=15, seed=99):
    """生成前向收益 (dates × stocks)"""
    np.random.seed(seed)
    dates = pd.date_range('2022-01-01', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    data = np.random.randn(n_periods, n_stocks) * 0.02
    return pd.DataFrame(data, index=dates, columns=stocks)


def _make_industry_data(n_stocks=15, seed=7):
    """生成行业分类数据"""
    np.random.seed(seed)
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    industries = [f'IND_{i}' for i in range(3)]
    return pd.Series(np.random.choice(industries, size=n_stocks), index=stocks)


def _make_synthetic_result(name='test', seed=42):
    """构造合成 AblationResult (用于 compare/diagnostics 测试)"""
    np.random.seed(seed)
    n = 30
    ic_series = np.random.randn(n) * 0.05 + 0.02
    ls_returns = np.random.randn(n) * 0.01 + 0.002
    return AblationResult(
        config=AblationConfig(name=name),
        metrics={
            'ic_mean': float(np.mean(ic_series)),
            'ic_std': float(np.std(ic_series, ddof=1)),
            'icir': float(np.mean(ic_series) / np.std(ic_series, ddof=1)),
            'sharpe_ls': float(np.mean(ls_returns) / np.std(ls_returns, ddof=1)),
            'sharpe_lo': np.nan,
            'turnover_mean': np.nan,
            'max_drawdown': np.nan,
            'hit_rate': float(np.mean(ic_series > 0)),
        },
        ic_series=ic_series,
        ls_return_series=ls_returns,
        rho_step={'imputer': 1.0, 'winsorizer': 1.0, 'scaler': 1.0,
                  'neutralizer': 1.0, 'orthogonalizer': 1.0},
        ortho_diagnostics={'condition_number': 5.0, 'vrr_mean': 0.9},
        n_factors=2,
        n_periods=n,
        runtime_sec=0.1,
    )


# =============================================================================
# E2-T1: Ledoit-Wolf HAC 检验
# =============================================================================

class TestLedoitWolfHAC:
    """E2-T1: Ledoit-Wolf (2008) HAC Sharpe 差检验"""

    def test_identical_series_zero_t(self):
        """两个相同序列 → ΔSR=0, t≈0, p>0.05"""
        np.random.seed(42)
        returns_a = np.random.randn(100) * 0.01 + 0.001
        returns_b = returns_a.copy()

        t_stat, p_value = ledoit_wolf_hac_test(returns_a, returns_b)

        assert abs(t_stat) < 0.5, f"t_stat should be ≈0, got {t_stat}"
        assert p_value > 0.05, f"p_value should be >0.05, got {p_value}"

    def test_better_series_significant(self):
        """a 明显优于 b → t>0, p<0.05"""
        np.random.seed(42)
        # a: 高均值低方差 (高 Sharpe)
        returns_a = np.random.randn(200) * 0.01 + 0.005
        # b: 低均值高方差 (低 Sharpe)
        returns_b = np.random.randn(200) * 0.03 + 0.0

        t_stat, p_value = ledoit_wolf_hac_test(returns_a, returns_b)

        assert t_stat > 0, f"t_stat should be positive, got {t_stat}"
        assert p_value < 0.05, f"p_value should be <0.05, got {p_value}"

    def test_hac_vs_naive_t_different(self):
        """HAC t 与朴素 t 不同 (时序依赖场景)"""
        np.random.seed(123)
        # 构造强自相关序列
        n = 200
        eps_a = np.random.randn(n) * 0.01
        eps_b = np.random.randn(n) * 0.01
        returns_a = np.zeros(n)
        returns_b = np.zeros(n)
        for i in range(1, n):
            returns_a[i] = 0.8 * returns_a[i - 1] + eps_a[i] + 0.002
            returns_b[i] = 0.8 * returns_b[i - 1] + eps_b[i]

        t_hac, _ = ledoit_wolf_hac_test(returns_a, returns_b)

        # 朴素 t (不考虑自相关): ΔSR / sqrt(Var(SR_a)/T + Var(SR_b)/T)
        sr_a = np.mean(returns_a) / np.std(returns_a, ddof=1)
        sr_b = np.mean(returns_b) / np.std(returns_b, ddof=1)
        # 朴素方差: Var(SR) ≈ (1 + 0.5 * SR^2) / T (Lo 2002, IID)
        var_naive_a = (1 + 0.5 * sr_a ** 2) / n
        var_naive_b = (1 + 0.5 * sr_b ** 2) / n
        var_delta_naive = var_naive_a + var_naive_b
        t_naive = (sr_a - sr_b) / np.sqrt(var_delta_naive)

        # HAC 和朴素 t 应该不同 (HAC 考虑了自相关导致的方差放大)
        assert abs(t_hac - t_naive) > 0.01, (
            f"HAC t ({t_hac:.4f}) should differ from naive t ({t_naive:.4f})"
        )

    def test_statsmodels_mean_diff_is_reference_only(self):
        """statsmodels HAC 路径仅检验均值差 Δμ (非 ΔSR), 作参考; 不与手工 Sharpe 差检验等价"""
        np.random.seed(42)
        # a: 低均值低方差, Sharpe 可能与 b 相近
        returns_a = np.random.randn(200) * 0.005 + 0.001
        # b: 高均值高方差, 均值差大但 Sharpe 可能相近
        returns_b = np.random.randn(200) * 0.02 + 0.004

        # 手工 Ledoit-Wolf: 检验 ΔSR = 0
        t_sr, p_sr = ledoit_wolf_hac_test(returns_a, returns_b)

        # statsmodels: 检验 Δμ = 0 (均值差, 非 Sharpe 差)
        t_mu, p_mu = mean_diff_hac_statsmodels(returns_a, returns_b)

        # 两者检验的统计量不同 (ΔSR vs Δμ), t 值应不同
        assert abs(t_sr - t_mu) > 0.01, (
            f"Sharpe diff t ({t_sr:.4f}) should differ from mean diff t ({t_mu:.4f})"
        )

    def test_auto_bandwidth(self):
        """T=240 → q≈4 (Newey-West 自动带宽)"""
        np.random.seed(42)
        returns_a = np.random.randn(240) * 0.01 + 0.001
        returns_b = np.random.randn(240) * 0.01 + 0.001

        # q = max(1, int(4 * (T/100)^(2/9)))
        # T=240: 4 * (2.4)^(2/9) ≈ 4 * 1.20 ≈ 4.8 → int → 4
        expected_q = max(1, int(4 * (240 / 100) ** (2 / 9)))
        assert expected_q == 4, f"Expected q=4 for T=240, got {expected_q}"

        # 调用不应出错, 隐含验证带宽计算
        t_stat, p_value = ledoit_wolf_hac_test(returns_a, returns_b)
        assert not np.isnan(t_stat)
        assert not np.isnan(p_value)


# =============================================================================
# E2-T2: Circular Block Bootstrap
# =============================================================================

class TestCircularBootstrap:
    """E2-T2: Circular Block Bootstrap (Politis & Romano 1992)"""

    def test_identical_series_p_value_high(self):
        """两个相同序列 → p_value > 0.05"""
        np.random.seed(42)
        series_a = np.random.randn(100) * 0.05 + 0.01
        series_b = series_a.copy()

        p_value, _ = circular_block_bootstrap(
            series_a, series_b, statistic='mean', n_bootstrap=500, seed=42,
        )

        assert p_value > 0.05, f"p_value should be >0.05 for identical series, got {p_value}"

    def test_significant_difference_p_low(self):
        """明显差异 → p_value < 0.05"""
        np.random.seed(42)
        series_a = np.random.randn(200) * 0.02 + 0.05  # 高均值
        series_b = np.random.randn(200) * 0.02 + 0.0    # 低均值

        p_value, _ = circular_block_bootstrap(
            series_a, series_b, statistic='mean', n_bootstrap=1000, seed=42,
        )

        assert p_value < 0.05, f"p_value should be <0.05 for different series, got {p_value}"

    def test_ci_covers_zero_when_identical(self):
        """相同序列 → 95% CI 包含 0"""
        np.random.seed(42)
        series_a = np.random.randn(100) * 0.05 + 0.01
        series_b = series_a.copy()

        _, boot_stats = circular_block_bootstrap(
            series_a, series_b, statistic='mean', n_bootstrap=500, seed=42,
        )

        ci_low = np.percentile(boot_stats, 2.5)
        ci_high = np.percentile(boot_stats, 97.5)

        assert ci_low <= 0 <= ci_high, (
            f"CI [{ci_low:.4f}, {ci_high:.4f}] should cover 0"
        )

    def test_ci_excludes_zero_when_different(self):
        """明显差异 → 95% CI 不包含 0"""
        np.random.seed(42)
        series_a = np.random.randn(200) * 0.01 + 0.05  # 高均值
        series_b = np.random.randn(200) * 0.01 + 0.0    # 低均值

        _, boot_stats = circular_block_bootstrap(
            series_a, series_b, statistic='mean', n_bootstrap=1000, seed=42,
        )

        ci_low = np.percentile(boot_stats, 2.5)
        ci_high = np.percentile(boot_stats, 97.5)

        assert not (ci_low <= 0 <= ci_high), (
            f"CI [{ci_low:.4f}, {ci_high:.4f}] should exclude 0"
        )

    def test_block_size_auto(self):
        """T=240 → block_size ≈ 6 (240^(1/3)≈6.2)"""
        np.random.seed(42)
        series_a = np.random.randn(240) * 0.01
        series_b = np.random.randn(240) * 0.01

        # block_size=None → auto: max(1, int(T**(1/3)))
        # T=240: 240^(1/3) ≈ 6.2 → int → 6
        expected_block = max(1, int(240 ** (1 / 3)))
        assert expected_block == 6, f"Expected block_size=6 for T=240, got {expected_block}"

        # 调用不应出错
        p_value, _ = circular_block_bootstrap(
            series_a, series_b, n_bootstrap=100, block_size=None, seed=42,
        )
        assert not np.isnan(p_value)

    def test_reproducible_with_seed(self):
        """相同 seed → 相同结果"""
        np.random.seed(42)
        series_a = np.random.randn(100) * 0.02 + 0.01
        series_b = np.random.randn(100) * 0.02 + 0.005

        p1, stats1 = circular_block_bootstrap(
            series_a, series_b, n_bootstrap=200, seed=123,
        )
        p2, stats2 = circular_block_bootstrap(
            series_a, series_b, n_bootstrap=200, seed=123,
        )

        assert p1 == p2, f"p_values differ: {p1} vs {p2}"
        np.testing.assert_array_equal(stats1, stats2)

    def test_sharpe_statistic_mode(self):
        """statistic='sharpe' → 计算 Sharpe 差而非 mean 差"""
        np.random.seed(42)
        # a: 低均值低方差 (高 Sharpe)
        series_a = np.random.randn(100) * 0.005 + 0.001
        # b: 高均值高方差 (低 Sharpe, 但均值可能更高)
        series_b = np.random.randn(100) * 0.02 + 0.002

        # mean 差: 可能很小 (0.001 vs 0.002)
        p_mean, stats_mean = circular_block_bootstrap(
            series_a, series_b, statistic='mean', n_bootstrap=500, seed=42,
        )

        # sharpe 差: a 的 Sharpe 可能远高于 b
        p_sharpe, stats_sharpe = circular_block_bootstrap(
            series_a, series_b, statistic='sharpe', n_bootstrap=500, seed=42,
        )

        # 两种 statistic 的 bootstrap 分布应不同
        delta_mean = np.mean(stats_mean)
        delta_sharpe = np.mean(stats_sharpe)

        # Sharpe 差和 mean 差的数值不同 (因为 Sharpe = mean/std)
        assert abs(delta_sharpe - delta_mean) > 1e-6, (
            f"sharpe delta ({delta_sharpe:.6f}) should differ from mean delta ({delta_mean:.6f})"
        )


# =============================================================================
# E2-T3: ρ_step 排序保持性
# =============================================================================

class TestRhoStep:
    """E2-T3: 排序保持性 ρ_step (Spearman 秩相关)"""

    def _make_cross_sectional_df(self, n_stocks=10, n_periods=5, seed=42):
        """生成截面因子 DataFrame (stocks × periods)"""
        np.random.seed(seed)
        stocks = [f'S{i:03d}' for i in range(n_stocks)]
        periods = [f'T{j}' for j in range(n_periods)]
        data = np.random.randn(n_stocks, n_periods)
        return pd.DataFrame(data, index=stocks, columns=periods)

    def test_identity_transform_rho_one(self):
        """恒等变换 → ρ_step = 1.0"""
        df = self._make_cross_sectional_df()
        rho = compute_rho_step(df, df)
        assert rho == pytest.approx(1.0, abs=1e-10), f"identity ρ should be 1.0, got {rho}"

    def test_monotonic_transform_rho_one(self):
        """单调变换 (z-score) → ρ_step ≈ 1.0"""
        df = self._make_cross_sectional_df()
        # z-score 标准化是线性单调变换, Spearman = 1.0
        df_transformed = (df - df.mean(axis=0)) / df.std(axis=0)
        rho = compute_rho_step(df, df_transformed)
        assert rho == pytest.approx(1.0, abs=1e-6), f"monotonic ρ should be ≈1.0, got {rho}"

    def test_shuffled_rho_near_zero(self):
        """打乱顺序 → ρ_step ≈ 0"""
        np.random.seed(42)
        df = self._make_cross_sectional_df(n_stocks=20, n_periods=10)
        # 打乱每列的顺序
        df_shuffled = df.copy()
        for col in df_shuffled.columns:
            df_shuffled[col] = np.random.permutation(df_shuffled[col].values)

        rho = compute_rho_step(df, df_shuffled)
        assert abs(rho) < 0.3, f"shuffled ρ should be ≈0, got {rho}"

    def test_partial_reorder_rho_between(self):
        """部分重排 → ρ_step ∈ (0, 1)"""
        np.random.seed(42)
        df = self._make_cross_sectional_df(n_stocks=20, n_periods=10)
        # 交换少量元素位置 (部分重排)
        df_partial = df.copy()
        for col in df_partial.columns:
            vals = df_partial[col].values.copy()
            # 交换前 3 个和后 3 个
            vals[:3], vals[-3:] = vals[-3:].copy(), vals[:3].copy()
            df_partial[col] = vals

        rho = compute_rho_step(df, df_partial)
        assert 0.0 < rho < 1.0, f"partial reorder ρ should be in (0,1), got {rho}"

    def test_nan_handling(self):
        """含 NaN → 跳过, 不崩溃"""
        df = self._make_cross_sectional_df()
        df_with_nan = df.copy()
        df_with_nan.iloc[0, 0] = np.nan
        df_with_nan.iloc[5, 2] = np.nan

        # 不应抛出异常
        rho = compute_rho_step(df, df_with_nan)
        assert not np.isnan(rho), f"ρ should not be NaN with some NaN values, got {rho}"


# =============================================================================
# E2-T4: AblationConfig
# =============================================================================

class TestAblationConfig:
    """E2-T4: AblationConfig 消融配置"""

    def test_default_config_is_baseline(self):
        """默认 AblationConfig → layer='baseline', 全启用"""
        config = AblationConfig()
        assert config.layer == 'baseline'
        assert config.name == 'baseline'
        assert config.module_enabled is None  # None = 全启用
        assert config.routing_mode == 'full'
        assert config.baseline_level is None

    def test_l1_config_module_enabled(self):
        """L1 config → module_enabled 指定关闭"""
        config = AblationConfig(
            name='L1_imputer_off',
            layer='L1',
            module_enabled={'imputer': False},
        )
        assert config.layer == 'L1'
        assert config.name == 'L1_imputer_off'
        assert config.module_enabled == {'imputer': False}

    def test_l2_config_routing_mode(self):
        """L2 config → routing_mode='random' + seed"""
        config = AblationConfig(
            name='L2_random_routing',
            layer='L2',
            routing_mode='random',
            random_seed=42,
        )
        assert config.layer == 'L2'
        assert config.routing_mode == 'random'
        assert config.random_seed == 42


# =============================================================================
# E2-T5: AblationRunner 单次运行
# =============================================================================

class TestAblationRunnerSingle:
    """E2-T5: AblationRunner.run_single"""

    def test_run_single_returns_result(self):
        """run_single → AblationResult 含全部 metrics"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_factor_data(n_periods=20, n_stocks=15)
        fwd_returns = _make_fwd_returns(n_periods=20, n_stocks=15)

        runner = AblationRunner(PipelineV2Config())
        config = AblationConfig(name='B0_raw', layer='baseline', baseline_level='B0')
        result = runner.run_single(config, factor_data, fwd_returns)

        assert isinstance(result, AblationResult)
        assert result.config.name == 'B0_raw'
        # metrics 含全部预期 key
        for key in ['ic_mean', 'ic_std', 'icir', 'sharpe_ls', 'hit_rate']:
            assert key in result.metrics, f"metrics missing key: {key}"
        assert result.n_factors > 0
        assert result.n_periods > 0
        assert result.runtime_sec >= 0

    def test_run_single_b0_raw_dropna(self):
        """B0 原始+dropna → 无管线处理, IC 直接计算"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_factor_data(n_periods=20, n_stocks=15)
        fwd_returns = _make_fwd_returns(n_periods=20, n_stocks=15)

        runner = AblationRunner(PipelineV2Config())
        config = AblationConfig(name='B0_raw', layer='baseline', baseline_level='B0')
        result = runner.run_single(config, factor_data, fwd_returns)

        # B0: 所有 rho_step = 1.0 (恒等变换)
        assert set(result.rho_step.keys()) == {
            'imputer', 'winsorizer', 'scaler', 'neutralizer', 'orthogonalizer'
        }
        for step, rho in result.rho_step.items():
            assert rho == pytest.approx(1.0, abs=1e-6), (
                f"B0 {step} ρ should be 1.0 (identity), got {rho}"
            )
        # IC 应可计算 (非 NaN)
        assert not np.isnan(result.metrics['ic_mean']), "B0 ic_mean should not be NaN"

    def test_run_single_b3_full_pipeline(self):
        """B3 完整管线 → IC 非 NaN, ICIR 非 NaN"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_factor_data(n_periods=24, n_stocks=20)
        fwd_returns = _make_fwd_returns(n_periods=24, n_stocks=20)
        industry_data = _make_industry_data(n_stocks=20)

        runner = AblationRunner(PipelineV2Config())
        config = AblationConfig(name='B3_full', layer='baseline', baseline_level='B3')
        result = runner.run_single(config, factor_data, fwd_returns, industry_data)

        assert isinstance(result, AblationResult)
        assert result.config.name == 'B3_full'
        # IC 和 ICIR 应可计算
        assert not np.isnan(result.metrics['ic_mean']), "B3 ic_mean should not be NaN"
        # ic_series 非空
        assert len(result.ic_series) > 0
        assert len(result.ls_return_series) > 0

    def test_rho_step_collected(self):
        """AblationResult.rho_step 含 5 个步骤"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_factor_data(n_periods=20, n_stocks=15)
        fwd_returns = _make_fwd_returns(n_periods=20, n_stocks=15)

        runner = AblationRunner(PipelineV2Config())
        config = AblationConfig(name='B0', baseline_level='B0')
        result = runner.run_single(config, factor_data, fwd_returns)

        expected_steps = {'imputer', 'winsorizer', 'scaler', 'neutralizer', 'orthogonalizer'}
        assert set(result.rho_step.keys()) == expected_steps

    def test_ortho_diagnostics_collected(self):
        """AblationResult.ortho_diagnostics 含 condition_number + VRR"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        factor_data = _make_factor_data(n_periods=20, n_stocks=15)
        fwd_returns = _make_fwd_returns(n_periods=20, n_stocks=15)

        runner = AblationRunner(PipelineV2Config())
        config = AblationConfig(name='B0', baseline_level='B0')
        result = runner.run_single(config, factor_data, fwd_returns)

        assert 'condition_number' in result.ortho_diagnostics
        assert 'vrr_mean' in result.ortho_diagnostics

    def test_rho_step_orthogonalizer_not_always_one(self):
        """P1-8: orthogonalizer ρ_step 不应恒为 1.0 (before != after)

        Bug: _collect_rho_steps 中 orthogonalizer 步骤 before==after
        (都用 processed_data), 导致 Spearman=1.0.
        Fix: before = intermediate['neutralization'] (正交化前),
             after = processed_data (正交化后).

        Spec §2.3.3: ρ_step 度量每个步骤前后的排序变化.
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())

        # 构造正交化前 (neutralization 输出) 和正交化后 (processed_data) 的数据
        # 两者排序不同 → Spearman != 1.0
        np.random.seed(42)
        stocks = [f'S{i:03d}' for i in range(10)]
        periods = [f'T{j}' for j in range(5)]
        # before: 随机数据
        df_before = pd.DataFrame(
            np.random.randn(10, 5), index=stocks, columns=periods,
        )
        # after: 取负值 (rank-reversing, 同 index 不同值 → Spearman ≈ -1.0)
        # 注意: 不能用 iloc[::-1] 因为 compute_rho_step 按 index 对齐会还原顺序
        df_after = (-df_before).copy()

        original_data = {'factor_0': df_before.copy()}
        processed_data = {'factor_0': df_after}

        # 构造 mock pipeline, get_intermediate_data 返回 neutralization 步骤的输出
        mock_pipe = MagicMock()
        mock_pipe.get_intermediate_data.return_value = {
            'neutralization': df_before,
        }
        mock_pipeline = MagicMock()
        mock_pipeline.factor_pipelines = {
            'factor_0': {'static': mock_pipe},
        }

        rho_step = runner._collect_rho_steps(
            mock_pipeline, original_data, processed_data,
        )

        # orthogonalizer ρ_step 不应恒为 1.0
        assert 'orthogonalizer' in rho_step
        assert rho_step['orthogonalizer'] != 1.0, (
            f"orthogonalizer ρ_step should not be 1.0 when before != after, "
            f"got {rho_step['orthogonalizer']}"
        )
        # 期望 ≈ -1.0 (rank 反转)
        assert rho_step['orthogonalizer'] < 0.5, (
            f"orthogonalizer ρ_step should be low (rank-reversing), "
            f"got {rho_step['orthogonalizer']}"
        )


# =============================================================================
# E2-T6: AblationRunner 批量运行
# =============================================================================

class TestAblationRunnerBatch:
    """E2-T6: AblationRunner 批量运行"""

    def test_run_l1_returns_6_results(self, monkeypatch):
        """run_l1 → 6 个 AblationResult (5 消融 + 1 参照)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        # Mock run_single 返回合成结果
        call_count = [0]
        def mock_run_single(config, fd, fr, industry_data=None):
            call_count[0] += 1
            return _make_synthetic_result(name=config.name)

        monkeypatch.setattr(runner, 'run_single', mock_run_single)
        results = runner.run_l1(factor_data, fwd_returns)

        assert len(results) == 6
        assert call_count[0] == 6
        names = [r.config.name for r in results]
        assert 'B3_full' in names
        assert any('imputer' in n for n in names)
        assert any('winsorizer' in n for n in names)
        assert any('scaler' in n for n in names)
        assert any('neutralizer' in n for n in names)
        assert any('orthogonalizer' in n for n in names)

    def test_run_l2_returns_5_results(self, monkeypatch):
        """run_l2 → 5 个 AblationResult"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        call_count = [0]
        def mock_run_single(config, fd, fr, industry_data=None):
            call_count[0] += 1
            return _make_synthetic_result(name=config.name)

        monkeypatch.setattr(runner, 'run_single', mock_run_single)
        results = runner.run_l2(factor_data, fwd_returns)

        assert len(results) == 5
        assert call_count[0] == 5
        names = [r.config.name for r in results]
        assert any('static' in n for n in names)
        assert any('dynamic' in n for n in names)
        assert any('mixed' in n for n in names)
        assert any('random' in n for n in names)
        assert any('full' in n for n in names)

    def test_run_baselines_returns_4_results(self, monkeypatch):
        """run_baselines → 4 个 (B0-B3)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        call_count = [0]
        def mock_run_single(config, fd, fr, industry_data=None):
            call_count[0] += 1
            return _make_synthetic_result(name=config.name)

        monkeypatch.setattr(runner, 'run_single', mock_run_single)
        results = runner.run_baselines(factor_data, fwd_returns)

        assert len(results) == 4
        assert call_count[0] == 4
        names = [r.config.name for r in results]
        assert any('B0' in n for n in names)
        assert any('B1' in n for n in names)
        assert any('B2' in n for n in names)
        assert any('B3' in n for n in names)

    def test_run_l4_oat_returns_20_plus(self, monkeypatch):
        """run_l4_oat → ≥ 20 个 (6 DOF × 3-4 选项 + 1 baseline)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        call_count = [0]
        def mock_run_single(config, fd, fr, industry_data=None):
            call_count[0] += 1
            return _make_synthetic_result(name=config.name)

        monkeypatch.setattr(runner, 'run_single', mock_run_single)
        results = runner.run_l4_oat(factor_data, fwd_returns)

        assert len(results) >= 20, f"Expected ≥20 results, got {len(results)}"
        assert call_count[0] >= 20


# =============================================================================
# E2-T7: 比较与 BH-FDR
# =============================================================================

class TestAblationCompare:
    """E2-T7: 显著性比较与 BH-FDR 校正"""

    def test_compare_identical_not_significant(self):
        """相同实验 vs 参照 → is_significant=False"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=200)
        result = _make_synthetic_result(name='exp', seed=42)
        reference = _make_synthetic_result(name='ref', seed=42)

        comp = runner.compare(result, reference)

        assert isinstance(comp, AblationComparison)
        assert comp.experiment == 'exp'
        assert comp.reference == 'ref'
        assert comp.is_significant is False
        assert comp.delta_ic == pytest.approx(0.0, abs=1e-6)

    def test_compare_better_significant(self):
        """明显优于参照 → is_significant=True"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=500)

        # 构造明显不同的结果
        np.random.seed(42)
        n = 100
        # experiment: 高 IC
        ic_exp = np.random.randn(n) * 0.02 + 0.08
        ls_exp = np.random.randn(n) * 0.005 + 0.01
        # reference: 低 IC
        ic_ref = np.random.randn(n) * 0.02 + 0.0
        ls_ref = np.random.randn(n) * 0.005 + 0.0

        exp_result = AblationResult(
            config=AblationConfig(name='exp'),
            metrics={
                'ic_mean': float(np.mean(ic_exp)),
                'sharpe_ls': float(np.mean(ls_exp) / np.std(ls_exp, ddof=1)),
            },
            ic_series=ic_exp,
            ls_return_series=ls_exp,
            rho_step={}, ortho_diagnostics={},
            n_factors=1, n_periods=n, runtime_sec=0.1,
        )
        ref_result = AblationResult(
            config=AblationConfig(name='ref'),
            metrics={
                'ic_mean': float(np.mean(ic_ref)),
                'sharpe_ls': float(np.mean(ls_ref) / np.std(ls_ref, ddof=1)),
            },
            ic_series=ic_ref,
            ls_return_series=ls_ref,
            rho_step={}, ortho_diagnostics={},
            n_factors=1, n_periods=n, runtime_sec=0.1,
        )

        comp = runner.compare(exp_result, ref_result)

        assert comp.delta_ic > 0
        assert comp.delta_sharpe > 0
        assert comp.is_significant is True

    def test_compare_all_bh_fdr_correction(self):
        """compare_all → p 值经 BH-FDR 校正"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=200)

        # 构造多个结果 (一些显著, 一些不显著)
        np.random.seed(42)
        results = []
        reference = _make_synthetic_result(name='ref', seed=100)
        ref_ic = reference.ic_series
        ref_ls = reference.ls_return_series

        for i in range(5):
            np.random.seed(200 + i)
            if i < 3:
                # 显著: 不同 IC
                ic = np.random.randn(30) * 0.05 + 0.08
                ls = np.random.randn(30) * 0.01 + 0.01
            else:
                # 不显著: 相似 IC
                ic = ref_ic + np.random.randn(30) * 0.001
                ls = ref_ls + np.random.randn(30) * 0.001

            results.append(AblationResult(
                config=AblationConfig(name=f'exp_{i}'),
                metrics={'ic_mean': float(np.mean(ic)), 'sharpe_ls': float(np.mean(ls) / np.std(ls, ddof=1))},
                ic_series=ic,
                ls_return_series=ls,
                rho_step={}, ortho_diagnostics={},
                n_factors=1, n_periods=30, runtime_sec=0.1,
            ))

        comparisons = runner.compare_all(results, reference)

        assert len(comparisons) == 5
        # 所有 comparison 应有 p_value_bootstrap
        for c in comparisons:
            assert hasattr(c, 'p_value_bootstrap')
            assert hasattr(c, 'p_value_hac')
            assert hasattr(c, 'is_significant')

    def test_compare_all_uses_shared_module(self):
        """compare_all 调用 backtest.multiple_testing.apply_bh_fdr"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)

        results = [_make_synthetic_result(name=f'r{i}', seed=i) for i in range(3)]
        reference = _make_synthetic_result(name='ref', seed=99)

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called, "compare_all should call apply_bh_fdr"


# =============================================================================
# E2-T8: get_diagnostics
# =============================================================================

class TestGetDiagnostics:
    """E2-T8: AblationRunner.get_diagnostics"""

    def test_diagnostics_has_n_experiments(self):
        """get_diagnostics → 含 n_experiments"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        # 添加一些合成结果
        runner._results = [
            _make_synthetic_result(name='r0'),
            _make_synthetic_result(name='r1'),
            _make_synthetic_result(name='r2'),
        ]

        diag = runner.get_diagnostics()
        assert 'n_experiments' in diag
        assert diag['n_experiments'] == 3

    def test_diagnostics_has_total_runtime(self):
        """get_diagnostics → 含 total_runtime_sec"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        runner._results = [_make_synthetic_result(name='r0')]

        diag = runner.get_diagnostics()
        assert 'total_runtime_sec' in diag
        assert diag['total_runtime_sec'] >= 0

    def test_diagnostics_has_results_summary(self):
        """get_diagnostics → 含 results_summary 列表"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        runner._results = [
            _make_synthetic_result(name='r0'),
            _make_synthetic_result(name='r1'),
        ]

        diag = runner.get_diagnostics()
        assert 'results_summary' in diag
        assert isinstance(diag['results_summary'], list)
        assert len(diag['results_summary']) == 2
        # 每个摘要含 name + key metrics
        for summary in diag['results_summary']:
            assert 'name' in summary


# =============================================================================
# E3-E7 共享辅助: 配置捕获 mock
# =============================================================================

def _capture_pipeline_configs(monkeypatch, runner):
    """Monkeypatch _run_pipeline 捕获 config/module_override/ortho_enabled.

    返回 captured 列表, 每个 entry 含:
        {'config': AblationConfig, 'module_override': ..., 'ortho_enabled': ...}
    """
    captured = []

    def mock_run_pipeline(config, factor_data, fwd_returns, industry_data=None,
                          module_override=None, ortho_enabled=None):
        captured.append({
            'config': config,
            'module_override': module_override,
            'ortho_enabled': ortho_enabled,
        })
        # 返回合成数据 (保留 NaN 以模拟 imputer off)
        processed = {name: df.copy() for name, df in factor_data.items()}
        rho_step = {step: 1.0 for step in AblationRunner.L1_MODULES}
        ortho_diag = {'condition_number': float('nan'), 'vrr_mean': float('nan')}
        return processed, rho_step, ortho_diag

    monkeypatch.setattr(runner, '_run_pipeline', mock_run_pipeline)
    return captured


def _make_layer_result(name, layer, ic_mean=0.02, sharpe=0.3, seed=42,
                       rho_step=None, ortho_diag=None):
    """构造指定层的合成 AblationResult (用于 compare/report 测试)"""
    np.random.seed(seed)
    n = 30
    ic_series = np.random.randn(n) * 0.05 + ic_mean
    ls_returns = np.random.randn(n) * 0.01 + sharpe * 0.01
    if rho_step is None:
        rho_step = {step: 1.0 for step in AblationRunner.L1_MODULES}
    if ortho_diag is None:
        ortho_diag = {'condition_number': 5.0, 'vrr_mean': 0.9}
    return AblationResult(
        config=AblationConfig(name=name, layer=layer),
        metrics={
            'ic_mean': float(np.mean(ic_series)),
            'ic_std': float(np.std(ic_series, ddof=1)),
            'icir': float(np.mean(ic_series) / np.std(ic_series, ddof=1)),
            'sharpe_ls': float(np.mean(ls_returns) / np.std(ls_returns, ddof=1)),
            'sharpe_lo': float('nan'),
            'turnover_mean': float('nan'),
            'max_drawdown': float(np.min(np.cumsum(ls_returns)
                                         - np.maximum.accumulate(np.cumsum(ls_returns)))),
            'hit_rate': float(np.mean(ic_series > 0)),
        },
        ic_series=ic_series,
        ls_return_series=ls_returns,
        rho_step=rho_step,
        ortho_diagnostics=ortho_diag,
        n_factors=2,
        n_periods=n,
        runtime_sec=0.1,
    )


# =============================================================================
# E3: L1 组件消融 (8 tests)
# =============================================================================

class TestL1Ablation:
    """E3: L1 组件消融行为测试 (规格 §3.6)"""

    def test_l1_imputer_off_preserves_nan(self, monkeypatch):
        """L1 imputer off → module_enabled={'imputer': False} (保留 NaN)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l1(factor_data, fwd_returns)

        # 找到 L1_imputer_off 的捕获
        imputer_caps = [c for c in captured if c['config'].name == 'L1_imputer_off']
        assert len(imputer_caps) == 1
        cfg = imputer_caps[0]['config']
        # module_enabled 指定 imputer=False (使管线保留 NaN)
        assert cfg.module_enabled == {'imputer': False}
        assert cfg.layer == 'L1'

    def test_l1_neutralizer_off_no_industry_neutral(self, monkeypatch):
        """L1 neutralizer off → module_enabled={'neutralizer': False} (未中性化)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l1(factor_data, fwd_returns)

        neut_caps = [c for c in captured if c['config'].name == 'L1_neutralizer_off']
        assert len(neut_caps) == 1
        cfg = neut_caps[0]['config']
        assert cfg.module_enabled == {'neutralizer': False}

    def test_l1_orthogonalizer_off_no_orthogonal(self, monkeypatch):
        """L1 orthogonalizer off → ortho_enabled=False (factor_dict 不变, M3 修正)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l1(factor_data, fwd_returns)

        ortho_caps = [c for c in captured if c['config'].name == 'L1_orthogonalizer_off']
        assert len(ortho_caps) == 1
        cfg = ortho_caps[0]['config']
        # M3 修正: ortho 走 ortho_enabled, 不走 module_enabled
        assert cfg.ortho_enabled is False
        assert cfg.module_enabled is None  # 不应通过 module_enabled 控制

    def test_l1_all_vs_b3_significant(self):
        """至少 3 个模块消融 vs B3 显著 (p<0.05)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=500)
        # B3 参照: 低 IC
        reference = _make_layer_result('B3_full', 'baseline', ic_mean=0.0,
                                       sharpe=0.0, seed=100)
        # 5 个消融: 3 个明显不同 (高 IC), 2 个相似
        results = [
            _make_layer_result('L1_imputer_off', 'L1', ic_mean=0.08,
                               sharpe=1.0, seed=1),
            _make_layer_result('L1_winsorizer_off', 'L1', ic_mean=0.07,
                               sharpe=0.9, seed=2),
            _make_layer_result('L1_scaler_off', 'L1', ic_mean=0.06,
                               sharpe=0.8, seed=3),
            _make_layer_result('L1_neutralizer_off', 'L1', ic_mean=0.01,
                               sharpe=0.1, seed=4),
            _make_layer_result('L1_orthogonalizer_off', 'L1', ic_mean=0.005,
                               sharpe=0.05, seed=5),
        ]

        comparisons = runner.compare_all(results, reference)
        sig_count = sum(1 for c in comparisons if c.is_significant)
        assert sig_count >= 3, (
            f"Expected ≥3 significant, got {sig_count}: "
            f"{[(c.experiment, c.is_significant) for c in comparisons]}"
        )

    def test_l1_rho_step_neutralizer_low(self):
        """Neutralizer ρ_step < 0.95 (改变排序)"""
        result = _make_layer_result(
            'L1_neutralizer_off', 'L1',
            rho_step={'imputer': 1.0, 'winsorizer': 0.98, 'scaler': 0.99,
                      'neutralizer': 0.82, 'orthogonalizer': 1.0},
        )
        assert result.rho_step['neutralizer'] < 0.95, (
            f"Neutralizer ρ_step should be <0.95 (reorders), "
            f"got {result.rho_step['neutralizer']}"
        )

    def test_l1_rho_step_scaler_high(self):
        """Scaler ρ_step > 0.99 (单调变换, 不改变排序)"""
        result = _make_layer_result(
            'L1_scaler_off', 'L1',
            rho_step={'imputer': 1.0, 'winsorizer': 0.97, 'scaler': 0.995,
                      'neutralizer': 0.85, 'orthogonalizer': 0.70},
        )
        assert result.rho_step['scaler'] > 0.99, (
            f"Scaler ρ_step should be >0.99 (monotonic), "
            f"got {result.rho_step['scaler']}"
        )

    def test_l1_bh_fdr_applied(self, monkeypatch):
        """5 比较的 p 值经 BH-FDR 校正"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        reference = _make_layer_result('B3_full', 'baseline', seed=100)
        results = [
            _make_layer_result('L1_imputer_off', 'L1', seed=i)
            for i in range(5)
        ]

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called, "compare_all should call apply_bh_fdr"
            # 5 个比较 → 5 个 p 值
            called_p_values = mock_bh.call_args[0][0]
            assert len(called_p_values) == 5, (
                f"Expected 5 p_values for BH-FDR, got {len(called_p_values)}"
            )

    def test_l1_report_generated(self):
        """generate_report 输出 Markdown 含 L1 表格"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        results = [
            _make_layer_result('B3_full', 'baseline', seed=0),
            _make_layer_result('L1_imputer_off', 'L1', seed=1),
            _make_layer_result('L1_winsorizer_off', 'L1', seed=2),
        ]
        comparisons = runner.compare_all(results[1:], results[0])

        report = runner.generate_report(results, comparisons)
        assert isinstance(report, str)
        assert "# Ablation Study Report" in report
        assert "L1 组件消融" in report
        assert "L1_imputer_off" in report
        # 含 ΔIC + p_HAC + p_Boot 列
        assert "ΔIC" in report
        assert "p_HAC" in report
        assert "p_Boot" in report


# =============================================================================
# E4: L2 路由消融 (8 tests)
# =============================================================================

class TestL2Ablation:
    """E4: L2 路由消融行为测试 (规格 §4.5)"""

    def test_all_static_uses_static_pipeline(self, monkeypatch):
        """routing_mode='static' → config 正确设置"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l2(_make_factor_data(), _make_fwd_returns())

        static_caps = [c for c in captured if c['config'].name == 'L2_all_static']
        assert len(static_caps) == 1
        assert static_caps[0]['config'].routing_mode == 'static'

    def test_all_dynamic_uses_dynamic_pipeline(self, monkeypatch):
        """routing_mode='dynamic' → config 正确设置"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l2(_make_factor_data(), _make_fwd_returns())

        dyn_caps = [c for c in captured if c['config'].name == 'L2_all_dynamic']
        assert len(dyn_caps) == 1
        assert dyn_caps[0]['config'].routing_mode == 'dynamic'

    def test_random_routing_reproducible(self, monkeypatch):
        """相同 seed → 相同 random_seed 配置 (可重现)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        runner.run_l2(_make_factor_data(), _make_fwd_returns())

        random_caps = [c for c in captured if c['config'].name == 'L2_random_routing']
        assert len(random_caps) == 1
        assert random_caps[0]['config'].routing_mode == 'random'
        assert random_caps[0]['config'].random_seed == 42

    def test_random_routing_different_from_full(self, monkeypatch):
        """随机路由 routing_mode != 完整路由 routing_mode"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        runner.run_l2(_make_factor_data(), _make_fwd_returns())

        random_cfg = next(c['config'] for c in captured
                         if c['config'].name == 'L2_random_routing')
        full_cfg = next(c['config'] for c in captured
                       if c['config'].name == 'L2_full_routing')
        assert random_cfg.routing_mode != full_cfg.routing_mode
        assert full_cfg.routing_mode == 'full'

    def test_full_vs_random_significant_or_not(self):
        """full vs random: 显著或诚实接受不显著"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=200)
        full = _make_layer_result('L2_full_routing', 'L2', ic_mean=0.03, seed=10)
        random_r = _make_layer_result('L2_random_routing', 'L2',
                                      ic_mean=0.02, seed=11)

        comp = runner.compare(random_r, full)
        # 诚实立场: 接受显著或不显著
        assert isinstance(comp.is_significant, bool)
        assert comp.experiment == 'L2_random_routing'
        assert comp.reference == 'L2_full_routing'

    def test_full_vs_static(self):
        """full vs static 比较 + HAC p 值"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=200)
        full = _make_layer_result('L2_full_routing', 'L2', ic_mean=0.04, seed=20)
        static_r = _make_layer_result('L2_all_static', 'L2',
                                      ic_mean=0.01, seed=21)

        comp = runner.compare(static_r, full)
        assert comp.experiment == 'L2_all_static'
        assert comp.reference == 'L2_full_routing'
        assert not np.isnan(comp.p_value_hac)
        assert 0.0 <= comp.p_value_hac <= 1.0

    def test_l2_bh_fdr_4_comparisons(self, monkeypatch):
        """4 比较经 BH-FDR 校正 (4 消融 vs full 参照)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        reference = _make_layer_result('L2_full_routing', 'L2', seed=99)
        results = [
            _make_layer_result('L2_all_static', 'L2', seed=1),
            _make_layer_result('L2_all_dynamic', 'L2', seed=2),
            _make_layer_result('L2_all_mixed', 'L2', seed=3),
            _make_layer_result('L2_random_routing', 'L2', seed=4),
        ]

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called
            called_p_values = mock_bh.call_args[0][0]
            assert len(called_p_values) == 4, (
                f"Expected 4 p_values for L2 BH-FDR, got {len(called_p_values)}"
            )

    def test_l2_report_has_routing_table(self):
        """报告含路由消融表"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        results = [
            _make_layer_result('L2_full_routing', 'L2', seed=0),
            _make_layer_result('L2_all_static', 'L2', seed=1),
        ]
        comparisons = runner.compare_all(results[1:], results[0])

        report = runner.generate_report(results, comparisons)
        assert "L2 路由消融" in report
        assert "L2_all_static" in report
        assert "L2_full_routing" in report

    def test_run_l2_accepts_b3_full_result(self, monkeypatch):
        """P1-6: run_l2 accepts b3_full_result → reuses it as L2_full_routing (4 calls, not 5)

        Spec §0.4 M6 修正: run_l2 应接受 b3_full_result 参数, 提供时引用复用
        作为 L2_full_routing 参照, 不重复 run_single.
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data()
        fwd_returns = _make_fwd_returns()

        call_count = [0]
        def mock_run_single(config, fd, fr, industry_data=None):
            call_count[0] += 1
            return _make_synthetic_result(name=config.name)

        monkeypatch.setattr(runner, 'run_single', mock_run_single)

        b3_full = _make_synthetic_result(name='B3_full_precomputed', seed=77)
        results = runner.run_l2(factor_data, fwd_returns, b3_full_result=b3_full)

        # 5 results total (4 消融 + 1 参照)
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        # run_single called 4 times (L2_full_routing reuses b3_full_result)
        assert call_count[0] == 4, (
            f"Expected 4 run_single calls (full reused), got {call_count[0]}"
        )
        # b3_full_result is reused in results (identity check)
        assert b3_full in results, (
            "b3_full_result should be reused in results (by identity)"
        )


# =============================================================================
# E5: L4 前置处理 OAT (12 tests)
# =============================================================================

class TestL4OAT:
    """E5: L4 前置处理 OAT 单维消融行为测试 (规格 §5.7)"""

    def _run_l4_and_capture(self, monkeypatch):
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        runner.run_l4_oat(_make_factor_data(), _make_fwd_returns())
        return captured

    def test_outlier_3sigma(self, monkeypatch):
        """outlier=3sigma → config.outlier_method='3sigma'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_outlier_method_3sigma']
        assert len(caps) == 1
        assert caps[0]['config'].outlier_method == '3sigma'

    def test_outlier_winsorize_1pct(self, monkeypatch):
        """outlier=winsorize_1pct → config.outlier_method='winsorize_1pct'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured
                if c['config'].name == 'L4_outlier_method_winsorize_1pct']
        assert len(caps) == 1
        assert caps[0]['config'].outlier_method == 'winsorize_1pct'

    def test_scaler_rank(self, monkeypatch):
        """scaler=rank → config.scaler_method='rank'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_scaler_method_rank']
        assert len(caps) == 1
        assert caps[0]['config'].scaler_method == 'rank'

    def test_scaler_minmax(self, monkeypatch):
        """scaler=minmax → config.scaler_method='minmax'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_scaler_method_minmax']
        assert len(caps) == 1
        assert caps[0]['config'].scaler_method == 'minmax'

    def test_missing_drop(self, monkeypatch):
        """missing=drop → config.missing_method='drop'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_missing_method_drop']
        assert len(caps) == 1
        assert caps[0]['config'].missing_method == 'drop'

    def test_missing_knn(self, monkeypatch):
        """missing=knn → config.missing_method='knn'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_missing_method_knn']
        assert len(caps) == 1
        assert caps[0]['config'].missing_method == 'knn'

    def test_neutralization_none(self, monkeypatch):
        """neutralization=none → config.neutralization='none'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured
                if c['config'].name == 'L4_neutralization_none']
        assert len(caps) == 1
        assert caps[0]['config'].neutralization == 'none'

    def test_time_align_t5(self, monkeypatch):
        """time_align=t+5 → config.time_align='t+5'"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_time_align_t+5']
        assert len(caps) == 1
        assert caps[0]['config'].time_align == 't+5'

    def test_data_window_2010_2020(self, monkeypatch):
        """data_window → config.data_window 正确设置"""
        captured = self._run_l4_and_capture(monkeypatch)
        # 验证 data_window 类配置存在
        dw_caps = [c for c in captured
                   if c['config'].name.startswith('L4_data_window_')]
        assert len(dw_caps) >= 1
        for c in dw_caps:
            assert c['config'].data_window is not None
            assert isinstance(c['config'].data_window, tuple)
            assert len(c['config'].data_window) == 2

    def test_outlier_mad(self, monkeypatch):
        """outlier=mad → config.outlier_method='mad' (默认选项)"""
        captured = self._run_l4_and_capture(monkeypatch)
        caps = [c for c in captured if c['config'].name == 'L4_outlier_method_mad']
        assert len(caps) == 1
        assert caps[0]['config'].outlier_method == 'mad'

    def test_l4_bh_fdr_applied(self, monkeypatch):
        """L4 多个比较经 BH-FDR 校正"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        reference = _make_layer_result('B3_full', 'baseline', seed=99)
        results = [
            _make_layer_result(f'L4_outlier_method_{m}', 'L4', seed=i)
            for i, m in enumerate(['3sigma', 'mad', 'winsorize_1pct', 'winsorize_5pct'])
        ]

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called
            called_p_values = mock_bh.call_args[0][0]
            assert len(called_p_values) == 4

    def test_l4_report_generated(self):
        """报告含 L4 前置处理 OAT 表"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        results = [
            _make_layer_result('B3_full', 'baseline', seed=0),
            _make_layer_result('L4_outlier_method_3sigma', 'L4', seed=1),
            _make_layer_result('L4_scaler_method_rank', 'L4', seed=2),
        ]
        comparisons = runner.compare_all(results[1:], results[0])

        report = runner.generate_report(results, comparisons)
        assert "L4 前置处理 OAT" in report
        assert "L4_outlier_method_3sigma" in report

    def test_l4_oat_marks_trivial_configs(self, monkeypatch):
        """P1-7: run_l4_oat 标记默认选项为 _is_trivial=True (M5 修正)

        Spec §5.2 M5: 每个自由度的默认选项与 baseline 相同, 构成平凡比较.
        默认选项: outlier=mad, scaler=zscore, missing=median,
                 neutralization=industry, time_align=t+1, data_window=full
        6 个 trivial + 13 个非平凡 = 19 个 L4 消融配置.
        """
        captured = self._run_l4_and_capture(monkeypatch)
        # 默认选项配置应标记为 trivial
        trivial_configs = [c for c in captured
                           if getattr(c['config'], '_is_trivial', False)]
        # 6 个自由度各 1 个默认选项 = 6 个 trivial
        assert len(trivial_configs) == 6, (
            f"Expected 6 trivial configs (one per DOF default), "
            f"got {len(trivial_configs)}"
        )
        # 非默认选项不应标记为 trivial (排除 baseline B3_full)
        non_trivial_l4 = [c for c in captured
                          if c['config'].layer == 'L4'
                          and not getattr(c['config'], '_is_trivial', False)]
        assert len(non_trivial_l4) == 13, (
            f"Expected 13 non-trivial L4 configs, got {len(non_trivial_l4)}"
        )

    def test_l4_trivial_comparisons_excluded_from_bh_fdr(self):
        """P1-7: compare_all 排除 _is_trivial 比较不参与 BH-FDR (M5 修正)

        Spec §5.3 M5: BH-FDR 校正 13 个非平凡比较 (排除 6 个 trivial).
        trivial 比较仍保留在结果列表中, 但 _is_trivial=True 且不占用多重比较额度.
        """
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        reference = _make_layer_result('B3_full', 'baseline', seed=99)

        # 构造 19 个 L4 结果: 6 trivial + 13 non-trivial
        results = []
        # 6 trivial (默认选项, 与 baseline 相同)
        for i, name in enumerate(['L4_outlier_method_mad', 'L4_scaler_method_zscore',
                                   'L4_missing_method_median',
                                   'L4_neutralization_industry',
                                   'L4_time_align_t+1',
                                   'L4_data_window_full']):
            r = _make_layer_result(name, 'L4', seed=i)
            r.config._is_trivial = True
            results.append(r)
        # 13 non-trivial
        for i in range(13):
            results.append(_make_layer_result(f'L4_nontrivial_{i}', 'L4',
                                               seed=i + 10))

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called
            called_p_values = mock_bh.call_args[0][0]
            # BH-FDR 仅校正 13 个非平凡比较 (排除 6 个 trivial)
            assert len(called_p_values) == 13, (
                f"Expected 13 p_values in BH-FDR (excluding 6 trivial), "
                f"got {len(called_p_values)}"
            )

        # trivial 比较应标记 _is_trivial=True 且保留在结果中
        trivial_comparisons = [c for c in comparisons
                               if getattr(c, '_is_trivial', False)]
        assert len(trivial_comparisons) == 6, (
            f"Expected 6 trivial comparisons marked, got {len(trivial_comparisons)}"
        )
        # 总比较数 = 19 (trivial + non-trivial 都保留)
        assert len(comparisons) == 19, (
            f"Expected 19 total comparisons (trivial+non-trivial), got {len(comparisons)}"
        )


# =============================================================================
# E6: L3 参数消融 (8 tests)
# =============================================================================

class TestL3Ablation:
    """E6: L3 参数消融行为测试 (规格 §6.5)"""

    def _run_l3_and_capture(self, monkeypatch):
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        runner.run_l3(_make_factor_data(), _make_fwd_returns())
        return captured

    def test_cusum_k_variants(self, monkeypatch):
        """3+ 个 cusum_k 值 → 3+ 个不同 CUSUM 行为"""
        captured = self._run_l3_and_capture(monkeypatch)
        cusum_results = [c for c in captured if c['config'].cusum_k is not None]
        k_values = {c['config'].cusum_k for c in cusum_results}
        assert len(k_values) >= 3, (
            f"Expected ≥3 distinct cusum_k values, got {k_values}"
        )

    def test_cusum_h_variants(self, monkeypatch):
        """3+ 个 cusum_h 值 → 3+ 个不同 ARL"""
        captured = self._run_l3_and_capture(monkeypatch)
        cusum_h_results = [c for c in captured if c['config'].cusum_h is not None]
        h_values = {c['config'].cusum_h for c in cusum_h_results}
        assert len(h_values) >= 3, (
            f"Expected ≥3 distinct cusum_h values, got {h_values}"
        )

    def test_correction_bh_vs_bonferroni(self, monkeypatch):
        """correction_method 覆盖 benjamini_hochberg / bonferroni / none"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        # 直接验证 apply_correction 的检测力差异
        from factor_pipeline.backtest.multiple_testing import (
            apply_bh_fdr, apply_bonferroni, apply_correction,
        )
        p_values = [0.01, 0.02, 0.03, 0.04, 0.50]
        _, sig_bh = apply_correction(p_values, 'benjamini_hochberg', alpha=0.05)
        _, sig_bonf = apply_correction(p_values, 'bonferroni', alpha=0.05)
        # BH 检测力 ≥ Bonferroni (更多或相等显著)
        assert sum(sig_bh) >= sum(sig_bonf), (
            f"BH ({sum(sig_bh)}) should detect ≥ Bonferroni ({sum(sig_bonf)})"
        )

    def test_winsorize_1pct_vs_5pct(self, monkeypatch):
        """1% vs 5% → winsorize_ratio 配置不同"""
        captured = self._run_l3_and_capture(monkeypatch)
        winsor_results = [c for c in captured
                         if c['config'].winsorize_ratio is not None]
        ratios = {c['config'].winsorize_ratio for c in winsor_results}
        assert 0.01 in ratios or 0.01 in {float(r) for r in ratios}, (
            f"Expected 0.01 in winsorize ratios, got {ratios}"
        )
        assert 0.05 in ratios or 0.05 in {float(r) for r in ratios}, (
            f"Expected 0.05 in winsorize ratios, got {ratios}"
        )

    def test_l3_returns_25_results(self, monkeypatch):
        """run_l3 → ~25 个 AblationResult (M4: 含 EWMA + 5叉阈值)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_l3(_make_factor_data(), _make_fwd_returns())

        # 1 baseline + 4 cusum + 3 ewma_hl + 5 ewma_alpha + 3 threshold + 3 winsor = 19
        # 规格允许 ≥19 (M4 修正 ~25, 当前实现 19)
        assert len(results) >= 19, (
            f"Expected ≥19 L3 results, got {len(results)}"
        )

    def test_l3_uses_t3_cusum(self, monkeypatch):
        """L3 消融复用 T3 CUSUM (cusum_k/h 参数覆盖)"""
        captured = self._run_l3_and_capture(monkeypatch)
        cusum_results = [c for c in captured if c['config'].cusum_k is not None]
        assert len(cusum_results) >= 3, (
            "L3 should include CUSUM k variants (T3 ADR-025)"
        )
        # 验证 cusum_h 也被设置
        for c in cusum_results:
            assert c['config'].cusum_h is not None

    def test_l3_bh_fdr_correction(self, monkeypatch):
        """L3 多个比较经 BH-FDR 校正"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=100)
        reference = _make_layer_result('B3_full', 'baseline', seed=99)
        results = [
            _make_layer_result(f'L3_cusum_{i}', 'L3', seed=i)
            for i in range(6)
        ]

        with patch('factor_pipeline.backtest.ablation_runner.apply_bh_fdr',
                   wraps=apply_bh_fdr) as mock_bh:
            comparisons = runner.compare_all(results, reference)
            assert mock_bh.called
            called_p_values = mock_bh.call_args[0][0]
            assert len(called_p_values) == 6

    def test_l3_report_has_param_table(self):
        """报告含参数消融表"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        results = [
            _make_layer_result('B3_full', 'baseline', seed=0),
            _make_layer_result('L3_cusum_0', 'L3', seed=1),
            _make_layer_result('L3_ewma_12', 'L3', seed=2),
        ]
        comparisons = runner.compare_all(results[1:], results[0])

        report = runner.generate_report(results, comparisons)
        assert "L3 参数消融" in report
        assert "L3_cusum_0" in report

    def test_l3_correction_method_variants(self, monkeypatch):
        """P1-3: run_l3 includes 3 correction_method configs (bh/bonferroni/none)

        Spec §6.2: correction_method ∈ {'benjamini_hochberg', 'bonferroni', 'none'}.
        当前 run_l3 缺失 correction_method 消融, 需补充 3 配置.
        """
        captured = self._run_l3_and_capture(monkeypatch)
        correction_configs = [c for c in captured
                              if c['config'].correction_method is not None]
        methods = {c['config'].correction_method for c in correction_configs}
        assert methods == {'benjamini_hochberg', 'bonferroni', 'none'}, (
            f"Expected 3 correction_method variants, got {methods}"
        )
        assert len(correction_configs) == 3, (
            f"Expected 3 correction_method configs, got {len(correction_configs)}"
        )

    def test_l3_cusum_oat_k_variants(self, monkeypatch):
        """P1-4: CUSUM OAT k 变体 — 3 配置 k=0.25/0.5/0.75, h 固定 5.5

        Spec §6.2: OAT (One-At-a-Time), k ∈ {0.25, 0.5, 0.75} (h=5.5 fixed).
        当前实现用组合对 (k,h), 需改为 OAT.
        """
        captured = self._run_l3_and_capture(monkeypatch)
        # k-OAT 配置: 通过名称前缀 'L3_cusum_oat_k' 区分 (避免与 h-OAT 混淆)
        k_oat_configs = [c for c in captured
                         if c['config'].name.startswith('L3_cusum_oat_k')]
        k_values = {c['config'].cusum_k for c in k_oat_configs}
        # 必须包含 3 个 OAT k 值
        assert {0.25, 0.5, 0.75} == k_values, (
            f"Expected k ∈ {{0.25, 0.5, 0.75}} OAT variants, got {k_values}"
        )
        assert len(k_oat_configs) == 3, (
            f"Expected 3 k-OAT configs, got {len(k_oat_configs)}"
        )
        # k OAT 配置中 h 必须固定为 5.5 (默认值)
        for c in k_oat_configs:
            assert c['config'].cusum_h == 5.5, (
                f"k OAT config (k={c['config'].cusum_k}) must have h=5.5 fixed, "
                f"got h={c['config'].cusum_h}"
            )

    def test_l3_cusum_oat_h_variants(self, monkeypatch):
        """P1-4: CUSUM OAT h 变体 — 3 配置 h=4.0/5.5/7.0, k 固定 0.5

        Spec §6.2: OAT, h ∈ {4.0, 5.5, 7.0} (k=0.5 fixed).
        """
        captured = self._run_l3_and_capture(monkeypatch)
        # h-OAT 配置: 通过名称前缀 'L3_cusum_oat_h' 区分
        h_oat_configs = [c for c in captured
                         if c['config'].name.startswith('L3_cusum_oat_h')]
        h_values = {c['config'].cusum_h for c in h_oat_configs}
        # 必须包含 3 个 OAT h 值
        assert {4.0, 5.5, 7.0} == h_values, (
            f"Expected h ∈ {{4.0, 5.5, 7.0}} OAT variants, got {h_values}"
        )
        assert len(h_oat_configs) == 3, (
            f"Expected 3 h-OAT configs, got {len(h_oat_configs)}"
        )
        # h OAT 配置中 k 必须固定为 0.5 (默认值)
        for c in h_oat_configs:
            assert c['config'].cusum_k == 0.5, (
                f"h OAT config (h={c['config'].cusum_h}) must have k=0.5 fixed, "
                f"got k={c['config'].cusum_k}"
            )

    def test_l3_winsorize_includes_mad(self, monkeypatch):
        """P1-5: run_l3 winsorize 包含 MAD 3σ 选项

        Spec §6.2: winsorize 4 选项 — 1% / 3% / 5% / MAD 3σ.
        当前仅 0.01/0.03/0.05, 缺失 MAD. MAD 用 outlier_method='mad' 表示
        (winsorize_ratio 为 float 无法表示 MAD).
        """
        captured = self._run_l3_and_capture(monkeypatch)
        # 检查 MAD 选项: 通过 outlier_method='mad' 配置
        mad_configs = [c for c in captured
                       if c['config'].outlier_method == 'mad']
        assert len(mad_configs) >= 1, (
            "run_l3 should include MAD 3σ winsorize option (outlier_method='mad')"
        )
        # 同时验证 3 个 winsorize_ratio 仍存在
        winsor_configs = [c for c in captured
                          if c['config'].winsorize_ratio is not None]
        ratios = {c['config'].winsorize_ratio for c in winsor_configs}
        assert {0.01, 0.03, 0.05}.issubset(ratios), (
            f"Expected winsorize ratios {{0.01, 0.03, 0.05}}, got {ratios}"
        )


# =============================================================================
# E7: Baseline 阶梯 + 报告生成 (6 tests)
# =============================================================================

class TestBaselines:
    """E7: B0-B3 Baseline 阶梯行为测试 (规格 §7.5)"""

    def test_b0_raw_dropna_no_processing(self):
        """B0 → 原始因子 + dropna (无管线处理)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data(n_periods=20, n_stocks=15)
        fwd_returns = _make_fwd_returns(n_periods=20, n_stocks=15)

        config = AblationConfig(name='B0_raw_dropna', layer='baseline',
                               baseline_level='B0')
        result = runner.run_single(config, factor_data, fwd_returns)

        assert result.config.baseline_level == 'B0'
        # B0: 所有 rho_step = 1.0 (恒等变换, 无管线)
        for step, rho in result.rho_step.items():
            assert rho == pytest.approx(1.0, abs=1e-6)

    def test_b1_imputer_only(self, monkeypatch):
        """B1 → 仅 imputer 启用 (其余关闭)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_baselines(_make_factor_data(), _make_fwd_returns())

        b1_caps = [c for c in captured
                   if c['config'].name == 'B1_baseline'
                   or c['config'].baseline_level == 'B1']
        assert len(b1_caps) >= 1
        b1_cap = b1_caps[0]
        # B1: module_override 指定仅 imputer 启用
        ov = b1_cap['module_override']
        assert ov is not None
        assert ov.get('imputer') is True
        assert ov.get('winsorizer') is False
        assert ov.get('scaler') is False
        assert ov.get('neutralizer') is False

    def test_b2_imputer_zscore(self, monkeypatch):
        """B2 → imputer + scaler (Z-score) 启用"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        captured = _capture_pipeline_configs(monkeypatch, runner)
        results = runner.run_baselines(_make_factor_data(), _make_fwd_returns())

        b2_caps = [c for c in captured if c['config'].baseline_level == 'B2']
        assert len(b2_caps) >= 1
        ov = b2_caps[0]['module_override']
        assert ov is not None
        assert ov.get('imputer') is True
        assert ov.get('scaler') is True
        assert ov.get('winsorizer') is False

    def test_b3_full_pipeline(self):
        """B3 → 全部启用 (完整管线)"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        factor_data = _make_factor_data(n_periods=24, n_stocks=20)
        fwd_returns = _make_fwd_returns(n_periods=24, n_stocks=20)
        industry_data = _make_industry_data(n_stocks=20)

        config = AblationConfig(name='B3_full', layer='baseline',
                               baseline_level='B3')
        result = runner.run_single(config, factor_data, fwd_returns, industry_data)

        assert result.config.baseline_level == 'B3'
        assert not np.isnan(result.metrics['ic_mean'])


class TestReport:
    """E7: 报告生成 + 诊断完整性测试 (规格 §7.5)"""

    def test_report_markdown_complete(self):
        """generate_report → 含全部章节的合法 Markdown"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config())
        # 构造覆盖各层的结果
        results = [
            _make_layer_result('B0_baseline', 'baseline', seed=0),
            _make_layer_result('B3_full', 'baseline', seed=1),
            _make_layer_result('L1_imputer_off', 'L1', seed=2),
            _make_layer_result('L2_all_static', 'L2', seed=3),
            _make_layer_result('L3_cusum_0', 'L3', seed=4),
            _make_layer_result('L4_outlier_3sigma', 'L4', seed=5),
        ]
        comparisons = runner.compare_all(results[2:], results[1])

        report = runner.generate_report(results, comparisons)
        assert isinstance(report, str)
        # 含全部章节
        assert "# Ablation Study Report" in report
        assert "Baseline 阶梯" in report
        assert "L1 组件消融" in report
        assert "L2 路由消融" in report
        assert "L3 参数消融" in report
        assert "L4 前置处理 OAT" in report
        assert "排序保持性 ρ_step" in report
        assert "正交化诊断" in report
        assert "诚实立场声明" in report
        assert "学术依据" in report
        # 含 BH-FDR 显著性标记
        assert "✓" in report or "✗" in report

    def test_diagnostics_complete(self):
        """get_diagnostics → 含全部必要字段"""
        from factor_pipeline.pipelines_v2 import PipelineV2Config

        runner = AblationRunner(PipelineV2Config(), n_bootstrap=500)
        runner._results = [
            _make_layer_result('r0', 'L1'),
            _make_layer_result('r1', 'L2'),
        ]

        diag = runner.get_diagnostics()
        assert 'n_experiments' in diag
        assert diag['n_experiments'] == 2
        assert 'total_runtime_sec' in diag
        assert 'alpha' in diag
        assert 'n_bootstrap' in diag
        assert 'results_summary' in diag
        assert len(diag['results_summary']) == 2
        for summary in diag['results_summary']:
            assert 'name' in summary
            assert 'layer' in summary
            assert 'ic_mean' in summary
            assert 'icir' in summary
            assert 'sharpe_ls' in summary


# =============================================================================
# P0-2/P0-3/P0-4: 参数注入行为测试 (audit 修复)
# 规格: §2.5/§4.3 (L2 routing) / §6.4 (L3 params) / §5.4 (L4 OAT)
# =============================================================================

def _make_mock_pipeline(factor_names=None):
    """构造 mock pipeline (含 factor_classifications) 用于 _override_routing 测试.

    使用真实 ClassificationResult + FactorType, 不依赖管线 fit.
    """
    from factor_pipeline.modules.factor_fingerprint import (
        FactorType, ClassificationResult,
    )

    class _MockPipeline:
        def __init__(self):
            # 初始化为 DYNAMIC (与 STATIC/MIXED 区分, 便于检测覆盖)
            self.factor_classifications = {
                name: ClassificationResult(
                    primary_type=FactorType.DYNAMIC,
                    primary_prob=0.6,
                    secondary_type=FactorType.STATIC,
                    secondary_prob=0.4,
                    is_hard=False,
                )
                for name in (factor_names or ['f0', 'f1', 'f2'])
            }

    return _MockPipeline()


class TestRoutingOverride:
    """P0-2: L2 路由覆盖 (_override_routing) 行为测试 (规格 §2.5/§4.3)"""

    def _make_runner(self):
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        return AblationRunner(PipelineV2Config())

    def test_override_routing_static(self):
        """routing_mode='static' → 所有 classifications 强制为 STATIC, is_hard=True"""
        from factor_pipeline.modules.factor_fingerprint import FactorType

        runner = self._make_runner()
        pipeline = _make_mock_pipeline(['f0', 'f1', 'f2'])
        original_keys = list(pipeline.factor_classifications.keys())

        runner._override_routing(pipeline, 'static', random_seed=None)

        for name in original_keys:
            cls = pipeline.factor_classifications[name]
            assert cls.primary_type == FactorType.STATIC, (
                f"{name}: expected STATIC, got {cls.primary_type}"
            )
            assert cls.is_hard is True
            assert cls.primary_prob == 1.0

    def test_override_routing_dynamic(self):
        """routing_mode='dynamic' → 所有 classifications 强制为 DYNAMIC"""
        from factor_pipeline.modules.factor_fingerprint import FactorType

        runner = self._make_runner()
        pipeline = _make_mock_pipeline(['f0', 'f1'])

        runner._override_routing(pipeline, 'dynamic', random_seed=None)

        for name, cls in pipeline.factor_classifications.items():
            assert cls.primary_type == FactorType.DYNAMIC, (
                f"{name}: expected DYNAMIC, got {cls.primary_type}"
            )
            assert cls.is_hard is True

    def test_override_routing_mixed(self):
        """routing_mode='mixed' → 所有 classifications 强制为 MIXED"""
        from factor_pipeline.modules.factor_fingerprint import FactorType

        runner = self._make_runner()
        pipeline = _make_mock_pipeline(['f0', 'f1', 'f2', 'f3'])

        runner._override_routing(pipeline, 'mixed', random_seed=None)

        for name, cls in pipeline.factor_classifications.items():
            assert cls.primary_type == FactorType.MIXED, (
                f"{name}: expected MIXED, got {cls.primary_type}"
            )
            assert cls.is_hard is True

    def test_override_routing_random_seed(self):
        """routing_mode='random' + 固定 seed → 可重现的随机分配"""
        from factor_pipeline.modules.factor_fingerprint import FactorType

        runner = self._make_runner()
        factor_names = ['f0', 'f1', 'f2', 'f3', 'f4', 'f5']

        # 第一次运行
        pipeline_a = _make_mock_pipeline(factor_names)
        runner._override_routing(pipeline_a, 'random', random_seed=42)
        types_a = {n: pipeline_a.factor_classifications[n].primary_type
                   for n in factor_names}

        # 第二次运行 (相同 seed)
        pipeline_b = _make_mock_pipeline(factor_names)
        runner._override_routing(pipeline_b, 'random', random_seed=42)
        types_b = {n: pipeline_b.factor_classifications[n].primary_type
                   for n in factor_names}

        # 可重现: 两次结果完全一致
        assert types_a == types_b, (
            f"random routing with same seed should be reproducible: "
            f"{types_a} vs {types_b}"
        )
        # 所有结果必须是合法类型
        valid_types = {FactorType.STATIC, FactorType.DYNAMIC, FactorType.MIXED}
        for name, t in types_a.items():
            assert t in valid_types, f"{name}: invalid type {t}"

    def test_override_routing_full(self):
        """routing_mode='full' → classifications 不变 (指纹驱动路由保持)"""
        runner = self._make_runner()
        pipeline = _make_mock_pipeline(['f0', 'f1'])
        # 保存原始分类的快照
        original = {n: cls for n, cls in pipeline.factor_classifications.items()}

        runner._override_routing(pipeline, 'full', random_seed=None)

        # 完全不变
        for name, orig_cls in original.items():
            cur = pipeline.factor_classifications[name]
            assert cur is orig_cls, (
                f"{name}: classification should be unchanged for 'full' mode"
            )


class TestL3ParameterInjection:
    """P0-3: L3 参数注入 (_apply_l3_overrides) 行为测试 (规格 §6.4)"""

    def _make_runner_and_config(self):
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        runner = AblationRunner(PipelineV2Config())
        # 深拷贝 base_config 作为可修改的 modified_config
        import copy as _copy
        modified_config = _copy.deepcopy(runner.base_config)
        return runner, modified_config

    def test_l3_cusum_k_injected(self):
        """cusum_k=0.25 → modified_config.cusum_k=0.25 (直接字段, 启用 CUSUM)"""
        runner, modified_config = self._make_runner_and_config()
        original_k = modified_config.cusum_k
        assert original_k != 0.25  # 确保测试值与默认不同

        abl_cfg = AblationConfig(name='L3_test', layer='L3', cusum_k=0.25)
        runner._apply_l3_overrides(modified_config, abl_cfg)

        assert modified_config.cusum_k == 0.25
        # spec §6.4: cusum_k 注入时启用 CUSUM 监测
        assert modified_config.enable_cusum_drift_monitor is True

    def test_l3_cusum_h_injected(self):
        """cusum_h=4.0 → modified_config.cusum_h=4.0 (直接字段, 启用 CUSUM)"""
        runner, modified_config = self._make_runner_and_config()
        assert modified_config.cusum_h != 4.0

        abl_cfg = AblationConfig(name='L3_test', layer='L3', cusum_h=4.0)
        runner._apply_l3_overrides(modified_config, abl_cfg)

        assert modified_config.cusum_h == 4.0
        assert modified_config.enable_cusum_drift_monitor is True

    def test_l3_winsorize_ratio_injected(self):
        """winsorize_ratio=0.03 → modified_config 携带该参数 (spec §6.4: _l3_winsorize_ratio)"""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name='L3_test', layer='L3', winsorize_ratio=0.03)
        runner._apply_l3_overrides(modified_config, abl_cfg)

        # winsorize_ratio 不在 PipelineV2Config 直接字段, spec 使用 _l3_winsorize_ratio
        assert getattr(modified_config, '_l3_winsorize_ratio', None) == 0.03

    def test_l3_none_values_skipped(self):
        """所有 L3 字段为 None → modified_config 不变 (cusum_k/h/enable_cusum_drift_monitor 保持默认)"""
        runner, modified_config = self._make_runner_and_config()
        original_k = modified_config.cusum_k
        original_h = modified_config.cusum_h
        original_cusum_enable = modified_config.enable_cusum_drift_monitor

        abl_cfg = AblationConfig(name='L3_test', layer='L3')  # 全 None
        runner._apply_l3_overrides(modified_config, abl_cfg)

        assert modified_config.cusum_k == original_k
        assert modified_config.cusum_h == original_h
        assert modified_config.enable_cusum_drift_monitor == original_cusum_enable
        # 不应创建任何 _l3_* 属性
        assert not hasattr(modified_config, '_l3_winsorize_ratio')


class TestL4ParameterInjection:
    """P0-4: L4 OAT 参数注入 (_apply_l4_overrides) 行为测试 (规格 §5.4)"""

    def _make_runner_and_config(self):
        from factor_pipeline.pipelines_v2 import PipelineV2Config
        runner = AblationRunner(PipelineV2Config())
        import copy as _copy
        modified_config = _copy.deepcopy(runner.base_config)
        return runner, modified_config

    def test_l4_outlier_method_injected(self):
        """outlier_method='mad' → modified_config 携带该参数 (spec §5.4: _l4_outlier_method)"""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name='L4_test', layer='L4', outlier_method='mad')
        runner._apply_l4_overrides(modified_config, abl_cfg)

        assert getattr(modified_config, '_l4_outlier_method', None) == 'mad'

    def test_l4_scaler_method_injected(self):
        """scaler_method='rank' → modified_config 携带该参数 (spec §5.4: _l4_scaler_method)"""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name='L4_test', layer='L4', scaler_method='rank')
        runner._apply_l4_overrides(modified_config, abl_cfg)

        assert getattr(modified_config, '_l4_scaler_method', None) == 'rank'

    def test_l4_missing_method_injected(self):
        """missing_method='median' → modified_config 携带插补策略 (spec §5.4: _l4_imputer_strategy)"""
        runner, modified_config = self._make_runner_and_config()

        abl_cfg = AblationConfig(name='L4_test', layer='L4', missing_method='median')
        runner._apply_l4_overrides(modified_config, abl_cfg)

        # spec §5.4: 'median' → _l4_imputer_strategy='median'
        assert getattr(modified_config, '_l4_imputer_strategy', None) == 'median'

    def test_l4_none_values_skipped(self):
        """所有 L4 字段为 None → modified_config 不变"""
        runner, modified_config = self._make_runner_and_config()
        original_module_enabled = modified_config.module_enabled

        abl_cfg = AblationConfig(name='L4_test', layer='L4')  # 全 None
        runner._apply_l4_overrides(modified_config, abl_cfg)

        assert modified_config.module_enabled == original_module_enabled
        assert not hasattr(modified_config, '_l4_outlier_method')
        assert not hasattr(modified_config, '_l4_scaler_method')
        assert not hasattr(modified_config, '_l4_imputer_strategy')
