# -*- coding: utf-8 -*-
"""管线级截断不变式测试 (Pipeline-Level Truncation Invariance)

不变式 (No-Lookahead Invariant)
--------------------------------
对任意截断点 t, 用 [0, t] 数据跑出的 [0, t] 期输出,
必须与用全样本 [0, T] 跑完后截取 [0, t] 期的输出一致.

这是"无前视偏差"的操作化定义: 处理前 t 期的结果不得依赖 t 之后的任何数据.
它可证伪, 且不依赖实现者是否想到某个步骤有前视.

与既有测试的分工
----------------
- ``tests/integration/test_imputer_e2e_causal.py``: 只覆盖 ImputerAdapter 单步
- ``tests/unit/test_imputer_lookahead_fix.py``: 只覆盖插补模块内部策略
- 本文件: 覆盖完整管线 5 步 (插补 → 去极值 → 变换 → 中性化 → 标准化),
  并把每一步**独立隔离**测量, 避免上游前视污染下游判定

三层结构
--------
1. ``TestIsolatedStepInvariance`` — 每步单独喂相同输入, 独立测因果性 (定位)
2. ``TestSubPipelineInvariance`` — 三条子管线端到端 (暴露传播效应)
3. ``TestTopLevelInvariance`` — ``FactorProcessingPipelineV2`` 全链路 (含指纹路由)
4. ``test_diagnostic_report`` — 输出完整测量表, 恒通过 (仪器)

缺陷登记 (xfail strict=True)
------------------------------
预期违反不变式的测试标记为 ``xfail(strict=True, raises=AssertionError)``,
reason 携带缺陷编号与实测数值. 作用: 套件保持绿; 一旦某缺陷被修复,
该 xfail 转为 "unexpectedly passing" 而报错, 强制移除标记 ——
修复不会悄悄发生, 也不会悄悄回归. ``raises=AssertionError`` 确保
其它异常类型 (ImportError / KeyError 等) 仍作为真错误暴露, 不被 xfail 吞掉.

当前登记: **无** (PL-05 / PL-07 已于 v3.3.6 修复, 详见下).

已修复:
    - DEFECT-PL-03 (2026-08): ``ProcessingAdapter`` 的 standardization 在
      ``method='auto'`` 时解析为 ``'z_score'``, 从而命中 ``_cross_sectional_zscore``
      逐日行内分支. 修复前 6.18e-01 (1800 格全差) → 修复后 0.
      连带效果: Static 端到端由 4.03e-01 降至 1.33e-02 (降 30 倍),
      证实该缺陷是 Static 的主因.
    - DEFECT-PL-01 (2026-10): ``ProcessingAdapter`` 的 outlier 由
      "全 panel flatten + auto 选型" 改为 "逐日横截面 + 构造期固定方法".
      ``auto`` 解析为 ``percentile`` (默认 1/99), detector 侧
      ``auto_select=False``; 非 percentile 方法逐行复用 detector,
      保留原截断语义. 修复前 1.68e-01 (187 格) → 修复后 0 (隔离测试);
      连带效果: Static 端到端由 1.33e-02 降至 4.72e-05, 残留为 PL-02.
    - DEFECT-PL-02 / PL-04 (2026-10, v3.3.4): ``ProcessingAdapter`` 的
      transformation 由 "全 panel flatten 拟合 λ + auto 选型" 改为
      "逐日截面 rank→正态, 构造期固定方法". 修复前 8.51e-04 (1800 格)
      → 隔离测试 0; Static 端到端 4.72e-05 → 0.
    - DEFECT-PL-06 (2026-11-04, v3.3.5): ``MixedFactorPipeline`` 的缩尾由
      "按股票全历史 3σ + fit 保存参数" 改为 "逐日截面 3σ + fit no-op".
      修复前 257/1800 格, max_abs=6.98e-01 (31/60 行) → 修复后 0 / 0.
    - DEFECT-PL-05 (2026-11-04, v3.3.6): ``ARDecoupler`` 的 AR 解耦由
      "全样本 AIC/OLS + fitted_values 充当一步预测" 改为 "前缀冻结模型 +
      三段式因果一步预测". 修复前 1653/1800 格, 8 NaN, max 8.05e-01 → 0 / 0 / 0.
    - DEFECT-PL-07 (2026-11-04, v3.3.6): 顶层差异由 PL-05 上游污染导致
      (同面板路由全程一致). 修复前 1650 格, max 1.84e+00 → 0 / 0 / 0.
      路由因果性另由 ``test_v2_pipeline_routing_is_causal`` 守卫.
    - 备注: ``PL-08-candidate`` (``_fit_ar`` 的 AIC 跨阶数不可比) **不登记为 xfail**.

已确认**满足**不变式 (6 项, 作为回归基线勿改):
    - 插补 ``ffill_ts``
    - 去极值 ``percentile`` (PL-01 修复后逐日截面, 每行只使用该行数据)
    - 变换 ``auto``→``rank`` (PL-02 修复后逐日截面无状态)
    - 中性化 (逐日截面 OLS + 静态行业哑变量)
    - 标准化 ``method='z_score'`` (逐日行内计算, 不使用 fit 参数)
    - 标准化 ``method='auto'`` (PL-03 修复后解析为 z_score, 同上)

已知未登记 (无生产路径使用, 留待需要时处理):
    - 标准化 ``method='robust' / 'min_max' / 'quantile'`` 仍走 per-column
      全样本拟合分支 → 非因果. 三条生产管线均未使用这些方法.

学术依据
--------
- Lopez de Prado (2018), Chapter on Cross-Validation Methods in Finance:
  前视偏差使样本内评估不可信 (保守引用, 章号未逐章核验)
- Hyndman & Athanasopoulos (2021) §5.10: 时序评估只能使用历史信息
"""

import numpy as np
import pandas as pd
import pytest

from factor_pipeline.adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter
from factor_pipeline.pipelines_v2 import (
    StaticFactorPipeline,
    DynamicFactorPipeline,
    MixedFactorPipeline,
)

RTOL = 1e-9
ATOL = 1e-12


# =============================================================================
# 数据构造
# =============================================================================

def _panel(n_periods: int = 100, n_stocks: int = 30, seed: int = 7,
           kind: str = 'smooth', nan_frac: float = 0.0) -> pd.DataFrame:
    """构造 (T, N) 因子面板 (行=日期, 列=股票), 遵循项目约定.

    kind:
        smooth  — 慢变高 AR1, 走 static
        skewed  — 对数正态 (偏度 > 2), 触发 Mixed 条件变换
        ar_low  — 弱自相关, 走 dynamic
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-31', periods=n_periods, freq='ME')
    stocks = [f'S{i:03d}' for i in range(n_stocks)]

    if kind == 'smooth':
        loadings = rng.standard_normal(n_stocks)
        drift = np.zeros(n_periods)
        for t in range(1, n_periods):
            drift[t] = 0.97 * drift[t - 1] + rng.standard_normal() * 0.02
        arr = loadings[None, :] + drift[:, None] + rng.standard_normal((n_periods, n_stocks)) * 0.01
    elif kind == 'skewed':
        arr = rng.lognormal(mean=0.0, sigma=1.1, size=(n_periods, n_stocks))
    elif kind == 'ar_low':
        arr = rng.standard_normal((n_periods, n_stocks))
    else:
        raise ValueError(f"unknown kind: {kind}")

    df = pd.DataFrame(arr, index=dates, columns=stocks)

    if nan_frac > 0:
        n_missing = int(nan_frac * n_periods * n_stocks)
        rows = rng.integers(1, n_periods, size=n_missing)
        cols = rng.integers(0, n_stocks, size=n_missing)
        df.values[rows, cols] = np.nan

    return df


def _industry(n_stocks: int = 30, n_industries: int = 4) -> pd.Series:
    stocks = [f'S{i:03d}' for i in range(n_stocks)]
    labels = [f'IND_{i % n_industries}' for i in range(n_stocks)]
    return pd.Series(labels, index=stocks, name='industry')


def _split(df: pd.DataFrame, frac: float = 0.6):
    t = int(len(df) * frac)
    return df, df.iloc[:t], t


# =============================================================================
# 比对工具
# =============================================================================

def _compare(full: pd.DataFrame, trunc: pd.DataFrame) -> dict:
    """比对全样本输出 (截取前 t 期) 与截断样本输出."""
    common_idx = trunc.index
    cols = [c for c in trunc.columns if c in full.columns]
    a = full.loc[common_idx, cols]
    b = trunc[cols]

    nan_mismatch = (a.isna().to_numpy() != b.isna().to_numpy())
    n_nan_mismatch = int(nan_mismatch.sum())

    a_v = a.to_numpy(dtype=float)
    b_v = b.to_numpy(dtype=float)
    with np.errstate(invalid='ignore'):
        diff = np.abs(a_v - b_v)

    finite = np.isfinite(diff)
    bad = finite & (diff > ATOL)
    n_diff = int(bad.sum())
    max_abs = float(np.max(diff[finite])) if finite.any() else 0.0

    if n_diff or n_nan_mismatch:
        row_bad = bad.any(axis=1) | nan_mismatch.any(axis=1)
        first_bad_date = common_idx[int(np.where(row_bad)[0][0])]
        col_bad = bad.any(axis=0) | nan_mismatch.any(axis=0)
        bad_columns = [cols[i] for i in np.where(col_bad)[0][:5]]
    else:
        first_bad_date = None
        bad_columns = []

    return {
        'max_abs_diff': max_abs,
        'n_diff_cells': n_diff,
        'n_nan_mismatch': n_nan_mismatch,
        'first_bad_date': first_bad_date,
        'bad_columns': bad_columns,
    }


def _assert_invariant(full: pd.DataFrame, trunc: pd.DataFrame, label: str,
                      trunc_point: int) -> None:
    rep = _compare(full, trunc)
    if rep['n_diff_cells'] > 0 or rep['n_nan_mismatch'] > 0:
        raise AssertionError(
            f"[{label}] 截断不变式违反 (截断点 t={trunc_point})\n"
            f"  含义: 前 {trunc_point} 期输出依赖了第 {trunc_point} 期之后的数据 (前视偏差)\n"
            f"  max_abs_diff   = {rep['max_abs_diff']:.6e}\n"
            f"  差异格子数      = {rep['n_diff_cells']}\n"
            f"  NaN 模式不一致  = {rep['n_nan_mismatch']}\n"
            f"  首个发散日期    = {rep['first_bad_date']}\n"
            f"  涉及列(前5)     = {rep['bad_columns']}"
        )


# =============================================================================
# 1. 步骤级独立隔离测量
# =============================================================================

class TestIsolatedStepInvariance:
    """每步单独喂**相同输入**, 独立判定因果性.

    隔离的必要性: 端到端串联时, 上游 (去极值) 的输出差异会污染下游所有步骤,
    无法判定下游步骤本身是否违反不变式. 本类为每步新建实例、喂同一份输入.
    """

    @pytest.fixture(scope='class')
    def inputs(self):
        """返回 (全样本输入, 截断输入, 截断点). 无缺失, 使各步收到同一份干净数据."""
        df = _panel(n_periods=100, n_stocks=30, seed=11, kind='smooth', nan_frac=0.0)
        return (*_split(df, frac=0.6),)

    @staticmethod
    def _run_isolated(factory, x_full: pd.DataFrame, x_trunc: pd.DataFrame):
        s_full = factory()
        s_full.fit(x_full)
        out_full = s_full.transform(x_full)

        s_trunc = factory()
        s_trunc.fit(x_trunc)
        out_trunc = s_trunc.transform(x_trunc)
        return out_full, out_trunc

    def test_imputer_ffill_ts_is_causal(self):
        """插补 ffill_ts 只回看历史 → 应满足 (v3.3.1 已硬化)."""
        df = _panel(n_periods=100, n_stocks=30, seed=11, kind='smooth', nan_frac=0.03)
        x_full, x_trunc, t = _split(df)

        out_full, out_trunc = self._run_isolated(
            lambda: ImputerAdapter(strategy='ffill_ts'), x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, 'isolated: imputer ffill_ts', t)

    def test_outlier_percentile_is_causal(self, inputs):
        """去极值 percentile: PL-01 修复后逐日截面, 每行只使用该行数据 → 应满足.

        修复前 fit 走 X.values.flatten() 全 panel, 实测 187 格差异,
        max_abs_diff=1.68e-01; 修复后应为 0.
        """
        x_full, x_trunc, t = inputs

        out_full, out_trunc = self._run_isolated(
            lambda: ProcessingAdapter(process_type='outlier', method='percentile',
                                      percentile_lower=1.0, percentile_upper=99.0),
            x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, 'isolated: outlier percentile', t)

    def test_neutralize_per_date_ols_is_causal(self, inputs):
        """中性化: 逐日截面 OLS + 静态行业哑变量 → 预期满足."""
        x_full, x_trunc, t = inputs

        out_full, out_trunc = self._run_isolated(
            lambda: NeutralizerAdapter(industry_data=_industry()), x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, 'isolated: neutralize', t)

    def test_transform_auto_is_causal(self, inputs):
        """变换 auto: PL-02 后解析为 rank, 逐日截面无状态."""
        x_full, x_trunc, t = inputs

        out_full, out_trunc = self._run_isolated(
            lambda: ProcessingAdapter(process_type='transformation', method='auto'),
            x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, 'isolated: transform auto', t)

    def test_standardize_auto_is_causal(self, inputs):
        """标准化 method='auto': 已在 DEFECT-PL-03 修复中解析为 'z_score' →
        命中 _cross_sectional_zscore 分支, 逐日行内计算, 满足不变式.

        修复前实测 max_abs_diff=6.18e-01 (1800 格全差); 修复后应为 0.
        """
        x_full, x_trunc, t = inputs

        out_full, out_trunc = self._run_isolated(
            lambda: ProcessingAdapter(process_type='standardization', method='auto'),
            x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, "isolated: standardize method='auto'", t)

    def test_standardize_cross_sectional_is_causal(self, inputs):
        """标准化 method='z_score': 逐日行内计算, 不使用 fit 参数 → 应满足.

        这与上一测试构成对照: 因果性由 method 字面量决定, 而非由 process_type 决定.
        """
        x_full, x_trunc, t = inputs

        out_full, out_trunc = self._run_isolated(
            lambda: ProcessingAdapter(process_type='standardization', method='z_score'),
            x_full, x_trunc)
        _assert_invariant(out_full, out_trunc, "isolated: standardize method='z_score'", t)


# =============================================================================
# 2. 子管线端到端不变式
# =============================================================================

class TestSubPipelineInvariance:
    """三条子管线端到端 (含步骤间传播效应)."""

    def test_static_pipeline_is_truncation_invariant(self):
        df = _panel(n_periods=100, n_stocks=30, seed=21, kind='smooth')
        x_full, x_trunc, t = _split(df)

        out_full = StaticFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_full)
        out_trunc = StaticFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_trunc)

        _assert_invariant(out_full, out_trunc, 'StaticFactorPipeline', t)

    def test_dynamic_pipeline_is_truncation_invariant(self):
        df = _panel(n_periods=100, n_stocks=30, seed=22, kind='ar_low')
        x_full, x_trunc, t = _split(df)

        out_full = DynamicFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_full)
        out_trunc = DynamicFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_trunc)

        _assert_invariant(out_full, out_trunc, 'DynamicFactorPipeline', t)

    def test_mixed_pipeline_is_truncation_invariant(self):
        """Mixed: kind='skewed' 的厚尾数据; 缩尾已逐日截面化 (PL-06)."""
        df = _panel(n_periods=100, n_stocks=30, seed=23, kind='skewed')
        x_full, x_trunc, t = _split(df)

        out_full = MixedFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_full)
        out_trunc = MixedFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(x_trunc)

        _assert_invariant(out_full, out_trunc, 'MixedFactorPipeline', t)

    def test_mixed_pipeline_output_is_unit_variance(self):
        """Mixed 输出应为单位方差.

        注意: 该契约**成立**, 因为 method='z_score' 命中 _cross_sectional_zscore 分支,
        transform 时行内重算 mean/std, 完全不使用 fit 阶段参数.
        因此 "标准化器拟合在未变换尺度上导致输出非单位方差" 的推断**不成立**.
        """
        df = _panel(n_periods=100, n_stocks=30, seed=23, kind='skewed')
        out = MixedFactorPipeline(neutralizer_params={'industry_data': _industry()}).fit_transform(df)

        per_date_std = out.std(axis=1).dropna()
        median_std = float(per_date_std.median())

        assert abs(median_std - 1.0) < 0.05, (
            f"Mixed 输出非单位方差: 逐日截面 std 中位数 = {median_std:.6f} (期望 ≈ 1.0)"
        )


# =============================================================================
# 3. 顶层管线端到端不变式 (含指纹路由)
# =============================================================================

class TestTopLevelInvariance:
    """FactorProcessingPipelineV2 全链路.

    顶层违反同时受两个因素影响, 二者都是缺陷但修法不同:
      (a) 处理参数依赖未来数据
      (b) 指纹分类/路由决策依赖未来数据 (截断后可能路由到不同子管线)
    """

    @staticmethod
    def _run(df: pd.DataFrame):
        from factor_pipeline.pipelines_v2 import FactorProcessingPipelineV2, PipelineV2Config

        pipe = FactorProcessingPipelineV2(PipelineV2Config(), strict_mode=True)
        out = pipe.fit_transform({'f': df}, industry_data=_industry())
        routes = {n: list(p.keys()) for n, p in getattr(pipe, 'factor_pipelines', {}).items()}
        return out, routes

    def test_v2_pipeline_is_truncation_invariant(self):
        df = _panel(n_periods=100, n_stocks=30, seed=31, kind='skewed')
        x_full, x_trunc, t = _split(df)

        out_full_dict, routes_full = self._run(x_full)
        out_trunc_dict, routes_trunc = self._run(x_trunc)

        assert 'f' in out_full_dict and 'f' in out_trunc_dict, (
            f"顶层管线未产出因子 f; 全样本路由={routes_full}, 截断路由={routes_trunc}"
        )

        _assert_invariant(out_full_dict['f'], out_trunc_dict['f'],
                          'FactorProcessingPipelineV2', t)

    @pytest.mark.parametrize('seed,kind', [
        (31, 'skewed'), (22, 'ar_low'), (7, 'smooth'),
    ])
    def test_v2_pipeline_routing_is_causal(self, seed, kind):
        """指纹路由 (模型选择) 必须只依赖前缀 (Varma & Simon 2006)."""
        df = _panel(n_periods=100, n_stocks=30, seed=seed, kind=kind)
        _, routes_full = self._run(df)
        _, routes_trunc = self._run(df.iloc[:int(len(df) * 0.6)])
        assert routes_full == routes_trunc, (
            f"路由决策依赖未来数据 (seed={seed}, kind={kind}): "
            f"全样本={routes_full}, 截断={routes_trunc}"
        )


# =============================================================================
# 4. 诊断报告 (仪器, 恒通过)
# =============================================================================

def test_diagnostic_report():
    """输出各步骤/各管线的截断不变式测量结果. 修复一项, 对应行 n_diff 应降为 0."""
    rows = []

    df = _panel(n_periods=100, n_stocks=30, seed=11, kind='smooth', nan_frac=0.0)
    x_full, x_trunc, _ = _split(df, frac=0.6)

    step_cases = [
        ('imputer ffill_ts', lambda: ImputerAdapter(strategy='ffill_ts')),
        ('outlier percentile', lambda: ProcessingAdapter(
            process_type='outlier', method='percentile',
            percentile_lower=1.0, percentile_upper=99.0)),
        ('neutralize', lambda: NeutralizerAdapter(industry_data=_industry())),
        ('transform auto', lambda: ProcessingAdapter(
            process_type='transformation', method='auto')),
        ("standardize 'auto'", lambda: ProcessingAdapter(
            process_type='standardization', method='auto')),
        ("standardize 'z_score'", lambda: ProcessingAdapter(
            process_type='standardization', method='z_score')),
    ]

    for label, factory in step_cases:
        s_full = factory()
        s_full.fit(x_full)
        o_full = s_full.transform(x_full)
        s_trunc = factory()
        s_trunc.fit(x_trunc)
        o_trunc = s_trunc.transform(x_trunc)
        rows.append(('step', label, _compare(o_full, o_trunc)))

    pipe_cases = [
        ('Static', 'smooth', 21, lambda kw: StaticFactorPipeline(neutralizer_params=kw)),
        ('Dynamic', 'ar_low', 22, lambda kw: DynamicFactorPipeline(neutralizer_params=kw)),
        ('Mixed', 'skewed', 23, lambda kw: MixedFactorPipeline(neutralizer_params=kw)),
    ]
    for label, kind, seed, factory in pipe_cases:
        d = _panel(n_periods=100, n_stocks=30, seed=seed, kind=kind)
        d_full, d_trunc, _ = _split(d)
        o_full = factory({'industry_data': _industry()}).fit_transform(d_full)
        o_trunc = factory({'industry_data': _industry()}).fit_transform(d_trunc)
        rows.append(('pipeline', label, _compare(o_full, o_trunc)))

    bad = [r for r in rows
           if r[2]['n_diff_cells'] > 0 or r[2]['n_nan_mismatch'] > 0]
    ok = [r for r in rows if r not in bad]

    lines = [
        '',
        '=' * 84,
        '管线级截断不变式 — 诊断报告',
        '=' * 84,
        '不变式: 用 [0,t] 跑出的 [0,t] 期输出 == 全样本跑后截取 [0,t] 期输出',
        f"容差: atol={ATOL}",
        '',
        f"{'层级':<10} {'对象':<24} {'状态':<6} {'差异格':>8} {'NaN歧':>7} {'最大绝对差':>12} {'首个发散'}",
        '-' * 84,
    ]
    for level, label, rep in rows:
        violated = rep['n_diff_cells'] > 0 or rep['n_nan_mismatch'] > 0
        first = str(rep['first_bad_date'].date()) if rep['first_bad_date'] is not None else '-'
        lines.append(
            f"{level:<10} {label:<24} {'FAIL' if violated else 'PASS':<6} "
            f"{rep['n_diff_cells']:>8} {rep['n_nan_mismatch']:>7} "
            f"{rep['max_abs_diff']:>12.3e}  {first}"
        )
    lines += [
        '-' * 84,
        f"违反不变式 {len(bad)} 项 / 满足 {len(ok)} 项 / 合计 {len(rows)} 项",
        '=' * 84,
        '',
    ]
    print('\n'.join(lines))

    assert len(rows) > 0, "诊断报告未收集到任何测量项"
