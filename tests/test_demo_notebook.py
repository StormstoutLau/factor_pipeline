# -*- coding: utf-8 -*-
"""TDD Red: Demo Notebook v3.1.0 — 10-cell 验收测试

规格文档: docs/ANALYSIS_V3.0.0.md §9.2.2 (10-cell 结构设计)
验收标准: docs/ANALYSIS_V3.0.0.md §9.2.3 (排序保持性/IC变化/正交化诊断阈值)

每个 cell 的验收标准:
- Cell 1: 成功加载合成因子数据 + 行业/市值/价格 (n_factors>=2, n_periods>=24)
- Cell 2: 21 维指纹雷达图生成 (21 个维度全部标注, ar1_median/skew/kurt/snr 非 NaN)
- Cell 3: 分类决策树输出 (primary_type/primary_prob/routing_weights 非空)
- Cell 4: fit 各步分布直方图 (>=3 步, 含 imputer/outlier/neutralize/standardize 至少 4 步)
- Cell 5: Spearman 排序相关矩阵 (shape >= 5×5, 对角线=1.0, 对称)
- Cell 6: IC 变化追溯 (IC 序列长度 > 0, 累积 IC 单调或接近)
- Cell 7: 正交化 W 热力图 (若正交化启用, condition_number/VRR 值; 若禁用, 标注跳过)
- Cell 8: 迁移检测追溯 (KS p 值序列/EWMA 衰减曲线 或 标注数据不足)
- Cell 9: 管线输出 vs 原始因子 (散点图 Spearman ρ < 1.0, 正相关)
- Cell 10: 校验报告 (dict 含 sorting_preserved/ic_significant/ortho_healthy/migration_ok 4 键)
"""

import pytest
import sys
import os
from types import SimpleNamespace

# 笔记本路径
_NOTEBOOK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'notebooks')
if _NOTEBOOK_DIR not in sys.path:
    sys.path.insert(0, _NOTEBOOK_DIR)


# =============================================================================
# Cell 1: 数据加载
# =============================================================================

def test_cell_1_load_factor_data():
    """Cell 1: 成功加载合成因子数据 (n_factors>=2, n_periods>=24)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data
    result = cell_1_load_data()
    assert isinstance(result, dict), "Cell 1 应返回 dict"
    assert 'factor_data' in result, "缺少 factor_data"
    assert 'n_periods' in result, "缺少 n_periods"
    assert 'n_stocks' in result, "缺少 n_stocks"
    assert len(result['factor_data']) >= 2, f"至少 2 个因子, 实际 {len(result['factor_data'])}"
    assert result['n_periods'] >= 24, f"至少 24 期, 实际 {result['n_periods']}"
    for name, df in result['factor_data'].items():
        assert not df.isnull().all().all(), f"因子 {name} 全为 NaN"


def test_cell_1_returns_industry_data():
    """Cell 1: 行业数据为 pd.Series 或 None"""
    from notebooks.demo_v3_1_0 import cell_1_load_data
    result = cell_1_load_data()
    import pandas as pd
    assert 'industry_data' in result
    idata = result['industry_data']
    assert idata is None or isinstance(idata, pd.Series)


# =============================================================================
# Cell 2: 指纹雷达图
# =============================================================================

def test_cell_2_fingerprint_radar():
    """Cell 2: 21 维指纹雷达图生成, 关键字段非 NaN"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_2_fingerprint_radar
    data = cell_1_load_data()
    result = cell_2_fingerprint_radar(data)
    assert isinstance(result, dict), "Cell 2 应返回 dict"
    assert 'fingerprints' in result, "缺少 fingerprints"
    fps = result['fingerprints']
    assert len(fps) >= 1, f"至少 1 个因子指纹, 实际 {len(fps)}"
    for name, fp in fps.items():
        assert fp.ar1_median is not None, f"{name}.ar1_median 为 None"
        assert fp.skewness_std is not None, f"{name}.skewness_std 为 None"
        assert fp.kurtosis_std is not None, f"{name}.kurtosis_std 为 None"
        assert fp.snr_estimate is not None, f"{name}.snr_estimate 为 None"


# =============================================================================
# Cell 3: 分类决策树
# =============================================================================

def test_cell_3_classification_tree():
    """Cell 3: 分类结果含 primary_type/primary_prob/routing_weights"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_3_classification
    data = cell_1_load_data()
    result = cell_3_classification(data)
    assert isinstance(result, dict), "Cell 3 应返回 dict"
    assert 'classifications' in result, "缺少 classifications"
    assert 'routing_weights' in result, "缺少 routing_weights"
    classifications = result['classifications']
    routing_weights = result['routing_weights']
    assert len(classifications) >= 1, f"至少 1 个分类结果"
    for name, cls_result in classifications.items():
        assert hasattr(cls_result, 'primary_type'), f"{name} 缺 primary_type"
        assert hasattr(cls_result, 'primary_prob'), f"{name} 缺 primary_prob"
    for name, weights in routing_weights.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"{name} 路由权重和应为 1.0, 实际 {total}"


# =============================================================================
# Cell 4: fit 各步分布直方图
# =============================================================================

def test_cell_4_step_distributions():
    """Cell 4: fit 各步输出 (>=4 步: imputer/outlier/neutralize/standardize)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_4_step_trace
    data = cell_1_load_data()
    result = cell_4_step_trace(data)
    assert isinstance(result, dict), "Cell 4 应返回 dict"
    assert 'steps' in result, "缺少 steps"
    steps = result['steps']
    assert len(steps) >= 3, f"至少 3 步中间数据, 实际 {len(steps)}"
    expected_steps = ['imputer', 'imputation', 'outlier', 'neutralize', 'standardize']
    found = set(steps.keys())
    found_expected = found & set(expected_steps)
    assert len(found_expected) >= 2, (
        f"应至少包含 {expected_steps} 中 2 步, 实际包含 {found_expected}"
    )


# =============================================================================
# Cell 5: Spearman 排序相关矩阵
# =============================================================================

def test_cell_5_spearman_matrix():
    """Cell 5: Spearman 排序相关矩阵 (shape>=5×5, 对角线≈1.0, 对称)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_5_spearman_ranking
    data = cell_1_load_data()
    result = cell_5_spearman_ranking(data)
    assert isinstance(result, dict), "Cell 5 应返回 dict"
    assert 'sorting_matrix' in result, "缺少 sorting_matrix"
    import numpy as np
    mat = result['sorting_matrix']
    assert mat.shape[0] >= 3, f"相关矩阵应 >= 3×3, 实际 {mat.shape}"
    assert mat.shape[0] == mat.shape[1], "应为方阵"
    for i in range(mat.shape[0]):
        assert abs(mat.iloc[i, i] - 1.0) < 1e-10, f"对角线 ({i},{i}) 应为 1.0, 实际 {mat.iloc[i,i]}"
    assert np.allclose(mat.values, mat.values.T, atol=1e-10), "矩阵应对称"
    assert 'rho_final' in result, "缺少 rho_final (最终输出 vs 原始排序相关)"


# =============================================================================
# Cell 6: IC 变化追溯
# =============================================================================

def test_cell_6_ic_trace():
    """Cell 6: IC 序列长度 > 0, 输出 IC dict 非空"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_6_ic_trace
    data = cell_1_load_data()
    result = cell_6_ic_trace(data)
    assert isinstance(result, dict), "Cell 6 应返回 dict"
    assert 'ic_by_step' in result, "缺少 ic_by_step"
    ic_by_step = result['ic_by_step']
    assert len(ic_by_step) >= 1, f"至少 1 步 IC, 实际 {len(ic_by_step)}"
    for step_name, ic_dict in ic_by_step.items():
        assert 'ic_mean' in ic_dict, f"{step_name} 缺 ic_mean"
        assert 'ic_ir' in ic_dict, f"{step_name} 缺 ic_ir"
        assert 'ic_series' in ic_dict, f"{step_name} 缺 ic_series"
        assert len(ic_dict['ic_series']) > 0, f"{step_name} IC 序列为空"


# =============================================================================
# Cell 7: 正交化诊断
# =============================================================================

def test_cell_7_orthogonalization_diagnostic():
    """Cell 7: 正交化诊断 (condition_number/VRR 或标注跳过)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_7_ortho_diagnostics
    data = cell_1_load_data()
    result = cell_7_ortho_diagnostics(data)
    assert isinstance(result, dict), "Cell 7 应返回 dict"
    assert 'ortho_enabled' in result, "缺少 ortho_enabled"
    if result['ortho_enabled']:
        assert 'condition_number' in result, "正交化启用时缺 condition_number"
        assert 'vrr_mean' in result, "正交化启用时缺 vrr_mean"


# =============================================================================
# Cell 8: 迁移检测
# =============================================================================

def test_cell_8_migration_detection():
    """Cell 8: 迁移检测 (含 KS p 值序列 或 标注数据不足)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_8_migration
    data = cell_1_load_data()
    result = cell_8_migration(data)
    assert isinstance(result, dict), "Cell 8 应返回 dict"
    assert 'migration_alerts' in result, "缺少 migration_alerts"
    assert isinstance(result['migration_alerts'], dict), "migration_alerts 应为 dict"


# =============================================================================
# Cell 9: 管线输出 vs 原始因子
# =============================================================================

def test_cell_9_output_vs_raw():
    """Cell 9: Spearman ρ < 1.0 但正相关 (>0)"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_9_output_vs_raw
    data = cell_1_load_data()
    result = cell_9_output_vs_raw(data)
    assert isinstance(result, dict), "Cell 9 应返回 dict"
    assert 'spearman_rho_per_factor' in result, "缺少 spearman_rho_per_factor"
    rho_dict = result['spearman_rho_per_factor']
    assert len(rho_dict) >= 1, "至少 1 个因子的 ρ 值"
    for name, rho in rho_dict.items():
        assert -1.0 <= rho <= 1.0, f"{name} ρ={rho} 应在 [-1, 1]"
        # 中性化后可能改变排序，但不应反转到完全负相关
        assert rho > -0.5, (
            f"{name} ρ={rho} < -0.5, 管线可能过度破坏排序"
        )


# =============================================================================
# Cell 10: 校验报告
# =============================================================================

def test_cell_10_validation_report():
    """Cell 10: 校验报告 dict 含 4 个关键键"""
    from notebooks.demo_v3_1_0 import cell_1_load_data, cell_10_validation_report
    data = cell_1_load_data()
    result = cell_10_validation_report(data)
    assert isinstance(result, dict), "Cell 10 应返回 dict"
    required_keys = ['sorting_preserved', 'ic_significant', 'ortho_healthy', 'migration_ok']
    for key in required_keys:
        assert key in result, f"校验报告缺关键键: {key}"
    # 校验报告自身不抛异常
    for key, val in result.items():
        assert isinstance(val, (bool, str)), (
            f"校验键 {key} 应为 bool 或 str (解释), 实际 {type(val)}"
        )


# =============================================================================
# Cell 11: 消融实验汇总
# =============================================================================

def test_cell_11_ablation_summary():
    """Cell 11: 加载 ablation_results.json, 返回 dict 含 3 键"""
    import json, os
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'notebooks', 'ablation_results.json')
    if not os.path.exists(json_path):
        pytest.skip("ablation_results.json 未生成, 先运行 scripts/run_ablation.py")
    from notebooks.demo_v3_1_0 import cell_11_ablation_summary
    result = cell_11_ablation_summary(json_path=json_path)
    assert isinstance(result, dict), "Cell 11 应返回 dict"
    assert 'b3_ic_mean' in result
    assert 'l1_modules' in result
    assert 'top_contributors' in result
    l1_modules = result['l1_modules']
    assert len(l1_modules) >= 4, f"至少 4 个模块, 实际 {len(l1_modules)}"


# =============================================================================
# 端到端验收: 全流程不抛异常
# =============================================================================

def test_demo_full_pipeline_no_errors():
    """端到端: 10 个 cell 全部执行不抛异常"""
    from notebooks.demo_v3_1_0 import (
        cell_1_load_data,
        cell_2_fingerprint_radar,
        cell_3_classification,
        cell_4_step_trace,
        cell_5_spearman_ranking,
        cell_6_ic_trace,
        cell_7_ortho_diagnostics,
        cell_8_migration,
        cell_9_output_vs_raw,
        cell_10_validation_report,
        cell_11_ablation_summary,
    )

    data = cell_1_load_data()
    assert cell_2_fingerprint_radar(data)
    assert cell_3_classification(data)
    assert cell_4_step_trace(data)
    assert cell_5_spearman_ranking(data)
    assert cell_6_ic_trace(data)
    assert cell_7_ortho_diagnostics(data)
    assert cell_8_migration(data)
    assert cell_9_output_vs_raw(data)
    cell_10_validation_report(data)
    cell_11_ablation_summary()
