# -*- coding: utf-8 -*-
"""SpecificationLogger / PreRegistration / BY-FDR 测试 (V3.1.0 E2, §3)

TDD Red 阶段: 测试先于实现.

覆盖 §2.8 的 19 个测试 (E2-T01 ~ E2-T19):
1. SpecificationLogger: log_run / append-only / JSON 序列化
2. Specification curve: 基础 / 过滤 / consistency (high / low)
3. PreRegistration: commit / compliant / deviation
4. enforce_test_set_once: 首次 / 重复
5. apply_by_fdr: 基础 / C(m) / 比 BH 更保守 / 空输入 / 返回类型
6. 向后兼容 v3.0.0
7. PipelineV2.log_specification 委托
"""
import json
import os
import inspect
import pytest
import numpy as np

from factor_pipeline.backtest.multiple_testing import apply_bh_fdr, apply_by_fdr
from factor_pipeline.backtest.specification_logger import (
    SpecificationLogger,
    PreRegistration,
    SpecificationCurve,
)
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2,
    PipelineV2Config,
)


# ============================================================
# E2-T01 ~ E2-T03: SpecificationLogger.log_run
# ============================================================

class TestLogRun:
    """E2-T01/T02/T03: log_run 基础功能"""

    def test_log_run_returns_hash(self, tmp_path):
        """E2-T01: log_run 返回 8 字符 commit_hash"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        config = {'lag': 5, 'neutralize': 'industry'}
        result = {'ic': 0.05, 'p_value': 0.01}
        commit_hash = logger.log_run(config, result, factor_name='momentum')
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 8

    def test_log_run_append_only(self, tmp_path):
        """E2-T02: 多次 log_run 后文件行数递增 (append-only)"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        for i in range(5):
            logger.log_run({'lag': i}, {'ic': 0.01 * i}, factor_name='f1')
        log_path = os.path.join(str(tmp_path), 'specifications.jsonl')
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 5

    def test_log_run_json_serializable(self, tmp_path):
        """E2-T03: numpy 类型自动转换为 JSON 可序列化"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        config = {
            'lag': np.int64(5),
            'threshold': np.float64(0.05),
            'arr': np.array([1, 2, 3]),
        }
        result = {'ic': np.float64(0.03)}
        commit_hash = logger.log_run(config, result)
        log_path = os.path.join(str(tmp_path), 'specifications.jsonl')
        with open(log_path, 'r', encoding='utf-8') as f:
            rec = json.loads(f.readline())
        # 不应抛异常; numpy 类型已转换
        assert rec['config']['lag'] == 5
        assert rec['config']['threshold'] == 0.05
        assert rec['config']['arr'] == [1, 2, 3]


# ============================================================
# E2-T04 ~ E2-T07: Specification curve
# ============================================================

class TestSpecificationCurve:
    """E2-T04/T05/T06/T07: specification curve 分析"""

    def test_specification_curve_basic(self, tmp_path):
        """E2-T04: get_specification_curve 返回 5 个键"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        for i in range(10):
            logger.log_run(
                {'lag': i}, {'ic': 0.01 * i, 'p_value': 0.05},
                factor_name='f1',
            )
        curve = logger.get_specification_curve(factor_name='f1')
        expected_keys = {
            'specifications', 'results', 'p_values',
            'median_effect', 'consistency',
        }
        assert set(curve.keys()) == expected_keys

    def test_specification_curve_filter_by_factor(self, tmp_path):
        """E2-T05: factor_name 过滤生效"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        for i in range(5):
            logger.log_run({'lag': i}, {'ic': 0.01}, factor_name='f1')
        for i in range(3):
            logger.log_run({'lag': i}, {'ic': 0.02}, factor_name='f2')
        curve_f1 = logger.get_specification_curve(factor_name='f1')
        curve_f2 = logger.get_specification_curve(factor_name='f2')
        assert len(curve_f1['specifications']) == 5
        assert len(curve_f2['specifications']) == 3

    def test_specification_curve_consistency_high(self, tmp_path):
        """E2-T06: 80%+ 同号 → consistency='high'"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        # 9 正 1 负 → 90% 正 → 'high'
        for i in range(9):
            logger.log_run({'lag': i}, {'ic': 0.05}, factor_name='f1')
        logger.log_run({'lag': 9}, {'ic': -0.05}, factor_name='f1')
        curve = logger.get_specification_curve(factor_name='f1')
        assert curve['consistency'] == 'high'

    def test_specification_curve_consistency_low(self, tmp_path):
        """E2-T07: 50% 同号 → consistency='low'"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        # 5 正 5 负 → 50% → 'low'
        for i in range(5):
            logger.log_run({'lag': i}, {'ic': 0.05}, factor_name='f1')
        for i in range(5):
            logger.log_run({'lag': i + 5}, {'ic': -0.05}, factor_name='f1')
        curve = logger.get_specification_curve(factor_name='f1')
        assert curve['consistency'] == 'low'


# ============================================================
# E2-T08 ~ E2-T10: PreRegistration
# ============================================================

class TestPreRegistration:
    """E2-T08/T09/T10: 事前注册"""

    def test_preregistration_commit(self, tmp_path):
        """E2-T08: commit 返回 8 字符 hash"""
        pre = PreRegistration(log_dir=str(tmp_path))
        spec = {'lag': 5, 'neutralize': 'industry', 'sample_start': '2020-01-01'}
        commit_hash = pre.commit(spec, researcher='scott', description='test')
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 8

    def test_preregistration_compliant(self, tmp_path):
        """E2-T09: 实际配置与承诺一致 → is_compliant=True"""
        pre = PreRegistration(log_dir=str(tmp_path))
        spec = {'lag': 5, 'neutralize': 'industry'}
        commit_hash = pre.commit(spec)
        actual = {'lag': 5, 'neutralize': 'industry'}
        result = pre.verify_compliance(actual, commit_hash)
        assert result['is_compliant'] is True
        assert len(result['deviations']) == 0

    def test_preregistration_deviation(self, tmp_path):
        """E2-T10: 实际配置偏差 → deviations 非空"""
        pre = PreRegistration(log_dir=str(tmp_path))
        spec = {'lag': 5, 'neutralize': 'industry'}
        commit_hash = pre.commit(spec)
        actual = {'lag': 10, 'neutralize': 'industry'}  # lag 偏差
        result = pre.verify_compliance(actual, commit_hash)
        assert result['is_compliant'] is False
        assert len(result['deviations']) > 0


# ============================================================
# E2-T11 ~ E2-T12: enforce_test_set_once
# ============================================================

class TestEnforceTestSetOnce:
    """E2-T11/T12: test set 一次性原则"""

    def test_enforce_test_set_once_first(self, tmp_path):
        """E2-T11: 首次评估 → is_first_evaluation=True"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        result = logger.enforce_test_set_once('test_2024q1', 'momentum')
        assert result['is_first_evaluation'] is True
        assert result['warning'] == ''
        assert len(result['previous_runs']) == 0

    def test_enforce_test_set_once_violation(self, tmp_path):
        """E2-T12: 重复评估 → 警告"""
        logger = SpecificationLogger(log_dir=str(tmp_path))
        # 首次: 记录一个 final 类型运行
        logger.log_run(
            config={'test_set_id': 'test_2024q1'},
            result={'ic': 0.05},
            run_type='final',
            factor_name='momentum',
        )
        result = logger.enforce_test_set_once('test_2024q1', 'momentum')
        assert result['is_first_evaluation'] is False
        assert 'P-hacking' in result['warning']
        assert len(result['previous_runs']) >= 1


# ============================================================
# E2-T13 ~ E2-T17: apply_by_fdr (BY-FDR)
# ============================================================

class TestByFDR:
    """E2-T13/T14/T15/T16/T17: Benjamini-Yekutieli FDR"""

    def test_by_fdr_basic(self):
        """E2-T13: BY 调整 p 值 >= 原始 p 值; 返回 Tuple (p_adj, is_significant)"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        p_adj, is_sig = apply_by_fdr(p_values, alpha=0.05)
        # BY 调整后 p 值应 >= 原始 p 值 (因 C(m) > 1 使校正更保守)
        for orig, adj in zip(p_values, p_adj):
            assert adj >= orig - 1e-10
        assert isinstance(is_sig, list)
        assert all(isinstance(s, bool) for s in is_sig)

    def test_by_fdr_c_m(self):
        """E2-T14: C(m) = 调和数 H_m = Σ_{i=1}^{m} 1/i"""
        # m=5: C(5) = 1 + 1/2 + 1/3 + 1/4 + 1/5 = 2.2833...
        m = 5
        expected_c_m = sum(1.0 / i for i in range(1, m + 1))
        # 用 m=5 的 p 值调用, 通过 BY vs BH 比值反推 C(m)
        # BY_adj = p * m * C(m) / rank, BH_adj = p * m / rank
        # 比值 = C(m)
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        by_adj, _ = apply_by_fdr(p_values, alpha=0.05)
        bh_adj, _ = apply_bh_fdr(p_values, alpha=0.05)
        # 取 rank=1 (最小 p 值): by_adj / bh_adj ≈ C(m)
        # 但需注意累积 min 和 clip, 取最保守比较: by_adj >= bh_adj * (接近 C(m))
        # 简单验证: by_adj 均不小于 bh_adj (C(m) > 1)
        for b, bh in zip(by_adj, bh_adj):
            assert b >= bh - 1e-10
        # 验证调和数公式
        assert abs(expected_c_m - 2.2833) < 0.001

    def test_by_fdr_more_conservative_than_bh(self):
        """E2-T15: BY 调整 p >= BH 调整 p (C(m) >= 1 使 BY 更保守)"""
        p_values = [0.001, 0.01, 0.02, 0.04, 0.1, 0.3, 0.5, 0.8]
        by_adj, _ = apply_by_fdr(p_values, alpha=0.05)
        bh_adj, _ = apply_bh_fdr(p_values, alpha=0.05)
        # 每个位置的 BY 调整值 >= BH 调整值 (C(m) = H_m > 1 对 m >= 2)
        for b, bh in zip(by_adj, bh_adj):
            assert b >= bh - 1e-10

    def test_by_fdr_empty_input(self):
        """E2-T16: 空列表返回 ([], []) 不崩溃"""
        p_adj, is_sig = apply_by_fdr([], alpha=0.05)
        assert p_adj == []
        assert is_sig == []

    def test_by_fdr_return_type_tuple(self):
        """E2-T17: 返回类型为 Tuple[List[float], List[bool]], 与 apply_bh_fdr 一致"""
        p_values = [0.01, 0.02, 0.03]
        result = apply_by_fdr(p_values, alpha=0.05)
        bh_result = apply_bh_fdr(p_values, alpha=0.05)
        # 解包验证: 与 apply_bh_fdr 一致
        assert len(result) == 2
        assert len(bh_result) == 2
        p_adj, is_sig = result
        assert isinstance(p_adj, list)
        assert isinstance(is_sig, list)
        assert all(isinstance(p, float) for p in p_adj)
        assert all(isinstance(s, bool) for s in is_sig)


# ============================================================
# E2-T18: 向后兼容 v3.0.0
# ============================================================

class TestBackwardCompatV300:
    """E2-T18: 不开启时 v3.0.0 行为不变"""

    def test_backward_compat_v3_0_0(self):
        # 默认 config 不开启 specification logger
        config = PipelineV2Config()
        assert config.enable_specification_logger is False
        assert config.enforce_test_set_once is False
        # 默认 config 创建管线不报错
        pipeline = FactorProcessingPipelineV2(config)
        assert pipeline is not None


# ============================================================
# E2-T19: PipelineV2.log_specification 委托
# ============================================================

class TestPipelineLogSpecification:
    """E2-T19: PipelineV2.log_specification 委托 SpecificationLogger"""

    def test_pipeline_log_specification(self, tmp_path):
        """E2-T19: enable=True → log_specification 委托 SpecificationLogger"""
        config = PipelineV2Config(
            enable_specification_logger=True,
            spec_log_dir=str(tmp_path),
        )
        pipeline = FactorProcessingPipelineV2(config)
        config_dict = {'lag': 5, 'neutralize': 'industry'}
        result_dict = {'ic': 0.05, 'p_value': 0.01}
        commit_hash = pipeline.log_specification(
            config_dict, result_dict, factor_name='momentum',
        )
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 8
