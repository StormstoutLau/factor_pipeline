# -*- coding: utf-8 -*-
"""v3.4.0 统一路由 TDD — Red Phase (T1-T14)

对应实施文档 EXECUTION_V3.4.0_UNIFIED_ROUTING.md v1.3 §10.1。
ADR: 编号待分配 (暂用号 ADR-042, 落库时回 DECISIONS.md 取号)。

Red 预期 (实施文档 §10.3):
- T1-T12 失败 (配置字段不存在 / 行为仍旧 / 方法不存在)
- T13 可能已通过 (既有 strict 行为保持)
- T14 部分失败 (旧字段 extra='ignore' 既有; 新字段默认值断言失败)
"""
import os
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

import sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
    StaticFactorPipeline,
    DynamicFactorPipeline,
    MixedFactorPipeline,
)

N_DATES = 240
N_STOCKS = 20
SEED = 42


def _make_panel(rng: np.random.Generator, ar1: float,
                n_dates: int = N_DATES, n_stocks: int = N_STOCKS) -> pd.DataFrame:
    """合成单因子面板 (rows=日期, columns=股票), AR(1) 过程."""
    eps = rng.normal(0.0, 1.0, (n_dates, n_stocks))
    y = np.zeros((n_dates, n_stocks))
    for t in range(1, n_dates):
        y[t] = ar1 * y[t - 1] + eps[t]
    idx = pd.date_range('2022-01-03', periods=n_dates, freq='B')
    return pd.DataFrame(y, index=idx,
                        columns=[f'S{i:03d}' for i in range(n_stocks)])


def _make_factor_dict(n_fin: int = 6, n_pv: int = 6) -> dict:
    """12 因子: 财务型高 AR1 + 价量型低 AR1 (实施 §10.1 注), 固定种子."""
    rng = np.random.default_rng(SEED)
    out = {}
    for i in range(n_fin):
        out[f'factor_fin_{i:02d}'] = _make_panel(rng, ar1=0.85)
    for i in range(n_pv):
        out[f'factor_pv_{i:02d}'] = _make_panel(rng, ar1=0.15)
    return out


def _direct_static(cfg: PipelineV2Config) -> StaticFactorPipeline:
    """与 _create_pipeline('static', {}, None) 参数一致的直调管道."""
    garch_params = {
        'p': cfg.static_garch_p,
        'q': cfg.static_garch_q,
        'vol': cfg.static_garch_vol,
        'min_obs': cfg.static_garch_min_obs,
    } if cfg.static_enable_garch else None
    return StaticFactorPipeline(
        neutralizer_params={},
        transformation_params={
            'method': cfg.static_transformation_method,
            'target_distribution': cfg.static_target_distribution,
        },
        enable_garch=cfg.static_enable_garch,
        garch_params=garch_params,
        module_enabled=None,
    )


def _direct_dynamic(cfg: PipelineV2Config) -> DynamicFactorPipeline:
    """与 _create_pipeline('dynamic', {}, None) 参数一致的直调管道."""
    return DynamicFactorPipeline(
        decorrelation_strength=cfg.dynamic_decorrelation_strength,
        max_ar_order=cfg.dynamic_max_ar_order,
        ar_criterion=cfg.dynamic_ar_criterion,
        neutralizer_params={},
        module_enabled=None,
    )


class _RecordingPipe:
    """透明包装: 记录 transform 调用次数, 用于断言 transform 走 factor_pipelines."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def transform(self, data):
        self.calls += 1
        return self.inner.transform(data)


class TestT1DefaultMode(unittest.TestCase):
    """T1: 默认模式与校验 (A1)."""

    def test_t1_default_unified_and_invalid_rejected(self):
        cfg = PipelineV2Config()
        self.assertEqual(cfg.pipeline_mode, 'unified',
                         "默认 pipeline_mode 应为 'unified'")
        with self.assertRaises(ValueError) as ctx:
            PipelineV2Config(pipeline_mode='x')
        msg = str(ctx.exception)
        self.assertIn('unified', msg, "错误消息应列出合法值 'unified'")
        self.assertIn('dynamic_ab', msg, "错误消息应列出合法值 'dynamic_ab'")
        # 两个合法值可构造
        PipelineV2Config(pipeline_mode='dynamic_ab')


class TestT2UnifiedBitEqual(unittest.TestCase):
    """T2: 统一输出与 StaticFactorPipeline 直调逐位等价 (A4)."""

    def test_t2_unified_matches_static_direct(self):
        factor_data = _make_factor_dict()
        cfg = PipelineV2Config()
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data)

        # 身份断言: transform 必须消费 factor_pipelines[name] 实例 (非兜底路径)
        wrappers = {}
        for name, pipes in pipe.factor_pipelines.items():
            wrappers[name] = _RecordingPipe(pipes['static'])
            pipes['static'] = wrappers[name]
        out = pipe.transform(factor_data)
        for name in factor_data:
            self.assertEqual(wrappers[name].calls, 1,
                             f"{name}: transform 应走 factor_pipelines 实例")

        direct = _direct_static(cfg)
        for name, df in factor_data.items():
            direct.fit(df)
            expected = direct.transform(df)
            self.assertIn(name, out)
            try:
                assert_frame_equal(out[name], expected, check_exact=True)
            except AssertionError as e:
                self.fail(f"统一管道输出应与 StaticFactorPipeline 直调逐位相等: {name}\n{e}")


class TestT3DynamicABBitEqual(unittest.TestCase):
    """T3: dynamic_ab 输出与 DynamicFactorPipeline 直调逐位等价 (A5)."""

    def test_t3_dynamic_ab_matches_dynamic_direct(self):
        factor_data = _make_factor_dict(n_fin=2, n_pv=2)
        cfg = PipelineV2Config(pipeline_mode='dynamic_ab')
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data)

        wrappers = {}
        for name, pipes in pipe.factor_pipelines.items():
            wrappers[name] = _RecordingPipe(pipes['dynamic'])
            pipes['dynamic'] = wrappers[name]
        out = pipe.transform(factor_data)
        for name in factor_data:
            self.assertEqual(wrappers[name].calls, 1,
                             f"{name}: transform 应走 factor_pipelines 实例")

        direct = _direct_dynamic(cfg)
        for name, df in factor_data.items():
            direct.fit(df)
            expected = direct.transform(df)
            self.assertIn(name, out)
            try:
                assert_frame_equal(out[name], expected, check_exact=True)
            except AssertionError as e:
                self.fail(f"dynamic_ab 输出应与 DynamicFactorPipeline 直调逐位相等: {name}\n{e}")


class TestT4NoMixedAuto(unittest.TestCase):
    """T4: Mixed 管道不再自动创建 (A6)."""

    def test_t4_no_mixed_in_factor_pipelines(self):
        factor_data = _make_factor_dict(n_fin=2, n_pv=2)
        pipe = FactorProcessingPipelineV2(PipelineV2Config())
        pipe.fit(factor_data)

        self.assertTrue(pipe.factor_pipelines)
        self.assertIsNone(pipe.mixed_pipeline,
                          "v3.4.0 起 mixed_pipeline 兼容回填为 None")
        for name, pipes in pipe.factor_pipelines.items():
            self.assertEqual(set(pipes.keys()), {'static'},
                             f"unified 模式下 {name} 键恒为 'static'")
            for p in pipes.values():
                self.assertNotIsInstance(p, MixedFactorPipeline)


class TestT5DeletedSymbols(unittest.TestCase):
    """T5: 删除符号 — 3 函数 ImportError; 5 字段 AttributeError (A2)."""

    def test_t5_functions_import_error(self):
        import importlib
        importlib.import_module('factor_pipeline.pipelines_v2')
        for fn in ('_get_pipeline_weights',
                   '_get_multi_dim_pipeline_weights',
                   '_apply_weighted_transform'):
            with self.assertRaises(ImportError, msg=fn):
                # from-import 语义: E6 前符号存在 → 不抛错 → Red
                exec(f"from factor_pipeline.pipelines_v2 import {fn}")

    def test_t5_dataclass_fields_gone(self):
        cfg = PipelineV2Config()
        for f in ('hard_routing_prob', 'merge_alpha', 'ks_alpha',
                  'mixed_winsor_sigma', 'enable_multi_dim_routing'):
            self.assertFalse(hasattr(cfg, f),
                             f"dataclass 字段 {f} 应已删除")


class TestT6DiagnosticsSwitch(unittest.TestCase):
    """T6: 诊断开关 — 关闭时标签全 unknown, transform 不变, 指纹摘要仍非空 (A7)."""

    def test_t6_switch_off_labels_unknown_output_unchanged(self):
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        names = list(factor_data.keys())

        cfg_on = PipelineV2Config()
        pipe_on = FactorProcessingPipelineV2(cfg_on)
        pipe_on.fit(factor_data)
        out_on = pipe_on.transform(factor_data)

        cfg_off = PipelineV2Config()
        cfg_off.enable_fingerprint_diagnostics = False
        pipe_off = FactorProcessingPipelineV2(cfg_off)
        pipe_off.fit(factor_data)
        out_off = pipe_off.transform(factor_data)

        for name in names:
            try:
                assert_frame_equal(out_off[name], out_on[name], check_exact=True)
            except AssertionError as e:
                self.fail(f"开关只影响标签, 不影响 transform: {name}\n{e}")
            cls = pipe_off.factor_classifications[name]
            self.assertEqual(cls.primary_type.value, 'unknown',
                             f"关闭诊断时 {name} 标签应为 unknown")
            self.assertAlmostEqual(cls.primary_prob, 0.0)

        # 指纹提取与 monitor 始终执行 → get_fingerprint_summary 非空
        fs = pipe_off.get_fingerprint_summary()
        self.assertFalse(fs.empty,
                         "诊断开关关闭时指纹摘要仍应非空 (提取不受开关影响)")


class TestT7SamplingFrequency(unittest.TestCase):
    """T7: infer_sampling_frequency 五档 (A7)."""

    def test_t7_five_buckets(self):
        from factor_pipeline.modules.factor_fingerprint import (
            infer_sampling_frequency,
        )

        daily = pd.date_range('2022-01-01', periods=10, freq='D')
        weekly = pd.date_range('2022-01-03', periods=10, freq='W')
        monthly = pd.date_range('2022-01-01', periods=10, freq='ME')
        intraday = pd.date_range('2022-01-03 09:30', periods=10, freq='h')
        biweekly = pd.date_range('2022-01-03', periods=10, freq='15D')
        quarterly = pd.date_range('2022-03-31', periods=10, freq='QE')
        annual = pd.date_range('2022-12-31', periods=10, freq='YE')

        # irregular: 间隔 ~450 自然日 (median > 400); 9 个等差时间点 → 8 个间隔全 450
        offsets = pd.to_timedelta(np.arange(9) * 450, unit='D')
        irregular = pd.DatetimeIndex(pd.Timestamp('2000-01-01') + offsets)

        self.assertEqual(infer_sampling_frequency(intraday), 'intraday')
        self.assertEqual(infer_sampling_frequency(daily), 'daily')
        self.assertEqual(infer_sampling_frequency(weekly), 'weekly')
        self.assertEqual(infer_sampling_frequency(biweekly), 'biweekly')
        self.assertEqual(infer_sampling_frequency(monthly), 'monthly')
        self.assertEqual(infer_sampling_frequency(quarterly), 'quarterly')
        self.assertEqual(infer_sampling_frequency(annual), 'annual')
        self.assertEqual(infer_sampling_frequency(irregular), 'irregular')
        # 非 DatetimeIndex → unknown
        self.assertEqual(infer_sampling_frequency(pd.Index(['a', 'b', 'c'])),
                         'unknown')


class TestT8SummaryTables(unittest.TestCase):
    """T8: 汇总表 — 新两列 + routing 行数 = 因子数 (A7)."""

    def test_t8_summary_columns_and_rows(self):
        factor_data = _make_factor_dict(n_fin=2, n_pv=1)
        pipe = FactorProcessingPipelineV2(PipelineV2Config())
        pipe.fit(factor_data)

        cls_summary = pipe.get_classification_summary()
        self.assertIn('execution_pipe_type', cls_summary.columns)
        self.assertIn('sampling_frequency', cls_summary.columns)
        self.assertEqual(set(cls_summary['execution_pipe_type']), {'static'})
        self.assertEqual(set(cls_summary['sampling_frequency']), {'daily'},
                         "日频面板的采样频率应为 'daily'")

        routing = pipe.get_routing_summary()
        self.assertEqual(len(routing), len(factor_data))
        for col in ('pipeline_mode', 'execution_pipe_type', 'diagnostic_type',
                    'ar1_median', 'sampling_frequency', 'n_obs', 'n_columns'):
            self.assertIn(col, routing.columns)
        self.assertEqual(set(routing['pipeline_mode']), {'unified'})
        self.assertEqual(set(routing['execution_pipe_type']), {'static'})

        # dynamic_ab 臂: execution_pipe_type 恒为 'dynamic'
        pipe_d = FactorProcessingPipelineV2(
            PipelineV2Config(pipeline_mode='dynamic_ab'))
        pipe_d.fit(factor_data)
        self.assertEqual(
            set(pipe_d.get_routing_summary()['execution_pipe_type']),
            {'dynamic'})


class TestT9SpecLogOn(unittest.TestCase):
    """T9: 规格日志开启 — 行数=因子数, 按臂派生 winsor/transformation (A8)."""

    def test_t9_unified_arm_winsor_recorded(self):
        import tempfile
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = str(Path(tmp) / 'spec_on')
            cfg = PipelineV2Config()
            cfg.enable_specification_logger = True
            cfg.spec_log_dir = log_dir
            pipe = FactorProcessingPipelineV2(cfg)
            pipe.fit(factor_data)

            jsonl = Path(log_dir) / 'specifications.jsonl'
            self.assertTrue(jsonl.exists(), "开启时 JSONL 应被创建")
            lines = [json.loads(x) for x in
                     jsonl.read_text(encoding='utf-8').splitlines() if x.strip()]
            self.assertEqual(len(lines), len(factor_data),
                             "JSONL 行数应 = 因子数")
            for rec in lines:
                self.assertEqual(rec['config']['execution_pipe_type'], 'static')
                self.assertEqual(rec['config']['winsor'], 'percentile(1,99)')
                self.assertIn('sampling_frequency', rec['config'])
                from factor_pipeline.backtest.cache_manager import (
                    CODE_VERSION as _CACHE_VERSION,
                )
                self.assertEqual(rec['config']['cache_version'], _CACHE_VERSION,
                                 "每行应带当前缓存代际")

    def test_t9_dynamic_ab_arm_no_winsor(self):
        import tempfile
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = str(Path(tmp) / 'spec_ab')
            cfg = PipelineV2Config(pipeline_mode='dynamic_ab')
            cfg.enable_specification_logger = True
            cfg.spec_log_dir = log_dir
            pipe = FactorProcessingPipelineV2(cfg)
            pipe.fit(factor_data)

            jsonl = Path(log_dir) / 'specifications.jsonl'
            self.assertTrue(jsonl.exists())
            lines = [json.loads(x) for x in
                     jsonl.read_text(encoding='utf-8').splitlines() if x.strip()]
            self.assertEqual(len(lines), len(factor_data))
            for rec in lines:
                self.assertEqual(rec['config']['execution_pipe_type'], 'dynamic')
                self.assertEqual(rec['config']['winsor'], 'none')
                self.assertEqual(rec['config']['transformation'],
                                 'ar_residual->z_score')


class TestT10SpecLogOff(unittest.TestCase):
    """T10: 规格日志关闭 — 目录不创建, 行数 0 (A8)."""

    def test_t10_no_dir_when_disabled(self):
        import tempfile
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = str(Path(tmp) / 'spec_off')
            cfg = PipelineV2Config()
            cfg.enable_specification_logger = False
            cfg.spec_log_dir = log_dir
            pipe = FactorProcessingPipelineV2(cfg)
            pipe.fit(factor_data)
            self.assertFalse(os.path.exists(log_dir),
                             "关闭时规格日志目录不应被创建 "
                             "(懒初始化的是管道侧 _spec_logger, 构造从未发生)")


class TestT11BreakMonitorDefaultOff(unittest.TestCase):
    """T11: 断点监控默认关闭 → {} (A9)."""

    def test_t11_default_returns_empty(self):
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        pipe = FactorProcessingPipelineV2(PipelineV2Config())
        pipe.fit(factor_data)
        self.assertEqual(pipe.monitor_structural_breaks(factor_data), {})


class TestT12BreakMonitorNoSideEffect(unittest.TestCase):
    """T12: 断点监控不改变 transform 输出 (A10)."""

    def test_t12_output_unchanged_after_monitor(self):
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        cfg = PipelineV2Config()
        cfg.enable_break_monitor = True
        pipe = FactorProcessingPipelineV2(cfg)
        pipe.fit(factor_data)
        out_before = pipe.transform(factor_data)

        alerts = pipe.monitor_structural_breaks(factor_data)
        self.assertIsInstance(alerts, dict)

        out_after = pipe.transform(factor_data)
        for name in factor_data:
            try:
                assert_frame_equal(out_after[name], out_before[name],
                                   check_exact=True)
            except AssertionError as e:
                self.fail(f"断点监控不得改变 transform 输出: {name}\n{e}")


class TestT13UnfittedFactor(unittest.TestCase):
    """T13: 未拟合因子 — strict 抛错 / 非 strict 跳过 (既有行为保持)."""

    def test_t13_strict_raises_and_non_strict_skips(self):
        factor_data = _make_factor_dict(n_fin=1, n_pv=1)
        name = next(iter(factor_data))

        pipe_s = FactorProcessingPipelineV2(PipelineV2Config(), strict_mode=True)
        pipe_s.fit({name: factor_data[name]})
        with self.assertRaises(ValueError):
            pipe_s.transform({'unfitted_factor': factor_data[name]})

        pipe_n = FactorProcessingPipelineV2(PipelineV2Config(), strict_mode=False)
        pipe_n.fit({name: factor_data[name]})
        out = pipe_n.transform({'unfitted_factor': factor_data[name]})
        self.assertNotIn('unfitted_factor', out)


class TestT14OldJsonCompat(unittest.TestCase):
    """T14: 旧 JSON 兼容 — 5 个旧字段被忽略, 新字段可映射 (A3)."""

    def test_t14_old_fields_ignored_new_fields_mapped(self):
        from factor_pipeline.config_v2 import PipelineV2ConfigUnified

        old = {
            'hard_routing_prob': 0.9,
            'merge_alpha': 0.5,
            'ks_alpha': 0.05,
            'mixed_winsor_sigma': 3.0,
            'transform_aggressiveness': 1.0,
        }
        cfg = PipelineV2ConfigUnified(**old)  # extra='ignore' → 成功
        for field in ('hard_routing_prob', 'merge_alpha', 'ks_alpha',
                      'mixed_winsor_sigma', 'transform_aggressiveness'):
            self.assertNotIn(field, PipelineV2ConfigUnified.model_fields,
                             f"{field} 应从 Pydantic 配置面删除")
        p2 = cfg.to_pipeline_v2_config()
        self.assertEqual(p2.pipeline_mode, 'unified')

        cfg2 = PipelineV2ConfigUnified(pipeline_mode='dynamic_ab',
                                       ab_experiment_id='AB-001')
        self.assertEqual(cfg2.pipeline_mode, 'dynamic_ab')
        self.assertEqual(cfg2.ab_experiment_id, 'AB-001')


def run_all():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestT1DefaultMode, TestT2UnifiedBitEqual, TestT3DynamicABBitEqual,
                TestT4NoMixedAuto, TestT5DeletedSymbols, TestT6DiagnosticsSwitch,
                TestT7SamplingFrequency, TestT8SummaryTables, TestT9SpecLogOn,
                TestT10SpecLogOff, TestT11BreakMonitorDefaultOff,
                TestT12BreakMonitorNoSideEffect, TestT13UnfittedFactor,
                TestT14OldJsonCompat):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == '__main__':
    run_all()
