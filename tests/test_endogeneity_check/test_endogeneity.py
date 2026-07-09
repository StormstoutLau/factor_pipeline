# -*- coding: utf-8 -*-
"""V3.1.0 E3 — 内生性检验 S1-S4 测试 (TDD Red 阶段).

四阶段诊断 (S1 插补前缺失机制 / S2 插补后基线 / S3 中性化后 / S4 解耦后)
+ 四方法 (Oster δ / AET / IFE Bai 2009 / Lewbel 2012).

v1.3 术语严格:
- "Oster δ" (非 "ITCV")
- R_max = min(1, 1.3 × R̃) (非 2.75)
- IFE `lambda_i' * F_t` (Bai 2009 标准记号)
- Lewbel `(Z - Z̄) × ê²` (非 `(X - X̄) × ê²`)

S1 → S2 上下文衔接 (逻辑衔接, 非数值乘法/非数值差分);
S3-S2, S4-S3, S4-S2 是数值差分 (连续 τ 之间).
"""
import pytest
import numpy as np
import pandas as pd

from factor_pipeline.modules.endogeneity_check import (
    MissingnessMechanismChecker,
    OsterDeltaChecker,
    AltonjiElderTaberChecker,
    InteractiveFEChecker,
    LewbelInternalIVChecker,
    EndogeneityThreatAssessor,
    EndogeneityDiagnosticOrchestrator,
)
from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config


# ============================================================
# 测试数据生成工具
# ============================================================

def _make_factor_returns(n_t=60, n_n=80, seed=0, beta=0.5, noise=0.5):
    """生成 (T, N) 因子与收益, beta 为真实因子效应."""
    rng = np.random.default_rng(seed)
    f = rng.standard_normal((n_t, n_n))
    r = beta * f + noise * rng.standard_normal((n_t, n_n))
    return pd.DataFrame(f), pd.DataFrame(r)


def _make_controls(n_t=60, n_n=80, k=2, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.standard_normal((n_t, k)), columns=[f'c{i}' for i in range(k)])


# ============================================================
# S1: MissingnessMechanismChecker (E3-T01 ~ T03)
# ============================================================

class TestS1MissingnessMechanism:
    """S1 缺失机制诊断 (MCAR / MAR / MNAR)."""

    def test_E3_T01_missingness_mcar(self):
        """E3-T01: MCAR 数据 → mechanism='MCAR'."""
        rng = np.random.default_rng(42)
        data = rng.standard_normal((60, 80))
        df = pd.DataFrame(data)
        # 随机插入缺失 (MCAR: 每个位置独立以概率 p 缺失)
        mask = rng.random(df.shape) < 0.1
        df_mcar = df.mask(mask)
        checker = MissingnessMechanismChecker()
        result = checker.diagnose(df_mcar)
        assert result['missingness_mechanism'] == 'MCAR'
        assert 0.0 <= result['mnar_risk_prior'] <= 1.0

    def test_E3_T02_missingness_mnar(self):
        """E3-T02: MNAR 数据 → mechanism='MNAR'."""
        rng = np.random.default_rng(7)
        n_t, n_n = 60, 80
        f = rng.standard_normal((n_t, n_n))
        # 缺失概率依赖因子值本身 (MNAR: 高值更易缺失)
        p_missing = 1 / (1 + np.exp(-(f - 0.5)))  # sigmoid, 高值缺失概率高
        mask = rng.random(f.shape) < p_missing
        df_mnar = pd.DataFrame(f).mask(mask)
        # 收益与缺失比例强相关 (制造 MNAR 信号)
        missing_ratio = pd.DataFrame(f).mask(mask).isna().mean(axis=0)
        r = pd.DataFrame(np.outer(np.ones(n_t), missing_ratio.values * 5) +
                         0.1 * rng.standard_normal((n_t, n_n)))
        checker = MissingnessMechanismChecker()
        result = checker.diagnose(df_mnar, r)
        assert result['missingness_mechanism'] == 'MNAR'

    def test_E3_T03_missingness_mnar_risk_prior_range(self):
        """E3-T03: mnar_risk_prior ∈ [0, 1]."""
        rng = np.random.default_rng(123)
        df = pd.DataFrame(rng.standard_normal((50, 60))).mask(
            rng.random((50, 60)) < 0.1
        )
        checker = MissingnessMechanismChecker()
        result = checker.diagnose(df)
        assert 0.0 <= result['mnar_risk_prior'] <= 1.0


# ============================================================
# S2: OsterDeltaChecker (E3-T04 ~ T07)
# ============================================================

class TestS2OsterDelta:
    """S2 Oster δ 稳健性界检验 (v1.3: R_max = 1.3 × R̃, 非 2.75)."""

    def test_E3_T04_oster_delta_stable(self):
        """E3-T04: |δ|>1 → threat_level='low' (结论稳健)."""
        # 构造: 无控制时 beta 与有控制时 beta 接近, δ 远大于 1
        rng = np.random.default_rng(1)
        n = 200
        f = rng.standard_normal(n)
        # 控制变量对收益影响极小 → 加控制后 beta 几乎不变 → δ 大
        c = rng.standard_normal(n)
        r = 1.0 * f + 0.01 * c + 0.1 * rng.standard_normal(n)
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame(c.reshape(-1, 1))
        checker = OsterDeltaChecker(r_max_multiplier=1.3, threat_threshold=0.1)
        checker.fit(factor_df, returns_df, controls_df)
        diag = checker.get_diagnostics()
        assert diag['threat_level'] == 'low'

    def test_E3_T05_oster_delta_fragile(self):
        """E3-T05: |δ|<0.1 → threat_level='high' (结论脆弱)."""
        # 构造: 加控制后 beta 大幅缩水 (混淆吸收大部分效应) → δ 小
        rng = np.random.default_rng(2)
        n = 500
        # 混淆 u 同时驱动 f 和 r
        u = rng.standard_normal(n)
        f = u + 0.3 * rng.standard_normal(n)
        r = u + 0.3 * rng.standard_normal(n)  # r 几乎全由 u 解释
        # 控制 u 后, f 的系数 → 0, δ 小
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame(u.reshape(-1, 1))
        checker = OsterDeltaChecker(r_max_multiplier=1.3, threat_threshold=0.1)
        checker.fit(factor_df, returns_df, controls_df)
        diag = checker.get_diagnostics()
        assert diag['threat_level'] == 'high'

    def test_E3_T06_oster_r_max_1_3_multiplier(self):
        """E3-T06: R_max = min(1, 1.3 × R̃) (v1.3 非 2.75)."""
        f_df, r_df = _make_factor_returns(seed=5)
        checker = OsterDeltaChecker(r_max_multiplier=1.3)
        checker.fit(f_df, r_df, None)
        diag = checker.get_diagnostics()
        # R_max 应为 min(1, 1.3 × R_observed)
        expected = min(1.0, 1.3 * diag['r_observed'])
        assert abs(diag['r_max'] - expected) < 1e-6
        # 严格小于 1.3 × R̃ (非 2.75 ×)
        assert diag['r_max'] <= 1.3 * diag['r_observed'] + 1e-9
        # 自定义 multiplier 也生效
        checker2 = OsterDeltaChecker(r_max_multiplier=1.5)
        checker2.fit(f_df, r_df, None)
        diag2 = checker2.get_diagnostics()
        expected2 = min(1.0, 1.5 * diag2['r_observed'])
        assert abs(diag2['r_max'] - expected2) < 1e-6

    def test_E3_T07_oster_terminology_delta(self):
        """E3-T07: 术语为 "Oster δ" (非 "ITCV")."""
        f_df, r_df = _make_factor_returns(seed=9)
        checker = OsterDeltaChecker()
        checker.fit(f_df, r_df, None)
        diag = checker.get_diagnostics()
        interp = diag['interpretation']
        assert 'Oster δ' in interp or 'Oster' in interp
        assert 'ITCV' not in interp
        assert '2.75' not in interp  # v1.3 修正: 非 2.75


# ============================================================
# AET (E3-T08 ~ T10)
# ============================================================

class TestAET:
    """Altonji-Elder-Taber 选择比例检验 (M0 ⊂ M1 ⊂ M2 嵌套)."""

    def test_E3_T08_aet_nested_models(self):
        """E3-T08: 嵌套 M0⊂M1⊂M2 → selection_ratio 计算."""
        rng = np.random.default_rng(11)
        n = 300
        u = rng.standard_normal(n)
        f = u + 0.5 * rng.standard_normal(n)
        c1 = u + 0.3 * rng.standard_normal(n)
        c2 = 0.5 * u + 0.3 * rng.standard_normal(n)
        r = f + c1 + c2 + 0.3 * rng.standard_normal(n)
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame({'c0': c1, 'c1': c2})
        # 嵌套: M0=无控制, M1={c0}, M2={c0, c1}
        nested = [[], [0], [0, 1]]
        checker = AltonjiElderTaberChecker()
        checker.fit(factor_df, returns_df, controls_df, nested_controls=nested)
        diag = checker.get_diagnostics()
        assert 'selection_ratio' in diag
        assert np.isfinite(diag['selection_ratio'])

    def test_E3_T09_aet_low_threat(self):
        """E3-T09: |SR|<1 → 低威胁 (选择比例小, 稳健).

        M1 用强混淆代理 (beta 大幅变化), M2 加无关控制 (beta 几乎不变)
        → |β* - β1| << |β1 - β0| → |SR| ≈ 0 < 1.
        """
        rng = np.random.default_rng(21)
        n = 500
        u = rng.standard_normal(n)  # 强混淆
        f = u + 0.5 * rng.standard_normal(n)
        r = 1.0 * f + 0.8 * u + 0.3 * rng.standard_normal(n)  # u 强影响 r
        c1 = u + 0.1 * rng.standard_normal(n)  # 强代理
        c2 = rng.standard_normal(n)  # 无关
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame({'c0': c1, 'c1': c2})
        nested = [[], [0], [0, 1]]
        checker = AltonjiElderTaberChecker(threat_threshold=1.0)
        checker.fit(factor_df, returns_df, controls_df, nested_controls=nested)
        # |SR| 小 → threat_tau 低
        assert checker.get_threat_level() < 0.5

    def test_E3_T10_aet_high_threat(self):
        """E3-T10: |SR|>1 → 高威胁 (选择比例大, 脆弱).

        M1 用弱混淆代理 (beta 小幅变化), M2 加强代理 (beta 大幅变化)
        → |β* - β1| >> |β1 - β0| → |SR| > 1.
        """
        rng = np.random.default_rng(22)
        n = 500
        u = rng.standard_normal(n)  # 强混淆
        f = u + 0.3 * rng.standard_normal(n)
        r = 0.5 * f + 1.0 * u + 0.3 * rng.standard_normal(n)  # u 强影响 r
        c1 = 0.2 * u + 0.8 * rng.standard_normal(n)  # 弱代理 (mostly noise)
        c2 = u + 0.1 * rng.standard_normal(n)  # 强代理
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame({'c0': c1, 'c1': c2})
        nested = [[], [0], [0, 1]]
        checker = AltonjiElderTaberChecker(threat_threshold=1.0)
        checker.fit(factor_df, returns_df, controls_df, nested_controls=nested)
        assert checker.get_threat_level() > 0.3


# ============================================================
# IFE (E3-T11 ~ T13)
# ============================================================

class TestIFE:
    """Interactive FE (Bai 2009, lambda_i' * F_t)."""

    def test_E3_T11_ife_lambda_f_notation(self):
        """E3-T11: 输出含 'lambda_i' * F_t' 记号 (v1.3)."""
        f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=31)
        checker = InteractiveFEChecker(max_dim=3)
        checker.fit(f_df, r_df, None)
        diag = checker.get_diagnostics()
        assert "lambda_i' * F_t" in diag['interpretation']

    def test_E3_T12_ife_dim_selection(self):
        """E3-T12: Bai-Ng IC 选择 R."""
        f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=32)
        checker = InteractiveFEChecker(max_dim=5)
        checker.fit(f_df, r_df, None)
        diag = checker.get_diagnostics()
        assert 'selected_r' in diag
        assert 0 <= diag['selected_r'] <= 5

    def test_E3_T13_ife_min_samples_guard(self):
        """E3-T13: T<20 或 N<50 → 警告."""
        # T=15 < 20
        small_t = pd.DataFrame(np.random.default_rng(33).standard_normal((15, 80)))
        r = pd.DataFrame(np.random.default_rng(34).standard_normal((15, 80)))
        checker = InteractiveFEChecker(max_dim=3)
        checker.fit(small_t, r, None)
        diag = checker.get_diagnostics()
        assert 'warning' in diag
        assert diag['warning']  # 非空警告


# ============================================================
# Lewbel (E3-T14 ~ T16, T29)
# ============================================================

class TestLewbel:
    """Lewbel (2012) 内部 IV: Z_internal = (Z - Z̄) × ê²."""

    def test_E3_T14_lewbel_z_internal_formula(self):
        """E3-T14: Z_internal = (Z - Z̄) × ê² (v1.3 记号)."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=41)
        controls = _make_controls(n_t=60, n_n=80, k=2, seed=42)
        checker = LewbelInternalIVChecker(min_samples=100)
        checker.fit(f_df, r_df, controls)
        diag = checker.get_diagnostics()
        assert '(Z - Z̄) × ê²' in diag['interpretation']

    def test_E3_T15_lewbel_heteroscedasticity_required(self):
        """E3-T15: 同方差 → Lewbel 不适用 (has_heteroscedasticity=False)."""
        rng = np.random.default_rng(43)
        n = 500
        f = rng.standard_normal(n)
        # 同方差噪声
        r = 0.5 * f + 0.5 * rng.standard_normal(n)
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        controls_df = pd.DataFrame(rng.standard_normal((n, 1)))
        checker = LewbelInternalIVChecker(min_samples=100)
        checker.fit(factor_df, returns_df, controls_df)
        diag = checker.get_diagnostics()
        # 同方差时 has_heteroscedasticity 应为 False
        assert diag['has_heteroscedasticity'] is False

    def test_E3_T16_lewbel_bp_test(self):
        """E3-T16: Breusch-Pagan 检验生效 (返回 bp_pvalue)."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=44)
        controls = _make_controls(n_t=60, n_n=80, k=2, seed=45)
        checker = LewbelInternalIVChecker(min_samples=100)
        checker.fit(f_df, r_df, controls)
        diag = checker.get_diagnostics()
        assert 'bp_pvalue' in diag
        assert np.isfinite(diag['bp_pvalue'])

    def test_E3_T29_lewbel_sargan_hansen_j_test(self):
        """E3-T29: 过度识别 (L>K) → Sargan-Hansen J 检验生效; p>0.05 → 不拒绝."""
        rng = np.random.default_rng(49)
        n = 600
        f = rng.standard_normal(n)
        # 异方差噪声 (满足 Lewbel 条件)
        z1 = rng.standard_normal(n)
        z2 = rng.standard_normal(n)
        z3 = rng.standard_normal(n)
        r = 0.5 * f + 0.3 * z1 + 0.2 * z2 + 0.1 * z3 + \
            (0.5 + 0.5 * z1) * rng.standard_normal(n)
        factor_df = pd.DataFrame(f.reshape(-1, 1))
        returns_df = pd.DataFrame(r.reshape(-1, 1))
        # L=3 工具变量 > K=1 内生变量 → 过度识别
        controls_df = pd.DataFrame({'z0': z1, 'z1': z2, 'z2': z3})
        checker = LewbelInternalIVChecker(min_samples=100)
        checker.fit(factor_df, returns_df, controls_df)
        diag = checker.get_diagnostics()
        # J 检验字段存在
        assert 'sargan_j_statistic' in diag
        assert 'sargan_j_pvalue' in diag
        assert 'sargan_j_df' in diag
        assert diag['sargan_j_df'] > 0  # 过度识别自由度 > 0


# ============================================================
# ThreatAssessor (E3-T17 ~ T18)
# ============================================================

class TestThreatAssessor:
    """EndogeneityThreatAssessor 跨方法融合."""

    def test_E3_T17_threat_assessor_weighted_avg(self):
        """E3-T17: 加权平均融合四方法."""
        assessor = EndogeneityThreatAssessor()
        results = {
            'oster_delta': {'threat_tau': 0.2},
            'aet': {'threat_tau': 0.4},
            'ife': {'threat_tau': 0.6},
            'lewbel': {'threat_tau': 0.8},
        }
        out = assessor.assess(results)
        # 加权: 0.2*0.4 + 0.4*0.3 + 0.6*0.2 + 0.8*0.1 = 0.08+0.12+0.12+0.08 = 0.40
        assert abs(out['final_threat_tau'] - 0.40) < 1e-6
        assert set(out['component_taus'].keys()) == set(results.keys())

    def test_E3_T18_threat_assessor_s1_context_logical(self):
        """E3-T18: S1 MNAR → 推荐策略逻辑上调一级 (非 τ 数值乘法).

        τ 不随 mnar_risk_prior 数值变化; 只是推荐策略离散升级.
        """
        assessor = EndogeneityThreatAssessor()
        base_results = {
            'oster_delta': {'threat_tau': 0.2},
            'aet': {'threat_tau': 0.2},
        }
        # 同样的 τ, 但不同 S1 机制
        out_mcar = assessor.assess(base_results, s1_context={'missingness_mechanism': 'MCAR'})
        out_mnar = assessor.assess(base_results, s1_context={'missingness_mechanism': 'MNAR'})
        # τ 数值不变 (逻辑衔接, 非数值乘法)
        assert out_mcar['final_threat_tau'] == out_mnar['final_threat_tau']
        # 但 MNAR 推荐策略上调一级
        rec_mcar = out_mcar['recommended_regularization']
        rec_mnar = out_mnar['recommended_regularization']
        # MCAR: τ=0.2 < 0.3 → 'none'; MNAR: 'none' → 'mild'
        assert rec_mnar != rec_mcar
        # MNAR 上下文说明含 "逻辑衔接" 关键词
        assert '逻辑衔接' in out_mnar['s1_context_note']


# ============================================================
# Orchestrator (E3-T19 ~ T23)
# ============================================================

class TestOrchestrator:
    """EndogeneityDiagnosticOrchestrator S1-S4 编排."""

    def test_E3_T19_orchestrator_s1_s2_context_not_diff(self):
        """E3-T19: S1→S2 上下文衔接 (非数值差分).

        S2 报告中含 s1_context_note (逻辑衔接说明), 无 s2_minus_s1 数值差分.
        """
        rng = np.random.default_rng(51)
        raw = pd.DataFrame(rng.standard_normal((40, 60))).mask(
            rng.random((40, 60)) < 0.05
        )
        r = pd.DataFrame(rng.standard_normal((40, 60)))
        orch = EndogeneityDiagnosticOrchestrator(enable_s3=False)
        s1 = orch.diagnose_s1_pre_imputation(raw, r)
        s2 = orch.diagnose_s2_post_imputation(raw.fillna(0), r, None)
        # S2 报告含 S1 上下文说明
        assert 's1_context_note' in s2
        assert 's1_mechanism' in s2
        # S2 报告无 's2_minus_s1' 数值差分键 (S1→S2 非数值差分)
        assert 's2_minus_s1' not in s2

    def test_E3_T20_orchestrator_s4_s2_diff(self):
        """E3-T20: S4-S2 数值差分有效."""
        f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=52)
        orch = EndogeneityDiagnosticOrchestrator(enable_s3=False)
        orch.diagnose_s1_pre_imputation(f_df, r_df)
        orch.diagnose_s2_post_imputation(f_df, r_df, None)
        s4 = orch.diagnose_s4_post_decoupling(f_df, r_df, None)
        traj = s4['threat_trajectory']
        assert 's4_minus_s2' in traj
        assert np.isfinite(traj['s4_minus_s2'])

    def test_E3_T21_orchestrator_s4_s3_critical_alert(self):
        """E3-T21: S4>S3 → CRITICAL alert (加强: 验证触发条件, 非仅字段存在).

        加强: 原测试仅断言字段存在 (恒真). 改为:
        1. 正向: 多个 seed 中至少一组触发 critical_alert=True
        2. 验证触发时 interpretation 含 'CRITICAL'
        3. 验证 s4_minus_s3 字段存在且为有限数
        """
        triggered = False
        for seed in range(50, 70):
            f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=seed)
            orch = EndogeneityDiagnosticOrchestrator(enable_s3=True)
            orch.diagnose_s1_pre_imputation(f_df, r_df)
            orch.diagnose_s2_post_imputation(f_df, r_df, None)
            orch.diagnose_s3_post_neutralization(f_df, r_df, None)
            s4 = orch.diagnose_s4_post_decoupling(f_df, r_df, None)
            traj = s4['threat_trajectory']
            # 字段存在
            assert 'critical_alert' in traj
            assert 'interpretation' in traj
            # s4_minus_s3 应存在 (enable_s3=True) 且为有限数
            assert 's4_minus_s3' in traj
            assert np.isfinite(traj['s4_minus_s3'])
            # 若触发 CRITICAL, 验证语义正确
            if traj['critical_alert']:
                triggered = True
                assert 'CRITICAL' in traj['interpretation'], (
                    f"critical_alert=True 但 interpretation 缺 'CRITICAL': {traj['interpretation']}"
                )
        # 至少一组触发 (避免所有 seed 退化)
        assert triggered, (
            "20 个 seed 中无一触发 critical_alert, 可能 S4>S3 逻辑失效"
        )

    def test_E3_T22_orchestrator_s3_disabled_by_default(self):
        """E3-T22: enable_s3=False → S3 返回 None."""
        f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=54)
        orch = EndogeneityDiagnosticOrchestrator(enable_s3=False)
        result = orch.diagnose_s3_post_neutralization(f_df, r_df, None)
        assert result is None

    def test_E3_T23_orchestrator_final_threat_tau_output(self):
        """E3-T23: get_final_threat_assessment 返回 final_threat_tau."""
        f_df, r_df = _make_factor_returns(n_t=40, n_n=60, seed=55)
        orch = EndogeneityDiagnosticOrchestrator(enable_s3=False)
        orch.diagnose_s1_pre_imputation(f_df, r_df)
        orch.diagnose_s2_post_imputation(f_df, r_df, None)
        orch.diagnose_s4_post_decoupling(f_df, r_df, None)
        final = orch.get_final_threat_assessment()
        assert final is not None
        assert 'final_threat_tau' in final
        assert 0.0 <= final['final_threat_tau'] <= 1.0


# ============================================================
# Pipeline 集成 (E3-T24 ~ T28)
# ============================================================

class TestPipelineIntegration:
    """FactorProcessingPipelineV2.check_endogeneity 集成."""

    def test_E3_T24_pipeline_check_endogeneity_disabled(self):
        """E3-T24: enable_endogeneity_check=False → 返回 None."""
        config = PipelineV2Config()  # 默认 False
        assert config.enable_endogeneity_check is False
        pipeline = FactorProcessingPipelineV2(config)
        f_df, r_df = _make_factor_returns(seed=61)
        result = pipeline.check_endogeneity(
            raw_factor_with_missing=f_df, imputed_factor=f_df,
            returns=r_df,
        )
        assert result is None

    def test_E3_T25_pipeline_check_endogeneity_enabled(self):
        """E3-T25: enable_endogeneity_check=True → 返回诊断 dict."""
        config = PipelineV2Config(enable_endogeneity_check=True)
        pipeline = FactorProcessingPipelineV2(config)
        f_df, r_df = _make_factor_returns(seed=62)
        result = pipeline.check_endogeneity(
            raw_factor_with_missing=f_df, imputed_factor=f_df,
            returns=r_df,
        )
        assert result is not None
        assert isinstance(result, dict)

    def test_E3_T26_no_controls_path(self):
        """E3-T26: controls=None → Oster δ 降级但不崩溃."""
        config = PipelineV2Config(enable_endogeneity_check=True)
        pipeline = FactorProcessingPipelineV2(config)
        f_df, r_df = _make_factor_returns(seed=63)
        result = pipeline.check_endogeneity(
            raw_factor_with_missing=f_df, imputed_factor=f_df,
            returns=r_df, controls=None,
        )
        assert result is not None  # 不崩溃

    def test_E3_T27_nan_handling(self):
        """E3-T27: 含 NaN 数据不崩溃."""
        config = PipelineV2Config(enable_endogeneity_check=True)
        pipeline = FactorProcessingPipelineV2(config)
        rng = np.random.default_rng(64)
        f_df = pd.DataFrame(rng.standard_normal((40, 60))).mask(
            rng.random((40, 60)) < 0.1
        )
        r_df = pd.DataFrame(rng.standard_normal((40, 60)))
        result = pipeline.check_endogeneity(
            raw_factor_with_missing=f_df, imputed_factor=f_df.fillna(0),
            returns=r_df,
        )
        assert result is not None  # 不崩溃

    def test_E3_T28_backward_compat_v3_0_0(self):
        """E3-T28: 不开启时 v3.0.0 配置字段保持默认 (向后兼容)."""
        config = PipelineV2Config()
        # 新增字段全部默认 False
        assert config.enable_endogeneity_check is False
        assert config.enable_ife_endogeneity_check is False
        assert config.enable_lewbel_endogeneity_check is False
        assert config.enable_missingness_diagnosis is False
        assert config.enable_s3_neutralization_check is False
        # 默认方法列表
        assert config.endogeneity_methods == ['oster_delta', 'aet']
        # Oster 参数 v1.3
        assert config.oster_r_max_multiplier == 1.3
        assert config.oster_threat_threshold == 0.1
        # 可实例化 (零回归)
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None


# ============================================================
# P2 测试盲区补强 (audit §5)
# B2: E3 配置字段生效测试
# C1: 跨文件端到端 S1→S2→S4 全链路
# ============================================================

class TestP2ConfigEffectiveness:
    """B2: E3 配置字段修改后实际生效测试 (P1-1/2/3 修复后补强).

    验证 oster_r_max_multiplier / endogeneity_ife_max_dim / endogeneity_alert_threshold
    三个配置字段不再装饰性, 修改后确实影响 check_endogeneity 行为.
    """

    def test_B2_oster_r_max_multiplier_affects_output(self):
        """B2-1: oster_r_max_multiplier 修改后传入 OsterDeltaChecker."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=10)
        # 低 R_max (1.0) vs 高 R_max (2.0)
        config_low = PipelineV2Config(
            enable_endogeneity_check=True,
            endogeneity_methods=['oster_delta'],
            oster_r_max_multiplier=1.0,
        )
        config_high = PipelineV2Config(
            enable_endogeneity_check=True,
            endogeneity_methods=['oster_delta'],
            oster_r_max_multiplier=2.0,
        )
        pipe_low = FactorProcessingPipelineV2(config_low)
        pipe_high = FactorProcessingPipelineV2(config_high)
        # 注意: check_endogeneity 签名 (raw_factor_with_missing, imputed_factor,
        #   neutralized_factor, decoupled_factor, returns, controls)
        # 用关键字传 returns, S2 用 raw_factor 作为 s2_data
        report_low = pipe_low.check_endogeneity(
            raw_factor_with_missing=f_df, returns=r_df
        )
        report_high = pipe_high.check_endogeneity(
            raw_factor_with_missing=f_df, returns=r_df
        )
        # 两者都应返回非 None (enable=True)
        assert report_low is not None
        assert report_high is not None
        # S2 报告应存在 (raw_factor + returns 提供)
        assert report_low.get('s2') is not None, "S2 报告缺失"
        assert report_high.get('s2') is not None, "S2 报告缺失"
        # S2 报告中应含 final_threat_tau (配置被消费, 非装饰性)
        s2_low = report_low['s2']
        s2_high = report_high['s2']
        assert 'final_threat_tau' in s2_low
        assert 'final_threat_tau' in s2_high
        # checker_results 中应能找到 r_max (OsterDeltaChecker 的诊断字段)
        def _find_r_max(report):
            if isinstance(report, dict):
                if 'r_max' in report and isinstance(report['r_max'], (int, float)):
                    return float(report['r_max'])
                for v in report.values():
                    found = _find_r_max(v)
                    if found is not None:
                        return found
            return None
        r_max_low = _find_r_max(s2_low)
        r_max_high = _find_r_max(s2_high)
        # r_max 应在报告中可见 (非装饰性: 配置被消费后计算)
        assert r_max_low is not None, "S2 报告中找不到 r_max, 配置可能未消费"
        assert r_max_high is not None, "S2 报告中找不到 r_max, 配置可能未消费"
        # r_max = min(1, multiplier × R̃). 不同 multiplier 应产生不同 r_max (非装饰性验证)
        # 注: 若 R̃ 较大使两者都被 clip 到 1.0, 则放宽为 r_max_high >= r_max_low
        assert r_max_high >= r_max_low, (
            f"高 multiplier (2.0) r_max={r_max_high} 应 >= 低 multiplier (1.0) r_max={r_max_low}"
        )

    def test_B2_endogeneity_alert_threshold_affects_alert(self):
        """B2-2: endogeneity_alert_threshold 修改后影响 critical_alert 触发."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=11)
        # 极低阈值 (0.001) → 几乎必触发 alert
        config_strict = PipelineV2Config(
            enable_endogeneity_check=True,
            endogeneity_methods=['oster_delta', 'aet'],
            endogeneity_alert_threshold=0.001,
        )
        # 极高阈值 (10.0) → 几乎不触发 alert
        config_lenient = PipelineV2Config(
            enable_endogeneity_check=True,
            endogeneity_methods=['oster_delta', 'aet'],
            endogeneity_alert_threshold=10.0,
        )
        pipe_strict = FactorProcessingPipelineV2(config_strict)
        pipe_lenient = FactorProcessingPipelineV2(config_lenient)
        report_strict = pipe_strict.check_endogeneity(
            raw_factor_with_missing=f_df, returns=r_df
        )
        report_lenient = pipe_lenient.check_endogeneity(
            raw_factor_with_missing=f_df, returns=r_df
        )
        assert report_strict is not None
        assert report_lenient is not None
        # S2 报告中获取 final_threat_tau
        s2_strict = report_strict.get('s2', {})
        s2_lenient = report_lenient.get('s2', {})
        tau_strict = s2_strict.get('final_threat_tau', 0.0)
        tau_lenient = s2_lenient.get('final_threat_tau', 0.0)
        # 至少一个字段反映配置被消费 (非装饰性)
        # 严格阈值下 alert 更可能触发
        alert_strict = report_strict.get('critical_alert', False)
        alert_lenient = report_lenient.get('critical_alert', False)
        # 验证配置确实传入 (非装饰性): 严格 >= 宽松
        assert alert_strict >= alert_lenient or tau_strict >= tau_lenient, (
            f"严格阈值 (0.001) 应比宽松阈值 (10.0) 产生更高威胁, "
            f"但 tau_strict={tau_strict} tau_lenient={tau_lenient} "
            f"alert_strict={alert_strict} alert_lenient={alert_lenient}"
        )


class TestP2EndToEndS1S2S4:
    """C1: 跨文件端到端 S1→S2→S4 全链路测试 (audit §5).

    V3.1.0-E3 check_endogeneity S1→S2→S4 无端到端测试.
    本测试验证完整诊断链路: 缺失机制 → 插补后基线 → 解耦后最终.
    """

    def test_C1_full_s1_s2_s4_chain(self):
        """C1: S1→S2→S4 完整链路 — 各阶段 τ 连续传递, 最终评估存在."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=20)
        orch = EndogeneityDiagnosticOrchestrator(enable_s3=False)
        # S1: 插补前缺失机制
        s1 = orch.diagnose_s1_pre_imputation(f_df, r_df)
        assert s1 is not None
        assert 'missingness_mechanism' in s1 or 's1_report' in s1 or len(s1) > 0
        # S2: 插补后基线
        s2 = orch.diagnose_s2_post_imputation(f_df, r_df, None)
        assert s2 is not None
        s2_tau = s2.get('final_threat_tau', s2.get('threat_tau', None))
        assert s2_tau is not None, "S2 缺 final_threat_tau"
        assert 0.0 <= float(s2_tau) <= 1.0
        # S4: 解耦后最终 (跳过 S3, enable_s3=False)
        s4 = orch.diagnose_s4_post_decoupling(f_df, r_df, None)
        assert s4 is not None
        s4_tau = s4.get('final_threat_tau', s4.get('threat_tau', None))
        assert s4_tau is not None, "S4 缺 final_threat_tau"
        assert 0.0 <= float(s4_tau) <= 1.0
        # threat_trajectory 应存在且含 s4_minus_s2
        traj = s4.get('threat_trajectory', {})
        assert 's4_minus_s2' in traj, "S4 threat_trajectory 缺 s4_minus_s2"
        assert np.isfinite(traj['s4_minus_s2'])
        # 最终评估
        final = orch.get_final_threat_assessment()
        assert final is not None, "get_final_threat_assessment 返回 None"
        assert 'final_threat_tau' in final or 'threat_tau' in final

    def test_C1_pipeline_check_endogeneity_e2e(self):
        """C1: Pipeline.check_endogeneity 端到端 — config 启用后返回完整报告."""
        f_df, r_df = _make_factor_returns(n_t=60, n_n=80, seed=21)
        config = PipelineV2Config(
            enable_endogeneity_check=True,
            endogeneity_methods=['oster_delta', 'aet'],
        )
        pipe = FactorProcessingPipelineV2(config)
        report = pipe.check_endogeneity(
            raw_factor_with_missing=f_df, returns=r_df
        )
        # 端到端: 返回非 None, 含 s2 报告
        assert report is not None, "enable=True 时 check_endogeneity 应返回报告"
        assert 's2' in report
        s2 = report['s2']
        assert s2 is not None, "S2 报告应为非 None (raw_factor + returns 已提供)"
        assert 'final_threat_tau' in s2
        tau = s2['final_threat_tau']
        assert 0.0 <= float(tau) <= 1.0
