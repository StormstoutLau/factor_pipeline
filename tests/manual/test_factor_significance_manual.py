# -*- coding: utf-8 -*-
"""O3b 手工数值校验脚本 — 因子增量显著性检验

校验目标: FactorSignificanceTest 与 statsmodels OLS 对比, 精度 1e-6
对应: EXECUTION_V2.5.0.md O4.6 手工数值校验方案

校验项目 (8 项):
1. 系数一致性 — 项目 Stage 3 OLS vs statsmodels OLS (同 X 矩阵, 精度 1e-10)
2. OLS 标准误 — 项目 vs statsmodels scale * sqrt(diag(XtX^-1)) (精度 1e-10)
3. HC3 标准误 — 项目 vs statsmodels cov_HC3 (精度 1e-10)
4. HC1 标准误 — 项目 vs statsmodels cov_HC1 (精度 1e-10)
5. t 统计量 — coef/se 一致性 (精度 1e-10)
6. p 值 — 项目 vs statsmodels t 分布生存函数 (精度 1e-8)
7. 截距一致性 — 非零截距下系数无偏 (atol=0.05)
8. BH 多重检验校正 — 手工排序计算 vs 项目结果 (精度 1e-10)

数学注记:
  - 项目实现与 statsmodels 对比时必须用相同 X 矩阵 (项目 Lasso 选出的控制集 +
    treatment D_k + 截距列), 否则系数不可比 (不同 X → 不同 OLS 解)
  - HC3 公式: cov_HC3 = (XtX)^-1 @ X^T @ diag(e_i^2 / (1-h_i)^2) @ X @ (XtX)^-1
  - BH 校正: p_(k) * K / rank, 取累积最小 (控制 FDR)

运行方式:
  pytest:  cd f:/Coding; python -m pytest factor_pipeline/tests/manual/test_factor_significance_manual.py -v
  独立:    cd f:/Coding; python -m factor_pipeline.tests.manual.test_factor_significance_manual
"""
from __future__ import annotations

import numpy as np
import pytest
import statsmodels.api as sm
from scipy import stats

from factor_pipeline.backtest.factor_significance import FactorSignificanceTest


# ---------- 工具函数 ----------

def _make_data(N: int = 500, K: int = 5, seed: int = 42):
    """构造已知数据: true_beta = [0.5, 0.0, 0.3, 0.0, 0.2]"""
    rng = np.random.default_rng(seed)
    F = rng.standard_normal((N, K))
    true_beta = np.array([0.5, 0.0, 0.3, 0.0, 0.2])
    y = F @ true_beta + 0.1 * rng.standard_normal(N)
    return F, y, true_beta


def _make_heteroscedastic_data(N: int = 300, K: int = 4, seed: int = 42):
    """构造异方差数据 (HC3 与 OLS 标准误差异显著)"""
    rng = np.random.default_rng(seed)
    F = rng.standard_normal((N, K))
    true_beta = np.array([0.5, 0.0, 0.3, 0.0])
    # 异方差: 噪声方差随 F[:, 0] 增大
    hetero_noise = (1 + np.abs(F[:, 0])) * rng.standard_normal(N)
    y = F @ true_beta + hetero_noise
    return F, y, true_beta


def _run_project(F, y, target_idx=0, **kwargs):
    """运行项目实现, 返回 result + 实际使用的 X_final 矩阵"""
    K = F.shape[1]
    test = FactorSignificanceTest(method='double_lasso', cv_folds=5, **kwargs)
    test.F_ = F
    test.y_ = y
    test.factor_names_ = [f'f{k}' for k in range(K)]
    result = test.test_incremental_alpha(f'f{target_idx}')

    # 重建 X_final 用于 statsmodels 对比
    D_k = F[:, target_idx]
    other_idx = [i for i in range(K) if i != target_idx]
    X = np.delete(F, target_idx, axis=1)
    # 从 selected_controls 反推索引
    selected_names = result.get('selected_controls', [])
    other_names = [f'f{i}' for i in other_idx]
    selected_idx = sorted([other_names.index(n) for n in selected_names])
    N = len(y)
    if selected_idx:
        X_selected = X[:, selected_idx]
        X_final = np.column_stack([D_k, X_selected, np.ones(N)])
    else:
        X_final = np.column_stack([D_k, np.ones(N)])

    return result, X_final


# =============================================================================
# 1. 系数一致性
# =============================================================================

class TestCoefficientConsistency:
    """系数与 statsmodels OLS 对比 (同 X 矩阵, 精度 1e-10)"""

    def test_coefficient_matches_statsmodels(self):
        """项目 Stage 3 OLS 系数 = statsmodels OLS 系数 (同 X, 精度 1e-10)"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(F, y, target_idx=0)

        sm_result = sm.OLS(y, X_final).fit()
        # D_k 是第 0 个系数
        np.testing.assert_allclose(
            result['coefficient'], sm_result.params[0], atol=1e-10,
            err_msg=(
                f"系数不一致: 项目={result['coefficient']}, "
                f"statsmodels={sm_result.params[0]}"
            ),
        )

    def test_coefficient_matches_statsmodels_target_f2(self):
        """treatment=f2 时系数也一致"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(F, y, target_idx=2)

        sm_result = sm.OLS(y, X_final).fit()
        np.testing.assert_allclose(
            result['coefficient'], sm_result.params[0], atol=1e-10,
            err_msg=f"系数不一致: 项目={result['coefficient']}, statsmodels={sm_result.params[0]}",
        )


# =============================================================================
# 2. OLS 标准误
# =============================================================================

class TestOLSStandardError:
    """OLS 标准误与 statsmodels 对比"""

    def test_ols_std_error_matches_statsmodels(self):
        """项目 OLS se = statsmodels se (精度 1e-10)"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(
            F, y, target_idx=0, std_error_type='ols'
        )

        sm_result = sm.OLS(y, X_final).fit()
        # statsmodels 标准误 = sqrt(diag(cov)) 默认 scale=SSR/(n-p)
        np.testing.assert_allclose(
            result['std_error'], sm_result.bse[0], atol=1e-10,
            err_msg=(
                f"OLS se 不一致: 项目={result['std_error']}, "
                f"statsmodels={sm_result.bse[0]}"
            ),
        )


# =============================================================================
# 3. HC3 标准误
# =============================================================================

class TestHC3StandardError:
    """HC3 标准误与 statsmodels cov_HC3 对比"""

    def test_hc3_std_error_matches_statsmodels(self):
        """项目 HC3 se = sqrt(diag(statsmodels cov_HC3)) (精度 1e-10)"""
        F, y, _ = _make_heteroscedastic_data(N=300, K=4)
        result, X_final = _run_project(
            F, y, target_idx=0, std_error_type='hc3'
        )

        sm_model = sm.OLS(y, X_final)
        sm_result = sm_model.fit()
        cov_hc3 = sm_result.cov_HC3
        se_hc3_sm = np.sqrt(np.maximum(np.diag(cov_hc3), 0.0))

        np.testing.assert_allclose(
            result['std_error'], se_hc3_sm[0], atol=1e-10,
            err_msg=(
                f"HC3 se 不一致: 项目={result['std_error']}, "
                f"statsmodels={se_hc3_sm[0]}"
            ),
        )

    def test_hc3_differs_from_ols_under_heteroscedasticity(self):
        """异方差下 HC3 se ≠ OLS se (HC3 修正异方差)"""
        F, y, _ = _make_heteroscedastic_data(N=300, K=4)
        result_hc3, _ = _run_project(
            F, y, target_idx=0, std_error_type='hc3'
        )
        result_ols, _ = _run_project(
            F, y, target_idx=0, std_error_type='ols'
        )
        assert not np.isclose(
            result_hc3['std_error'], result_ols['std_error'], atol=1e-8
        ), (
            f"HC3 se={result_hc3['std_error']} 与 OLS se={result_ols['std_error']} "
            f"在异方差下应有差异"
        )


# =============================================================================
# 4. HC1 标准误
# =============================================================================

class TestHC1StandardError:
    """HC1 标准误与 statsmodels cov_HC1 对比"""

    def test_hc1_std_error_matches_statsmodels(self):
        """项目 HC1 se = sqrt(diag(statsmodels cov_HC1)) (精度 1e-10)"""
        F, y, _ = _make_heteroscedastic_data(N=300, K=4)
        result, X_final = _run_project(
            F, y, target_idx=0, std_error_type='hc1'
        )

        sm_model = sm.OLS(y, X_final)
        sm_result = sm_model.fit()
        cov_hc1 = sm_result.cov_HC1
        se_hc1_sm = np.sqrt(np.maximum(np.diag(cov_hc1), 0.0))

        np.testing.assert_allclose(
            result['std_error'], se_hc1_sm[0], atol=1e-10,
            err_msg=(
                f"HC1 se 不一致: 项目={result['std_error']}, "
                f"statsmodels={se_hc1_sm[0]}"
            ),
        )


# =============================================================================
# 5. t 统计量
# =============================================================================

class TestTStatistic:
    """t 统计量 = coef / se 一致性"""

    def test_t_statistic_matches_statsmodels(self):
        """项目 t_stat = statsmodels tvalue (精度 1e-10)"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(
            F, y, target_idx=0, std_error_type='hc3'
        )

        sm_result = sm.OLS(y, X_final).fit(cov_type='HC3')
        np.testing.assert_allclose(
            result['t_statistic'], sm_result.tvalues[0], atol=1e-8,
            err_msg=(
                f"t 统计量不一致: 项目={result['t_statistic']}, "
                f"statsmodels={sm_result.tvalues[0]}"
            ),
        )

    def test_t_statistic_is_coef_over_se(self):
        """t_statistic = coefficient / std_error (精度 1e-10)"""
        F, y, _ = _make_data(N=500, K=5)
        result, _ = _run_project(F, y, target_idx=0)
        expected_t = result['coefficient'] / result['std_error']
        np.testing.assert_allclose(
            result['t_statistic'], expected_t, atol=1e-10,
            err_msg="t_statistic != coefficient / std_error",
        )


# =============================================================================
# 6. p 值
# =============================================================================

class TestPValue:
    """p 值与 statsmodels 对比"""

    def test_p_value_matches_statsmodels(self):
        """项目 p_value = statsmodels pvalue (精度 1e-8)"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(
            F, y, target_idx=0, std_error_type='hc3'
        )

        sm_result = sm.OLS(y, X_final).fit(cov_type='HC3')
        # p 值可能因自由度微小差异略有不同, 用相对精度
        np.testing.assert_allclose(
            result['p_value'], sm_result.pvalues[0], rtol=1e-6,
            err_msg=(
                f"p 值不一致: 项目={result['p_value']}, "
                f"statsmodels={sm_result.pvalues[0]}"
            ),
        )

    def test_p_value_is_two_sided_t(self):
        """p_value = 2 * (1 - t.cdf(|t|, df)) (精度 1e-10)"""
        F, y, _ = _make_data(N=500, K=5)
        result, X_final = _run_project(F, y, target_idx=0)
        n, p = X_final.shape
        df = n - p
        expected_p = 2 * (1 - stats.t.cdf(abs(result['t_statistic']), df=df))
        np.testing.assert_allclose(
            result['p_value'], expected_p, atol=1e-10,
            err_msg="p_value != 2 * (1 - t.cdf(|t|, df))",
        )


# =============================================================================
# 7. 截距一致性
# =============================================================================

class TestInterceptConsistency:
    """截距处理一致性 (O4.9.1)"""

    def test_nonzero_intercept_coefficient_unbiased(self):
        """Y = 0.5*D_k + 1.0 (非零截距), 系数估计接近 0.5 (atol=0.05)"""
        rng = np.random.default_rng(42)
        N, K = 500, 5
        F = rng.standard_normal((N, K))
        true_beta = np.array([0.5, 0.0, 0.0, 0.0, 0.0])
        intercept = 1.0  # 非零截距
        y = F @ true_beta + intercept + 0.1 * rng.standard_normal(N)

        result, _ = _run_project(F, y, target_idx=0)
        np.testing.assert_allclose(
            result['coefficient'], 0.5, atol=0.05,
            err_msg=f"非零截距下系数有偏: {result['coefficient']}",
        )

    def test_intercept_does_not_affect_coef_with_statsmodels(self):
        """非零截距下, 项目系数与 statsmodels 一致 (精度 1e-10)"""
        rng = np.random.default_rng(42)
        N, K = 500, 5
        F = rng.standard_normal((N, K))
        true_beta = np.array([0.5, 0.0, 0.0, 0.0, 0.0])
        y = F @ true_beta + 1.0 + 0.1 * rng.standard_normal(N)

        result, X_final = _run_project(F, y, target_idx=0)
        sm_result = sm.OLS(y, X_final).fit()
        np.testing.assert_allclose(
            result['coefficient'], sm_result.params[0], atol=1e-10,
            err_msg="非零截距下项目系数与 statsmodels 不一致",
        )


# =============================================================================
# 8. BH 多重检验校正
# =============================================================================

class TestBHCorrection:
    """Benjamini-Hochberg 多重检验校正手工校验"""

    def test_bh_correction_matches_manual(self):
        """项目 BH 校正与手工排序计算一致 (精度 1e-10)"""
        F, y, _ = _make_data(N=300, K=5)
        test = FactorSignificanceTest(method='double_lasso', cv_folds=3)
        test.F_ = F
        test.y_ = y
        test.factor_names_ = [f'f{k}' for k in range(5)]
        results = test.test_all_factors(correction='benjamini_hochberg')

        # 手工 BH 计算 (与 statsmodels.stats.multitest.multipletests 一致)
        # 1. p 值升序排序 (最小 p = rank 1, 最大 p = rank K)
        # 2. 从大到小处理 (rank K → rank 1), bh = p * K / rank
        # 3. 取累积最小, clip 到 [0, 1]
        names = [f'f{k}' for k in range(5)]
        p_values = np.array([results[n]['p_value'] for n in names])
        K = len(names)

        order = np.argsort(p_values)  # 升序
        bh_adjusted = np.zeros(K)
        prev = 1.0
        for i in range(K - 1, -1, -1):  # 从大到小
            rank = i + 1
            idx = order[i]
            bh = p_values[idx] * K / rank
            prev = min(prev, bh)
            bh_adjusted[idx] = min(prev, 1.0)

        for i, name in enumerate(names):
            np.testing.assert_allclose(
                results[name]['p_value_adjusted'], bh_adjusted[i], atol=1e-10,
                err_msg=(
                    f"BH 校正不一致 {name}: 项目={results[name]['p_value_adjusted']}, "
                    f"手工={bh_adjusted[i]}"
                ),
            )

    def test_bonferroni_correction_matches_manual(self):
        """Bonferroni 校正 = p * K (clip 到 1.0)"""
        F, y, _ = _make_data(N=300, K=5)
        test = FactorSignificanceTest(method='double_lasso', cv_folds=3)
        test.F_ = F
        test.y_ = y
        test.factor_names_ = [f'f{k}' for k in range(5)]
        results = test.test_all_factors(correction='bonferroni')

        K = 5
        for k in range(K):
            name = f'f{k}'
            expected = min(results[name]['p_value'] * K, 1.0)
            np.testing.assert_allclose(
                results[name]['p_value_adjusted'], expected, atol=1e-10,
                err_msg=f"Bonferroni 校正不一致 {name}",
            )


# =============================================================================
# T4 v3.0.0: KS 迁移检测 BH-FDR 校正手工校验
# =============================================================================

class TestKSMigrationBHCorrection:
    """T4 v3.0.0: _ks_migration_significance BH-FDR 校正手工校验

    校验 _ks_migration_significance (pipelines_v2.py) 的 BH 路径与手工计算一致。
    与 TestBHCorrection 不同, 这里测试的是 KS 迁移检测路径, 而非 FactorSignificanceTest。

    黄金参考: p=[0.01, 0.04, 0.03, 0.20, 0.50], K=5
        p_adj = [0.05, 0.0667, 0.0667, 0.25, 0.50]
        min_p_value_adjusted = 0.05
    """

    def test_bh_golden_sample_p_adj(self):
        """BH 黄金参考: p_adj 与手工计算 [0.05, 0.0667, 0.0667, 0.25, 0.50] 一致"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance

        target_p = [0.01, 0.04, 0.03, 0.20, 0.50]
        # 构造可控 p 值: monkeypatch scipy.stats.ks_2samp
        import factor_pipeline.pipelines_v2 as pv2
        import pandas as pd

        call_state = {'idx': 0}
        def fake_ks_2samp(a, b):
            p = target_p[call_state['idx'] % len(target_p)]
            call_state['idx'] += 1
            return 0.5, float(p)

        # _ks_migration_significance 内部通过模块级 _scipy_stats.ks_2samp 调用
        original = pv2._scipy_stats.ks_2samp
        pv2._scipy_stats.ks_2samp = fake_ks_2samp
        try:
            hist = pd.DataFrame(
                np.random.RandomState(42).randn(100, 5),
                columns=[f'f{i}' for i in range(5)]
            )
            recent = pd.DataFrame(
                np.random.RandomState(43).randn(100, 5),
                columns=[f'f{i}' for i in range(5)]
            )
            is_sig, min_p, details = _ks_migration_significance(
                hist, recent, alpha=0.05
            )
        finally:
            pv2._scipy_stats.ks_2samp = original

        # 期望 p_adj (原列顺序, atol=1e-4)
        expected_p_adj = [0.05, 0.0667, 0.0667, 0.25, 0.50]
        actual_p_adj = [c['p_value_adjusted'] for c in details['per_column']]
        np.testing.assert_allclose(
            actual_p_adj, expected_p_adj, atol=1e-4,
            err_msg=f"BH p_adj 不一致: 实际 {actual_p_adj}, 期望 {expected_p_adj}",
        )

        # min_p_value_adjusted
        np.testing.assert_allclose(
            details['min_p_value_adjusted'], 0.05, atol=1e-10,
            err_msg="min_p_value_adjusted 不一致",
        )
        # min_p_value (未校正)
        np.testing.assert_allclose(
            min_p, 0.01, atol=1e-10,
            err_msg="min_p_value 不一致",
        )
        # is_significant: 0.05 < 0.05 = False
        assert is_sig is False, (
            f"is_sig 期望 False (0.05 < 0.05 不成立), 实际 {is_sig}"
        )
        # correction_method 字段
        assert details['correction_method'] == 'benjamini_hochberg'

    def test_bh_less_conservative_than_bonferroni(self):
        """BH 检测力 >= Bonferroni (10 列, BH 3 个 vs Bonferroni 1 个)"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance
        import factor_pipeline.pipelines_v2 as pv2
        import pandas as pd

        target_p = [0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.10, 0.30, 0.50]

        def run_with_p_values(p_values, correction_method):
            call_state = {'idx': 0}
            def fake_ks_2samp(a, b):
                p = p_values[call_state['idx'] % len(p_values)]
                call_state['idx'] += 1
                return 0.5, float(p)
            original = pv2._scipy_stats.ks_2samp
            pv2._scipy_stats.ks_2samp = fake_ks_2samp
            try:
                hist = pd.DataFrame(
                    np.random.RandomState(42).randn(100, len(p_values)),
                    columns=[f'f{i}' for i in range(len(p_values))]
                )
                recent = pd.DataFrame(
                    np.random.RandomState(43).randn(100, len(p_values)),
                    columns=[f'f{i}' for i in range(len(p_values))]
                )
                return _ks_migration_significance(
                    hist, recent, alpha=0.05, correction_method=correction_method
                )
            finally:
                pv2._scipy_stats.ks_2samp = original

        # Bonferroni 路径
        is_sig_bonf, _, details_bonf = run_with_p_values(target_p, 'bonferroni')
        bonf_sig_count = sum(
            1 for c in details_bonf['per_column']
            if c['p_value'] < details_bonf['alpha_corrected']
        )

        # BH 路径
        is_sig_bh, _, details_bh = run_with_p_values(target_p, 'benjamini_hochberg')
        bh_sig_count = sum(
            1 for c in details_bh['per_column']
            if c['p_value_adjusted'] < 0.05
        )

        assert bonf_sig_count == 1, f"Bonferroni 期望 1 个显著, 实际 {bonf_sig_count}"
        assert bh_sig_count == 3, f"BH 期望 3 个显著, 实际 {bh_sig_count}"
        assert bh_sig_count >= bonf_sig_count, "BH 检测数应 >= Bonferroni"

    def test_bonferroni_backward_compat(self):
        """Bonferroni 路径向后兼容: alpha_corrected / bonferroni_correction 字段保留"""
        from factor_pipeline.pipelines_v2 import _ks_migration_significance
        import pandas as pd

        np.random.seed(42)
        hist = pd.DataFrame(np.random.randn(100, 5))
        recent = pd.DataFrame(np.random.randn(100, 5) + 0.5)

        is_sig, min_p, details = _ks_migration_significance(
            hist, recent, alpha=0.05, correction_method='bonferroni'
        )

        # 旧字段保留
        assert 'alpha_corrected' in details
        assert 'bonferroni_correction' in details
        assert details['bonferroni_correction'] is True
        assert abs(details['alpha_corrected'] - 0.01) < 1e-10  # 0.05/5

        # 旧路径不应有 BH 专属字段
        assert 'min_p_value_adjusted' not in details
        assert 'correction_method' not in details
        for c in details['per_column']:
            assert 'p_value_adjusted' not in c


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == '__main__':
    # 独立运行: 打印所有校验结果
    print("=" * 70)
    print("O3b 手工数值校验: FactorSignificanceTest vs statsmodels")
    print("=" * 70)

    passed = 0
    failed = 0

    def run_check(name, fn):
        global passed, failed
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    # 1. 系数一致性
    print("\n[1] 系数一致性")
    run_check(
        "coefficient_matches_statsmodels (f0)",
        TestCoefficientConsistency().test_coefficient_matches_statsmodels,
    )
    run_check(
        "coefficient_matches_statsmodels (f2)",
        TestCoefficientConsistency().test_coefficient_matches_statsmodels_target_f2,
    )

    # 2. OLS 标准误
    print("\n[2] OLS 标准误")
    run_check(
        "ols_std_error_matches_statsmodels",
        TestOLSStandardError().test_ols_std_error_matches_statsmodels,
    )

    # 3. HC3 标准误
    print("\n[3] HC3 标准误")
    run_check(
        "hc3_std_error_matches_statsmodels",
        TestHC3StandardError().test_hc3_std_error_matches_statsmodels,
    )
    run_check(
        "hc3_differs_from_ols_under_heteroscedasticity",
        TestHC3StandardError().test_hc3_differs_from_ols_under_heteroscedasticity,
    )

    # 4. HC1 标准误
    print("\n[4] HC1 标准误")
    run_check(
        "hc1_std_error_matches_statsmodels",
        TestHC1StandardError().test_hc1_std_error_matches_statsmodels,
    )

    # 5. t 统计量
    print("\n[5] t 统计量")
    run_check(
        "t_statistic_matches_statsmodels",
        TestTStatistic().test_t_statistic_matches_statsmodels,
    )
    run_check(
        "t_statistic_is_coef_over_se",
        TestTStatistic().test_t_statistic_is_coef_over_se,
    )

    # 6. p 值
    print("\n[6] p 值")
    run_check(
        "p_value_matches_statsmodels",
        TestPValue().test_p_value_matches_statsmodels,
    )
    run_check(
        "p_value_is_two_sided_t",
        TestPValue().test_p_value_is_two_sided_t,
    )

    # 7. 截距一致性
    print("\n[7] 截距一致性")
    run_check(
        "nonzero_intercept_coefficient_unbiased",
        TestInterceptConsistency().test_nonzero_intercept_coefficient_unbiased,
    )
    run_check(
        "intercept_does_not_affect_coef_with_statsmodels",
        TestInterceptConsistency().test_intercept_does_not_affect_coef_with_statsmodels,
    )

    # 8. BH 校正
    print("\n[8] BH 多重检验校正")
    run_check(
        "bh_correction_matches_manual",
        TestBHCorrection().test_bh_correction_matches_manual,
    )
    run_check(
        "bonferroni_correction_matches_manual",
        TestBHCorrection().test_bonferroni_correction_matches_manual,
    )

    print("\n" + "=" * 70)
    print(f"总计: {passed} passed, {failed} failed")
    print("=" * 70)
    exit(0 if failed == 0 else 1)
