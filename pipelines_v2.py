# -*- coding: utf-8 -*-
"""
因子处理流水线 v2.0 - 带指纹分类的增强版

在原有 Pipeline 基础上，增加因子指纹前置层，实现：
1. 先诊断分类（静态/动态/混合）
2. 再分流处理（三条差异化管道）
3. 持续监测迁移

设计哲学（与项目保持一致）：
- 数据驱动自适应：因子管道由指纹自动决定
- 类型感知路由：三种类型对应三条管道
- 学术级顺序校验：每条管道内部仍遵循五步法
- sklearn风格接口：fit/transform/fit_transform
- 中间状态追踪：指纹、分类、处理全流程可追溯
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
import logging

from .pipeline import FactorProcessingPipeline, PipelineResult
from .adapters import ImputerAdapter, ProcessingAdapter, NeutralizerAdapter, GarchWhiteningAdapter

# T3.5 (v3.0.0): 共享多重检验校正模块
try:
    from .multiple_testing import apply_bh_fdr as _apply_bh_fdr_shared
    from .multiple_testing import apply_bonferroni as _apply_bonferroni_shared
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False
from factor_pipeline.modules.factor_fingerprint import (
    FactorFingerprinter, FactorFingerprint, FactorType,
    FingerprintConfig,
    AdaptiveFactorClassifier, ClassificationConfig, ClassificationResult,
    FactorFingerprintMonitor, MonitorConfig,
    SemanticStatisticalFusion, SemanticPrior, ArbitratedResult,
)
# 引入因子解耦模块
from factor_pipeline.modules.factor_decoupler import (
    CompositeDecoupler,
    DecouplerConfig
)

logger = logging.getLogger(__name__)


# =============================================================================
# P0-1: 软路由 — 模块级函数
# =============================================================================

def _get_pipeline_weights(classification: 'ClassificationResult',
                         hard_routing_prob: float = 0.9) -> Dict[str, float]:
    """
    从 ClassificationResult 中提取管道权重，实现概率加权路由。

    规则：
    1. 高置信度 (is_hard=True 且 primary_prob > hard_routing_prob): 主类型权重 = 1.0
    2. 中等置信度: primary_type 和 secondary_type 按概率加权
    3. 所有权重归一化至和为 1.0

    Args:
        classification: 分类结果，包含 primary_type, primary_prob,
                       secondary_type, secondary_prob, is_hard
        hard_routing_prob: 硬路由概率阈值（默认 0.9）

    Returns:
        Dict[str, float]: {'static': 0.7, 'mixed': 0.3} 形式的权重字典
    """
    from factor_pipeline.modules.factor_fingerprint import FactorType

    weights: Dict[str, float] = {}

    # 高置信度硬分类：仅使用主管道
    if classification.is_hard and classification.primary_prob > hard_routing_prob:
        weights[classification.primary_type.value.lower()] = 1.0
        return weights

    # 添加主管道概率
    primary_key = classification.primary_type.value.lower()
    weights[primary_key] = classification.primary_prob

    # 添加次管道概率（如果有）
    if (classification.secondary_type is not None and
            classification.secondary_prob is not None and
            classification.secondary_prob > 0.01):
        secondary_key = classification.secondary_type.value.lower()
        weights[secondary_key] = classification.secondary_prob

    # 归一化
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights


# =============================================================================
# P3: 多维分类决策 — 利用13维指纹做多维度路由权重
# =============================================================================

def _get_multi_dim_pipeline_weights(
    fingerprint: 'FactorFingerprint',
    classification: 'ClassificationResult',
    hard_routing_prob: float = 0.9,
) -> Dict[str, float]:
    """多维指纹驱动的管道权重计算。

    五叉决策树 (v3.0.0 T1 扩展至 5 步):
    1. 基底权重: 从 ar1_median 确定初始管道概率（复用 _get_pipeline_weights）
    2. 分布形状修正: skewness/kurtosis 极端 → 向混合偏移 +0.15
    3. 稳定性修正: 低 SNR → 向动态偏移 +0.15
    4. T1 新维度修正 (v3.0.0 T1):
       4a. 尾部严重度 (gpd_shape/hill_estimator > 0.3): 重尾 → 向 mixed 偏移 +0.10
       4b. 体制不稳定 (regime_transition_prob > 0.1): → 向 dynamic 偏移 +0.10
    5. 归一化: 权重和为 1

    手工计算验证 (既有 3 步):
      基底: static=0.90, mixed=0.10, dynamic=0.00
      分布修正: skew=2.5 > 1.5, kurt=8.0 > 5.0 → mixed 偏差 +0.20
      稳定性修正: snr=1.0 → 不触发
      调整后: static=0.90, mixed=0.10+0.20=0.30, dynamic=0.00
      归一化: static=0.75, mixed=0.25, dynamic=0.00
      总和=1.0 ✓

    Args:
        fingerprint: 21维因子指纹 (v3.0.0 T1, 仅用 skewness/kurtosis/snr/gpd_shape/hill_estimator/regime_transition_prob)
        classification: 分类结果（含 ar1 驱动的初始概率）
        hard_routing_prob: 硬路由阈值

    Returns:
        Dict[str, float]: {'static': w, 'dynamic': w, 'mixed': w}
    """
    # Step 1: 基底权重（复用 ar1 驱动的分类结果）
    base_weights = _get_pipeline_weights(classification, hard_routing_prob)

    # 确保三个键都存在
    weights = {'static': base_weights.get('static', 0.0),
               'dynamic': base_weights.get('dynamic', 0.0),
               'mixed': base_weights.get('mixed', 0.0)}

    # Step 2: 分布形状修正
    # 提取指纹维度，处理 NaN
    skew = fingerprint.skewness_std
    kurt = fingerprint.kurtosis_std

    skew_valid = not (skew is None or (isinstance(skew, float) and np.isnan(skew)))
    kurt_valid = not (kurt is None or (isinstance(kurt, float) and np.isnan(kurt)))

    if skew_valid or kurt_valid:
        # 偏度修正: |skew| > 1.5 → 向 mixed 偏移
        if skew_valid and abs(skew) > 1.5:
            # 偏度越大，偏移越大（最多 0.15）
            skew_shift = min(0.15, (abs(skew) - 1.5) / 10.0)
            if weights['static'] > 0:
                weights['static'] = max(0.0, weights['static'] - skew_shift)
            if weights['dynamic'] > 0:
                weights['dynamic'] = max(0.0, weights['dynamic'] - skew_shift * 0.5)
            weights['mixed'] = weights['mixed'] + skew_shift + skew_shift * 0.5

        # 峰度修正: kurt > 5 → 向 mixed 偏移
        if kurt_valid and kurt > 5.0:
            kurt_shift = min(0.15, (kurt - 5.0) / 20.0)
            if weights['static'] > 0:
                weights['static'] = max(0.0, weights['static'] - kurt_shift)
            if weights['dynamic'] > 0:
                weights['dynamic'] = max(0.0, weights['dynamic'] - kurt_shift * 0.5)
            weights['mixed'] = weights['mixed'] + kurt_shift + kurt_shift * 0.5

    # Step 3: 稳定性修正（SNR）
    snr = fingerprint.snr_estimate
    snr_valid = not (snr is None or (isinstance(snr, float) and np.isnan(snr)))

    if snr_valid and snr < 1.0:
        # 低 SNR → 预测不稳定 → 向 dynamic 偏移
        snr_shift = min(0.15, (1.0 - snr) / 5.0)
        if weights['static'] > 0:
            weights['static'] = max(0.0, weights['static'] - snr_shift * 0.5)
        if weights['mixed'] > 0:
            weights['mixed'] = max(0.0, weights['mixed'] - snr_shift * 0.5)
        weights['dynamic'] = weights['dynamic'] + snr_shift

    # Step 4: T1 新维度修正 (v3.0.0 T1, E2)
    # 4a: 尾部严重度修正 — 重尾因子需复杂处理 → 向 mixed 偏移
    gpd_shape = fingerprint.gpd_shape
    hill_est = fingerprint.hill_estimator
    gpd_valid = not (gpd_shape is None or (isinstance(gpd_shape, float) and np.isnan(gpd_shape)))
    hill_valid = not (hill_est is None or (isinstance(hill_est, float) and np.isnan(hill_est)))

    # 尾部严重度: 优先用 gpd_shape, 否则 hill_estimator
    tail_severity = None
    if gpd_valid:
        tail_severity = abs(gpd_shape)
    elif hill_valid:
        tail_severity = abs(hill_est)

    if tail_severity is not None and tail_severity > 0.3:
        # 重尾阈值 0.3: 超过 → 向 mixed 偏移 (最多 0.10)
        tail_shift = min(0.10, (tail_severity - 0.3) / 3.0)
        if weights['static'] > 0:
            weights['static'] = max(0.0, weights['static'] - tail_shift)
        weights['mixed'] = weights['mixed'] + tail_shift

    # 4b: 体制不稳定修正 — regime 频繁转换 → 向 dynamic 偏移
    regime_trans_prob = fingerprint.regime_transition_prob
    regime_valid = not (regime_trans_prob is None or
                       (isinstance(regime_trans_prob, float) and np.isnan(regime_trans_prob)))

    if regime_valid and regime_trans_prob > 0.1:
        # 体制不稳定阈值 0.1: 超过 → 向 dynamic 偏移 (最多 0.10)
        regime_shift = min(0.10, (regime_trans_prob - 0.1) / 2.0)
        if weights['static'] > 0:
            weights['static'] = max(0.0, weights['static'] - regime_shift * 0.5)
        if weights['mixed'] > 0:
            weights['mixed'] = max(0.0, weights['mixed'] - regime_shift * 0.5)
        weights['dynamic'] = weights['dynamic'] + regime_shift

    # Step 5: 归一化
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights


def _apply_weighted_transform(
    data: pd.DataFrame,
    pipelines: Dict[str, Any],
    weights: Dict[str, float],
    **kwargs
) -> pd.DataFrame:
    """
    使用概率权重对多个管道输出进行加权混合。

    手工计算验证:
      pipeline_A 输出全 10.0, pipeline_B 输出全 20.0
      weights = {A: 0.6, B: 0.4}
      期望: 10.0 * 0.6 + 20.0 * 0.4 = 14.0 ✓

    Args:
        data: 输入因子数据
        pipelines: {'static': pipeline_instance, 'mixed': pipeline_instance, ...}
        weights: {'static': 0.6, 'mixed': 0.4}
        **kwargs: 传递给 pipeline.transform() 的额外参数

    Returns:
        pd.DataFrame: 加权混合后的因子数据
    """
    if len(weights) == 0:
        raise ValueError("权重字典不能为空")

    # 单管道路由：直接返回（退化为硬路由）
    if len(weights) == 1:
        pipeline_name = list(weights.keys())[0]
        return pipelines[pipeline_name].transform(data, **kwargs)

    # 多管道加权混合
    result = None
    for pipeline_name, weight in weights.items():
        if weight < 0.001:
            continue
        pipeline = pipelines[pipeline_name]
        transformed = pipeline.transform(data, **kwargs)
        if result is None:
            result = transformed * weight
        else:
            result = result + transformed * weight

    return result


# =============================================================================
# P2-6: 迁移显著性检验 (Kolmogorov-Smirnov) — 模块级函数
# =============================================================================

# P2.5: scipy 现为 REQUIRED 依赖 (pyproject.toml 声明), 直接导入
from scipy import stats as _scipy_stats


def _ks_migration_significance(
    historical_data: 'pd.DataFrame | pd.Series',
    recent_data: 'pd.DataFrame | pd.Series',
    alpha: float = 0.05,
    correction_method: str = 'benjamini_hochberg',
) -> Tuple[bool, float, Dict[str, Any]]:
    """
    使用 Kolmogorov-Smirnov 双样本检验判断因子迁移是否显著。

    对每列（或单列）分别进行 KS 检验, 然后按 correction_method 进行多重比较校正:
    - 'benjamini_hochberg' (默认, T4 v3.0.0): BH-FDR 校正, p_adj_(k) = p_(k) * K / rank
      累积 min 后 clip [0,1], is_significant = (min_p_value_adjusted < alpha)
    - 'bonferroni' (向后兼容): alpha_corrected = alpha / K,
      is_significant = (min_p_value < alpha_corrected)
    - 'none': 无校正, is_significant = (min_p_value < alpha)

    学术依据: Benjamini-Hochberg (1995) Controlling the false discovery rate

    黄金参考 (附录 B):
      输入 p_values = [0.01, 0.04, 0.03, 0.20, 0.50], K=5, alpha=0.05
      BH 路径:
        排序后 [0.01, 0.03, 0.04, 0.20, 0.50], rank=[1,2,3,4,5]
        bh_raw = [0.05, 0.075, 0.0667, 0.25, 0.50]
        累积 min (从大到小): prev=[0.50, 0.25, 0.0667, 0.0667, 0.05]
        p_adj (原顺序) = [0.05, 0.0667, 0.0667, 0.25, 0.50]
        min_p_value_adjusted = 0.05
        is_significant = (0.05 < 0.05) = False
      Bonferroni 路径:
        alpha_corrected = 0.05/5 = 0.01
        is_significant = (0.01 < 0.01) = False

    Args:
        historical_data: 历史因子数据 (DataFrame 或 Series)
        recent_data: 近期因子数据 (DataFrame 或 Series)
        alpha: 显著性水平，默认 0.05
        correction_method: 多重比较校正方法, 默认 'benjamini_hochberg'
            - 'benjamini_hochberg': BH-FDR (T4 v3.0.0 默认)
            - 'bonferroni': Bonferroni 校正 (向后兼容)
            - 'none': 无校正

    Returns:
        Tuple[bool, float, Dict]:
            - is_significant: 迁移是否显著
            - min_p_value: 所有列中最小的原始 p 值 (未校正)
            - details: 包含每列统计量的字典
                BH 路径: {per_column, n_columns, min_p_value, min_p_value_adjusted,
                         alpha, correction_method, method}
                Bonferroni 路径: {per_column, n_columns, min_p_value,
                                 alpha, alpha_corrected, bonferroni_correction, method}
                none 路径: {per_column, n_columns, min_p_value,
                          alpha, correction_method, method}
                per_column 每项: {column, statistic, p_value[, p_value_adjusted]}
    """
    # 参数校验
    _valid_methods = {'benjamini_hochberg', 'bonferroni', 'none'}
    if correction_method not in _valid_methods:
        raise ValueError(
            f"correction_method 必须为 {sorted(_valid_methods)}, "
            f"实际: {correction_method!r}"
        )

    # P2.5: scipy 现为 REQUIRED 依赖, 不再有 HAS_SCIPY fallback
    # 处理空数据 (保护路径, 不受 correction_method 影响)
    if historical_data.empty or recent_data.empty:
        return False, 1.0, {
            'per_column': [],
            'n_columns': 0,
            'alpha': alpha,
            'method': 'ks_2samp',
            'warning': 'empty data'
        }

    # 统一为 DataFrame
    if isinstance(historical_data, pd.Series):
        historical_data = historical_data.to_frame('factor')
    if isinstance(recent_data, pd.Series):
        recent_data = recent_data.to_frame('factor')

    # 对齐列
    common_cols = historical_data.columns.intersection(recent_data.columns)
    if len(common_cols) == 0:
        return False, 1.0, {
            'per_column': [],
            'n_columns': 0,
            'alpha': alpha,
            'method': 'ks_2samp',
            'warning': 'no common columns'
        }

    per_column = []
    p_values = []

    for col in common_cols:
        hist_vals = historical_data[col].dropna().values
        recent_vals = recent_data[col].dropna().values

        # 需要至少 5 个观测值才能进行有意义的 KS 检验
        if len(hist_vals) < 5 or len(recent_vals) < 5:
            continue

        stat, p = _scipy_stats.ks_2samp(hist_vals, recent_vals)
        per_column.append({
            'column': str(col),
            'statistic': float(stat),
            'p_value': float(p),
        })
        p_values.append(p)

    if not p_values:
        return False, 1.0, {
            'per_column': [],
            'n_columns': 0,
            'alpha': alpha,
            'method': 'ks_2samp',
            'warning': 'insufficient data'
        }

    min_p_value = float(np.min(p_values))
    n_tests = len(p_values)

    # ── 三路径分流 ──────────────────────────────────────────
    if correction_method == 'benjamini_hochberg':
        # BH-FDR 校正 (T4 v3.0.0 默认, T3.5 重构为调用共享模块)
        # 学术依据: Benjamini-Hochberg (1995)
        # 公式: p_adj_(k) = p_(k) * K / rank, 从大到小累积 min, clip [0,1]
        K = n_tests
        p_arr = np.asarray(p_values, dtype=float)
        # T3.5: 调用共享模块 (向后兼容, fallback 到内联)
        if _HAS_MULTIPLE_TESTING:
            p_adj_list, _ = _apply_bh_fdr_shared(p_arr.tolist(), alpha=alpha)
            p_adj = np.array(p_adj_list)
        else:
            order = np.argsort(p_arr)
            p_adj = np.empty_like(p_arr)
            prev = 1.0
            for i in range(K - 1, -1, -1):
                rank = i + 1
                idx = order[i]
                bh = p_arr[idx] * K / rank
                prev = min(prev, bh)
                p_adj[idx] = min(prev, 1.0)

        min_p_value_adjusted = float(np.min(p_adj))
        is_significant = (min_p_value_adjusted < alpha)

        # 将 p_value_adjusted 写入 per_column (保持原列顺序)
        for i, c in enumerate(per_column):
            c['p_value_adjusted'] = float(p_adj[i])

        details = {
            'per_column': per_column,
            'n_columns': len(per_column),
            'min_p_value': min_p_value,
            'min_p_value_adjusted': min_p_value_adjusted,
            'alpha': alpha,
            'correction_method': 'benjamini_hochberg',
            'method': 'ks_2samp',
        }

        if is_significant:
            logger.info(
                f"KS 迁移显著性检验 (BH-FDR): 显著 "
                f"(min_p_adj={min_p_value_adjusted:.4f} < alpha={alpha:.4f}), "
                f"{len(per_column)} 列参与检验"
            )
        else:
            logger.info(
                f"KS 迁移显著性检验 (BH-FDR): 不显著 "
                f"(min_p_adj={min_p_value_adjusted:.4f} >= alpha={alpha:.4f}), "
                f"{len(per_column)} 列参与检验"
            )

    elif correction_method == 'bonferroni':
        # Bonferroni 校正 (向后兼容, 旧路径字段全部保留)
        alpha_corrected = alpha / max(n_tests, 1)
        is_significant = (min_p_value < alpha_corrected)

        details = {
            'per_column': per_column,
            'n_columns': len(per_column),
            'min_p_value': min_p_value,
            'alpha': alpha,
            'alpha_corrected': alpha_corrected,
            'bonferroni_correction': True,
            'method': 'ks_2samp',
        }

        if is_significant:
            logger.info(
                f"KS 迁移显著性检验 (Bonferroni): 显著 "
                f"(min_p={min_p_value:.4f} < alpha_corrected={alpha_corrected:.4f}), "
                f"{len(per_column)} 列参与检验"
            )
        else:
            logger.info(
                f"KS 迁移显著性检验 (Bonferroni): 不显著 "
                f"(min_p={min_p_value:.4f} >= alpha_corrected={alpha_corrected:.4f}), "
                f"{len(per_column)} 列参与检验"
            )

    else:  # correction_method == 'none'
        # 无校正
        is_significant = (min_p_value < alpha)

        details = {
            'per_column': per_column,
            'n_columns': len(per_column),
            'min_p_value': min_p_value,
            'alpha': alpha,
            'correction_method': 'none',
            'method': 'ks_2samp',
        }

        if is_significant:
            logger.info(
                f"KS 迁移显著性检验 (none): 显著 "
                f"(min_p={min_p_value:.4f} < alpha={alpha:.4f}), "
                f"{len(per_column)} 列参与检验"
            )
        else:
            logger.info(
                f"KS 迁移显著性检验 (none): 不显著 "
                f"(min_p={min_p_value:.4f} >= alpha={alpha:.4f}), "
                f"{len(per_column)} 列参与检验"
            )

    return is_significant, min_p_value, details


# =============================================================================
# P1-5: 迁移权重合并 — 模块级函数
# =============================================================================

def _merge_transition_weights(
    cls_weights: Dict[str, float],
    trans_weights: Dict['FactorType', float],
    alpha: float = 0.5
) -> Dict[str, float]:
    """
    合并分类权重和迁移权重，实现平滑过渡。

    当 monitor 检测到因子类型迁移时，使用指数衰减的历史权重
    与当前分类权重进行加权平均，避免硬切换。

    手工计算验证:
      cls_weights = {dynamic: 0.58, mixed: 0.42}
      trans_weights = {STATIC: 0.21, MIXED: 0.43, DYNAMIC: 0.36}
      alpha = 0.5
      static:  0.5*0.00 + 0.5*0.21 = 0.105
      mixed:   0.5*0.42 + 0.5*0.43 = 0.425
      dynamic: 0.5*0.58 + 0.5*0.36 = 0.470
      total = 1.0 ✓

    Args:
        cls_weights: 分类权重 {'static': 0.8, 'mixed': 0.2}
        trans_weights: 迁移权重 {FactorType.STATIC: 0.21, ...}
        alpha: 迁移权重的影响因子 [0, 1]
            0.0 = 完全忽略迁移，仅使用分类权重
            1.0 = 完全使用迁移权重

    Returns:
        Dict[str, float]: 合并后的权重 {'static': 0.5, 'mixed': 0.3, 'dynamic': 0.2}
    """
    from factor_pipeline.modules.factor_fingerprint import FactorType

    if alpha <= 0.0 or not trans_weights or len(trans_weights) <= 1:
        return cls_weights

    # 转换迁移权重键为字符串
    trans_str: Dict[str, float] = {}
    for k, v in trans_weights.items():
        if isinstance(k, FactorType):
            trans_str[k.value.lower()] = v
        else:
            trans_str[str(k).lower()] = v

    # 合并
    merged: Dict[str, float] = {}
    all_keys = set(cls_weights.keys()) | set(trans_str.keys())

    for key in all_keys:
        cls_w = cls_weights.get(key, 0.0)
        trans_w = trans_str.get(key, 0.0)
        merged[key] = (1.0 - alpha) * cls_w + alpha * trans_w

    # 归一化
    total = sum(merged.values())
    if total > 0:
        merged = {k: v / total for k, v in merged.items()}

    return merged


# =============================================================================
# P0-2: 阈值校准器
# =============================================================================

@dataclass
class ThresholdCalibrator:
    """
    数据驱动的 AR(1) 阈值校准器。

    支持两种校准模式：
    1. 'percentile': 从 AR(1) 值分布中计算分位数阈值
       - dynamic_threshold = 25th percentile（约 25% 因子归为动态）
       - static_threshold = 75th percentile（约 25% 因子归为静态）
       - 中间 50% 归为混合
    2. 'preset': 使用基于市场的预设阈值
       - a_share: A股（因子普遍高自相关）→ 0.85/0.45
       - us_equity: 美股（因子自相关较低）→ 0.75/0.35
       - crypto: 加密货币（接近白噪声）→ 0.55/0.25

    边界情况处理:
    - 空列表/单值/所有相同 → 返回默认阈值 (0.80/0.40)
    - 含 NaN → 忽略 NaN 后计算
    - 全部 NaN → 返回默认阈值

    Args:
        method: 校准方法 ('percentile' 或 'preset')
        preset: 预设名称 ('a_share', 'us_equity', 'crypto')
        default_dynamic: 默认动态阈值 (回退用)
        default_static: 默认静态阈值 (回退用)
    """

    method: str = 'percentile'
    preset: str = 'us_equity'
    default_dynamic: float = 0.40
    default_static: float = 0.80

    # 市场预设阈值
    MARKET_PRESETS: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        'a_share': {'dynamic': 0.45, 'static': 0.85},
        'us_equity': {'dynamic': 0.35, 'static': 0.75},
        'crypto': {'dynamic': 0.25, 'static': 0.55},
    })

    def calibrate(self, ar1_values: List[float]) -> Dict[str, float]:
        """
        校准 AR(1) 阈值。

        Args:
            ar1_values: AR(1) 值列表（从因子指纹中提取）

        Returns:
            {'dynamic_threshold': float, 'static_threshold': float}
        """
        if self.method == 'preset':
            preset = self.MARKET_PRESETS.get(self.preset, self.MARKET_PRESETS['us_equity'])
            return {
                'dynamic_threshold': preset['dynamic'],
                'static_threshold': preset['static'],
            }

        if self.method == 'percentile':
            return self._percentile_calibrate(ar1_values)

        # 默认回退
        return {
            'dynamic_threshold': self.default_dynamic,
            'static_threshold': self.default_static,
        }

    def _percentile_calibrate(self, ar1_values: List[float]) -> Dict[str, float]:
        """分位数法校准"""
        import numpy as np

        # 清理 NaN
        clean = [v for v in ar1_values if v is not None and not (isinstance(v, float) and np.isnan(v))]

        # 边界情况：需要至少 3 个不同的值才能计算有意义的分位数
        if len(clean) < 3:
            return {
                'dynamic_threshold': self.default_dynamic,
                'static_threshold': self.default_static,
            }

        unique = set(clean)
        if len(unique) < 3:
            return {
                'dynamic_threshold': self.default_dynamic,
                'static_threshold': self.default_static,
            }

        dynamic_threshold = float(np.percentile(clean, 25))
        static_threshold = float(np.percentile(clean, 75))

        # 确保 dynamic < static，且至少保持 0.15 的间隔
        if static_threshold - dynamic_threshold < 0.15:
            center = (dynamic_threshold + static_threshold) / 2
            dynamic_threshold = max(0.10, center - 0.10)
            static_threshold = min(0.95, center + 0.10)

        return {
            'dynamic_threshold': dynamic_threshold,
            'static_threshold': static_threshold,
        }


@dataclass
class PipelineV2Config:
    """Pipeline v2.0 配置"""
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    # 动态因子解耦强度 [0, 1]，0=不解耦，1=完全AR残差
    dynamic_decorrelation_strength: float = 1.0
    # 动态因子最大AR阶数
    dynamic_max_ar_order: int = 5
    # 动态因子AR阶数选择准则
    dynamic_ar_criterion: str = 'aic'
    # 混合因子是否条件性变换
    mixed_conditional_transform: bool = True
    # 混合因子变换阈值
    mixed_skew_threshold: float = 2.0
    mixed_kurt_threshold: float = 5.0
    # 静态因子是否启用GARCH白化（默认关闭）
    static_enable_garch: bool = False
    # GARCH白化参数
    static_garch_p: int = 1
    static_garch_q: int = 1
    static_garch_vol: str = 'Garch'
    static_garch_min_obs: int = 50

    # v2.1 端到端阈值搜索新增配置 (P3 Phase 2)
    hard_routing_prob: float = 0.90
    merge_alpha: float = 0.50
    ks_alpha: float = 0.05
    mixed_winsor_sigma: float = 3.0

    # v2.6.0 E2 (P3-10'): migration_threshold 字段位置修正
    # 修正前: optimizer.py:155-158 错误设置到 config.monitor.migration_threshold
    #         (MonitorConfig 无此字段, hasattr 静默跳过, 参数被丢弃)
    # 修正后: 字段位于 config 本身, 默认值与 PipelineV2ConfigUnified.migration_threshold 对齐
    migration_threshold: float = 0.10

    # v2.5.0 正交化配置 (Layer 2, ADR-020) — Optional[Any] 避免循环导入
    # 接收 OrthogonalizationConfig (Pydantic) 整对象, enabled=False 时 None
    orthogonalization: Optional[Any] = None

    # v3.0.0 T1 (E2): 多维指纹路由开关 (默认 False, 向后兼容)
    # True: transform 使用 _get_multi_dim_pipeline_weights (含 T1 tail/regime 修正)
    # False: 走旧路径 _get_pipeline_weights (仅 ar1 驱动)
    enable_multi_dim_routing: bool = False

    # v3.0.0 T3.4: CUSUM 在线漂移监测开关 (默认 False, 向后兼容)
    # True: 启用 CUSUM 监测因子值矩阵的横截面统计量 (均值/标准差)
    # 两个 CUSUM 独立监测 (序贯检验, 无需 BH-FDR), h=5.5σ 补偿误报率叠加
    enable_cusum_drift_monitor: bool = False
    cusum_k: float = 0.5       # slack (0.5σ, 检测半漂移, T3.3 校准验证)
    cusum_h: float = 5.5       # trigger (5.5σ, 两个 CUSUM 叠加补偿)

    @classmethod
    def from_unified(cls, unified) -> 'PipelineV2Config':
        """从 PipelineV2ConfigUnified (Pydantic) 构造 dataclass — 桥接层 (Fix 2)

        备选入口: 等价于 unified.to_pipeline_v2_config()。
        提供此方法使 dataclass 侧也可主动发起转换, 双向可达。

        Args:
            unified: PipelineV2ConfigUnified 实例

        Returns:
            PipelineV2Config (dataclass)
        """
        return unified.to_pipeline_v2_config()


class _BaseFactorPipeline:
    """因子管道基类，提供通用的 fit/transform/fit_transform 接口"""

    def __init__(self):
        self.is_fitted = False
        self._intermediate_data: Dict[str, pd.DataFrame] = {}

    def fit(self, X: pd.DataFrame, **kwargs) -> '_BaseFactorPipeline':
        raise NotImplementedError

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not self.is_fitted:
            raise ValueError("Pipeline未拟合")
        return X

    def fit_transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        return self.fit(X, **kwargs).transform(X, **kwargs)

    def get_intermediate_data(self) -> Dict[str, pd.DataFrame]:
        """
        获取 fit 阶段的中间数据，便于调试和审计。

        Returns:
            Dict[str, pd.DataFrame]: 步骤名到中间数据的映射
        """
        return self._intermediate_data.copy()


class StaticFactorPipeline(_BaseFactorPipeline):
    """
    静态因子处理管道

    适用条件：ar1_median > 0.80 且 rank_autocorr > 0.70
    典型代表：市净率（PB）、市盈率（PE）、股息率

    处理流程：
        缺失插补 → 自适应非线性变换 → (可选)GARCH白化 → 中性化 → 线性Z-Score

    为何这样处理：
        静态因子的价值在截面排序，非线性变换可有效驯服厚尾和偏态。
        高自相关性意味着GARCH预白化可能有必要。
    """

    def __init__(self,
                 neutralizer_params: Optional[Dict] = None,
                 enable_garch: bool = False,
                 garch_params: Optional[Dict] = None):
        super().__init__()
        self.steps = [
            ('imputer', ImputerAdapter(strategy='auto')),
            ('outlier', ProcessingAdapter(process_type='outlier', method='auto')),
            ('transform', ProcessingAdapter(process_type='transformation', method='auto')),
        ]

        # 可选：GARCH白化（默认关闭）
        if enable_garch:
            garch_kwargs = garch_params or {}
            self.steps.append(('garch_whiten', GarchWhiteningAdapter(**garch_kwargs)))

        self.steps.extend([
            ('neutralize', NeutralizerAdapter(**(neutralizer_params or {}))),
            ('standardize', ProcessingAdapter(process_type='standardization', method='auto')),
        ])

    def fit(self, X: pd.DataFrame, **kwargs) -> 'StaticFactorPipeline':
        self._intermediate_data = {}
        for name, step in self.steps:
            logger.info(f"[StaticPipeline] Fitting {name}...")
            step.fit(X, **kwargs)
            X = step.transform(X, **kwargs)
            self._intermediate_data[name] = X.copy()
        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted
        for name, step in self.steps:
            logger.info(f"[StaticPipeline] Transforming {name}...")
            X = step.transform(X, **kwargs)
        return X


class DynamicFactorPipeline(_BaseFactorPipeline):
    """
    动态因子处理管道

    适用条件：ar1_median < 0.40
    典型代表：短期反转、换手率变化、波动率变化

    处理流程（符合设计要求）：
        缺失插补 → 原始值双重中性化 → AR建模 → AR残差中性化 → 线性Z-Score

    为何这样处理：
        动态因子的价值在时序变化，禁止非线性变换以保护时序信号。
        中性化必须在原始值阶段进行以剥离内生性暴露（第一重中性化）。
        AR建模后再进行第二重中性化以剥离残差中的行业/市值暴露。
        绝对禁止GARCH白化，因为已接近白噪声的序列再做波动率标准化会引入新噪声。
    """

    def __init__(self,
                 decorrelation_strength: float = 1.0,
                 max_ar_order: int = 5,
                 ar_criterion: str = 'aic',
                 neutralizer_params: Optional[Dict] = None):
        super().__init__()
        self.decorrelation_strength = decorrelation_strength
        self.max_ar_order = max_ar_order
        self.ar_criterion = ar_criterion
        self.neutralizer_params = neutralizer_params or {}

        # 提取行业和市值数据用于解耦器
        self.industry_data = self.neutralizer_params.get('industry_data', None)
        self.market_cap_data = self.neutralizer_params.get('market_cap_data', None)

        # 核心组件：插补器 + 解耦器 + 标准化器（延迟初始化）
        self._imputer: Optional[ImputerAdapter] = None
        self._decoupler: Optional[CompositeDecoupler] = None
        self._standardizer: Optional[ProcessingAdapter] = None

    def fit(self, X: pd.DataFrame, **kwargs) -> 'DynamicFactorPipeline':
        logger.info("[DynamicPipeline] Fitting (三重中性化流程)...")
        self._intermediate_data = {}

        # Step 1: 插补
        logger.info("[DynamicPipeline] Step 1: 缺失值插补")
        self._imputer = ImputerAdapter(strategy='auto')
        self._imputer.fit(X, **kwargs)
        X_imputed = self._imputer.transform(X, **kwargs)
        self._intermediate_data['imputation'] = X_imputed.copy()
        
        # Step 2: 初始化并拟合组合解耦器（三重中性化核心）
        logger.info("[DynamicPipeline] Step 2: 拟合三重中性化解耦器")
        self._decoupler = CompositeDecoupler(
            industry_data=self.industry_data,
            market_cap_data=self.market_cap_data,
            max_ar_order=self.max_ar_order,
            ar_criterion=self.ar_criterion,
            decorrelation_strength=self.decorrelation_strength
        )
        self._decoupler.fit(X_imputed, **kwargs)
        
        # Step 3: 应用解耦得到残差，用于拟合标准化器
        logger.info("[DynamicPipeline] Step 3: 拟合标准化器")
        X_decoupled = self._decoupler.transform(X_imputed, **kwargs)
        self._intermediate_data['decoupling'] = X_decoupled.copy()
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score')
        self._standardizer.fit(X_decoupled, **kwargs)
        
        self.is_fitted = True
        logger.info("[DynamicPipeline] Fit complete")
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted

        logger.info("[DynamicPipeline] Transforming (三重中性化流程)...")

        # Step 1: 插补
        logger.info("[DynamicPipeline] Step 1: 插补")
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 三重中性化解耦（原始值中性化 → AR建模 → AR残差中性化）
        logger.info("[DynamicPipeline] Step 2: 三重中性化解耦")
        X = self._decoupler.transform(X, **kwargs)

        # Step 3: 标准化
        logger.info("[DynamicPipeline] Step 3: 标准化")
        X = self._standardizer.transform(X, **kwargs)

        logger.info("[DynamicPipeline] Transform complete")
        return X
    
    def get_decoupling_summary(self) -> Dict[str, Any]:
        """获取解耦流程摘要信息"""
        if self._decoupler is None:
            return {}
        return self._decoupler.get_summary()


class MixedFactorPipeline(_BaseFactorPipeline):
    """
    混合因子处理管道

    适用条件：0.40 <= ar1_median <= 0.80
    典型代表：1个月动量、3个月动量

    处理流程：
        缺失插补 → 温和去极值(3σ缩尾) → 条件性非线性变换 → 原始值中性化 → 线性Z-Score

    为何这样处理：
        这类因子介于两者之间，最保守的策略是降级处理。
        只做温和缩尾和中性化，条件性做非线性变换。
        宁可保留一些原始噪声，也不冒险破坏其信号结构。
    """

    def __init__(self,
                 conditional_transform: bool = True,
                 skew_threshold: float = 2.0,
                 kurt_threshold: float = 5.0,
                 mixed_winsor_sigma: float = 3.0,
                 neutralizer_params: Optional[Dict] = None):
        super().__init__()
        self.conditional_transform = conditional_transform
        self.skew_threshold = skew_threshold
        self.kurt_threshold = kurt_threshold
        self.mixed_winsor_sigma = mixed_winsor_sigma
        self.neutralizer_params = neutralizer_params or {}
        self._needs_transform = False  # 是否需要进行非线性变换
        self._transformer = None  # 显式初始化，避免状态不一致

    def fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline':
        self._intermediate_data = {}

        # Step 1: 插补
        logger.info("[MixedPipeline] Fitting imputer...")
        self._imputer = ImputerAdapter(strategy='auto')
        self._imputer.fit(X, **kwargs)
        X = self._imputer.transform(X, **kwargs)
        self._intermediate_data['imputation'] = X.copy()

        # Step 2: 温和去极值（3σ缩尾）
        logger.info("[MixedPipeline] Applying gentle winsorization...")
        self._winsorize_params = self._compute_winsorize_params(X)
        X_winsor = self._apply_winsorize(X)
        self._intermediate_data['outlier'] = X_winsor.copy()

        # Step 3: 诊断是否需要非线性变换
        if self.conditional_transform:
            self._needs_transform = self._diagnose_transform_need(X)
            if self._needs_transform:
                logger.info("[MixedPipeline] Distribution extreme, will apply gentle transform")
                self._transformer = ProcessingAdapter(process_type='transformation', method='yeo_johnson')
                self._transformer.fit(X, **kwargs)
            else:
                logger.info("[MixedPipeline] Distribution normal, skipping transform")
        else:
            self._needs_transform = False

        # Step 4: 中性化
        logger.info("[MixedPipeline] Fitting neutralizer...")
        self._neutralizer = NeutralizerAdapter(**self.neutralizer_params)
        self._neutralizer.fit(X, **kwargs)

        # Step 5: 标准化
        logger.info("[MixedPipeline] Fitting standardizer...")
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score')
        X_neutral = self._neutralizer.transform(X, **kwargs)
        self._standardizer.fit(X_neutral, **kwargs)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted

        # Step 1: 插补
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 温和缩尾
        X = self._apply_winsorize(X)

        # Step 3: 条件性变换
        if self._needs_transform:
            X = self._transformer.transform(X, **kwargs)

        # Step 4: 中性化
        X = self._neutralizer.transform(X, **kwargs)

        # Step 5: 标准化
        X = self._standardizer.transform(X, **kwargs)

        return X

    def _compute_winsorize_params(self, X: pd.DataFrame) -> Dict:
        """计算温和缩尾参数"""
        means = X.mean()
        stds = X.std()
        return {
            'lower': means - self.mixed_winsor_sigma * stds,
            'upper': means + self.mixed_winsor_sigma * stds,
        }

    def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
        """应用3σ缩尾"""
        return X.clip(lower=self._winsorize_params['lower'],
                      upper=self._winsorize_params['upper'],
                      axis=1)

    def _diagnose_transform_need(self, X: pd.DataFrame) -> bool:
        """诊断是否需要进行非线性变换"""
        skew = X.skew().median()
        kurt = X.kurtosis().median()
        return abs(skew) > self.skew_threshold or kurt > self.kurt_threshold


class FactorProcessingPipelineV2:
    """
    增强版因子处理流水线 v2.0

    集成指纹分类层，实现"先诊断分类，再分流处理"。

    Usage:
        config = PipelineV2Config()
        pipeline = FactorProcessingPipelineV2(config)

        # 拟合
        pipeline.fit(factor_dict, industry_data=industry_series)

        # 变换
        results = pipeline.transform(factor_dict)

        # 查看分类结果
        print(pipeline.get_classification_summary())
    """

    def __init__(self, config: Optional[PipelineV2Config] = None, strict_mode: bool = False):
        self.config = config or PipelineV2Config()
        self.strict_mode = strict_mode

        # 前置智能层
        self.fingerprinter = FactorFingerprinter(self.config.fingerprint)
        self.classifier = AdaptiveFactorClassifier(self.config.classification)
        self.semantic_fusion = SemanticStatisticalFusion()

        # 三条处理管道
        self.static_pipeline: Optional[StaticFactorPipeline] = None
        self.dynamic_pipeline: Optional[DynamicFactorPipeline] = None
        self.mixed_pipeline: Optional[MixedFactorPipeline] = None

        # 监测器
        self.monitor = FactorFingerprintMonitor(self.config.monitor)

        # 状态追踪
        self.factor_classifications: Dict[str, ClassificationResult] = {}
        self.factor_pipelines: Dict[str, Any] = {}
        self.is_fitted = False

        # v2.5.0: post_transform_hooks (Layer 2 正交化等, 半侵入式)
        # O2.8.4: enabled=False 时 hooks 为空列表 (零循环开销)
        self.post_transform_hooks: List[Any] = []
        ortho_config = getattr(self.config, 'orthogonalization', None)
        if ortho_config is not None and getattr(ortho_config, 'enabled', False):
            from factor_pipeline.adapters import OrthogonalizerAdapter
            self.post_transform_hooks.append(OrthogonalizerAdapter(ortho_config))

        # v3.0.0 T3.4: CUSUM 在线漂移监测器 (事后诊断, 不侵入 fit/transform)
        # 两个 CUSUM 独立监测: 'mean' (横截面均值) + 'std' (横截面标准差)
        # 序贯检验无需 BH-FDR, h=5.5σ 补偿误报率叠加
        self.cusum_monitors: Dict[str, Any] = {}
        self.drift_alerts: Dict[str, Dict] = {}
        if getattr(self.config, 'enable_cusum_drift_monitor', False):
            try:
                from backtest.cusum_drift_monitor import CUSUMDriftMonitor
                # baseline 初始化为 0/1 (fit 时会重新估)
                self.cusum_monitors['mean'] = CUSUMDriftMonitor(
                    baseline_mean=0.0, baseline_std=1.0,
                    k=self.config.cusum_k, h=self.config.cusum_h,
                    two_sided=True,
                )
                self.cusum_monitors['std'] = CUSUMDriftMonitor(
                    baseline_mean=1.0, baseline_std=0.5,
                    k=self.config.cusum_k, h=self.config.cusum_h,
                    two_sided=True,
                )
                logger.info(
                    f"CUSUM 监测器已启用: k={self.config.cusum_k}, "
                    f"h={self.config.cusum_h}"
                )
            except ImportError:
                logger.warning("CUSUM 监测器启用失败: cusum_drift_monitor 模块不可用")

        logger.info("FactorProcessingPipelineV2 initialized")

    def fit(self,
            factor_data: Dict[str, pd.DataFrame],
            industry_data: Optional[pd.Series] = None,
            descriptions: Optional[Dict[str, str]] = None,
            **kwargs) -> 'FactorProcessingPipelineV2':
        """
        拟合整个流水线

        Parameters
        ----------
        factor_data : Dict[str, pd.DataFrame]
            因子名字到数据的映射
        industry_data : pd.Series, optional
            行业数据，用于中性化
        descriptions : Dict[str, str], optional
            因子名字到构造描述的映射（用于语义-统计融合）
        """
        logger.info(f"=== FactorProcessingPipelineV2.fit() ===")
        logger.info(f"Factors: {list(factor_data.keys())}")

        # 输入验证：检查空数据
        if not factor_data:
            raise ValueError("因子数据字典不能为空")

        # 检查所有因子数据是否为空
        empty_factors = [name for name, df in factor_data.items()
                        if df is None or (isinstance(df, pd.DataFrame) and df.empty)]
        if empty_factors:
            logger.warning(f"以下因子数据为空: {empty_factors}")

        # Step 1: 为每个因子提取指纹（带异常处理）
        logger.info("Step 1: Extracting fingerprints...")
        try:
            fingerprints = self.fingerprinter.batch_extract(factor_data)
        except Exception as e:
            logger.error(f"指纹提取失败: {e}")
            raise RuntimeError(f"指纹提取失败，请检查数据格式: {e}") from e

        # Step 2: 分类（支持语义-统计融合）
        logger.info("Step 2: Classifying factors...")
        if descriptions:
            # 使用语义-统计融合
            logger.info("Using semantic-statistical fusion...")
            data_months = kwargs.get('data_months', {})
            classifications = {}
            for name in factor_data:
                desc = descriptions.get(name, "")
                fp = fingerprints.get(name, FactorFingerprint())
                months = data_months.get(name, 0) if isinstance(data_months, dict) else 0
                
                if desc:
                    result = self.semantic_fusion.classify(desc, fp, months)
                else:
                    result = self.classifier.classify(fp)
                classifications[name] = result
                
                if hasattr(result, 'conflict_reason') and result.conflict_reason:
                    logger.warning(
                        f"Factor {name}: semantic-statistical conflict - "
                        f"{result.conflict_reason}"
                    )
        else:
            # 纯统计分类
            classifications = self.classifier.batch_classify(fingerprints)

        # Step 3+4: 为每个因子创建独立的管道实例并拟合
        # P4'.3 修复: 原"共享管道+concat"方案在多因子场景下存在两个致命问题:
        #   (a) 不同因子列名相同 → concat 产生重复列 → pandas 3.0 stack_v3 崩溃
        #   (b) 加前缀避免重复 → industry_data 的 stock 名无法匹配 → KeyError
        # 正确方案: 每个因子创建独立 pipeline 实例, 单因子 fit/transform,
        #   列名天然唯一, industry 匹配正常, 软路由通过拟合次类型管道支持
        logger.info("Step 3+4: Creating and fitting per-factor pipelines...")
        neutralizer_params = {'industry_data': industry_data} if industry_data is not None else {}

        for name, classification in classifications.items():
            self.factor_classifications[name] = classification

            factor_pipes = {}
            primary_type = classification.primary_type.value.lower()

            # 创建并拟合主类型管道
            factor_pipes[primary_type] = self._create_pipeline(primary_type, neutralizer_params)
            logger.info(f"Fitting {name} → {primary_type} pipeline")
            factor_pipes[primary_type].fit(factor_data[name], **kwargs)

            # 软路由: 创建并拟合次类型管道 (权重 > 0.01 时)
            if (not classification.is_hard and
                    classification.secondary_type is not None and
                    classification.secondary_prob is not None and
                    classification.secondary_prob > 0.01):
                secondary_type = classification.secondary_type.value.lower()
                if secondary_type != primary_type:
                    factor_pipes[secondary_type] = self._create_pipeline(
                        secondary_type, neutralizer_params)
                    logger.info(f"Fitting {name} → {secondary_type} pipeline (soft routing)")
                    factor_pipes[secondary_type].fit(factor_data[name], **kwargs)

            self.factor_pipelines[name] = factor_pipes

        # Backward compat: 保留共享管道属性引用 (测试中可能被 mock)
        if self.factor_pipelines:
            first_pipes = next(iter(self.factor_pipelines.values()))
            self.static_pipeline = first_pipes.get('static', self.static_pipeline)
            self.dynamic_pipeline = first_pipes.get('dynamic', self.dynamic_pipeline)
            self.mixed_pipeline = first_pipes.get('mixed', self.mixed_pipeline)

        # Step 5: 记录到监测器
        logger.info("Step 5: Recording to monitor...")
        for name, fp in fingerprints.items():
            self.monitor.add_fingerprint(name, fp)

        self.is_fitted = True
        logger.info("=== Fit complete ===")
        return self

    def transform(self,
                  factor_data: Dict[str, pd.DataFrame],
                  **kwargs) -> Dict[str, pd.DataFrame]:
        """
        应用流水线（P0-1 修复：使用概率加权软路由）

        路由规则：
        - 高置信度 (is_hard=True, primary_prob > 0.9): 单管道硬路由
        - 中等置信度: primary_type + secondary_type 概率加权混合
        - 边界因子: 两个管道按概率加权混合输出

        Parameters
        ----------
        factor_data : Dict[str, pd.DataFrame]
            因子名字到数据的映射

        Returns
        -------
        Dict[str, pd.DataFrame]
            处理后的因子数据
        """
        if not self.is_fitted:
            raise ValueError("Pipeline未拟合，请先调用 fit()")

        results = {}

        for name, data in factor_data.items():
            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                logger.warning(f"因子 {name} 数据为空，跳过")
                continue

            classification = self.factor_classifications.get(name)
            if classification is None:
                logger.warning(f"因子 {name} 未分类，跳过")
                if self.strict_mode:
                    raise ValueError(f"因子 {name} 未在 fit 阶段分类，请在 strict_mode=False 时使用或重新拟合")
                continue

            # P0-1: 使用概率加权路由
            # v3.0.0 T1 (E2): enable_multi_dim_routing 开关控制路由路径
            #   True: 多维指纹驱动 (含 T1 tail/regime 修正)
            #   False (默认): 仅 ar1 驱动 (向后兼容)
            if self.config.enable_multi_dim_routing:
                # 从 monitor 获取指纹 (fit 阶段已存入)
                fp = None
                if self.monitor is not None:
                    fp_history = self.monitor.fingerprint_history.get(name, [])
                    fp = fp_history[-1] if fp_history else None
                if fp is None:
                    fp = FactorFingerprint()  # 全 NaN 兜底
                weights = _get_multi_dim_pipeline_weights(
                    fp, classification,
                    hard_routing_prob=self.config.hard_routing_prob,
                )
            else:
                weights = _get_pipeline_weights(
                    classification, hard_routing_prob=self.config.hard_routing_prob
                )

            # P1-5: 检查 monitor 的迁移权重，合并平滑过渡
            if self.monitor is not None and self.monitor.config.enable_smooth_transition:
                current_fp = self.monitor.fingerprint_history.get(name, [None])[-1]
                if current_fp is not None:
                    trans_weights = self.monitor.get_transition_weights(name, current_fp)
                    if len(trans_weights) > 1:
                        # P2-6: KS 显著性检验 — 验证迁移是否真实
                        # Fix 1: 使用 transform 参数 factor_data (当前因子数据) 替代
                        #         未定义的 self.factors, 使 KS 检验路径可达
                        # Fix 1b: 按时间(columns/dates)拆分而非按股票(rows)拆分,
                        #         转置后让 stocks 成为 columns, 逐股票做时间维度 KS
                        if name in factor_data:
                            factor_df = factor_data[name]  # (n_stocks, n_dates)
                            n_dates = factor_df.shape[1]
                            if n_dates >= 10:
                                split_idx = n_dates // 2
                                hist_data = factor_df.iloc[:, :split_idx]
                                recent_data = factor_df.iloc[:, split_idx:]
                                is_sig, p_val, ks_details = _ks_migration_significance(
                                    hist_data.T, recent_data.T,
                                    alpha=self.config.ks_alpha,
                                )
                                if is_sig:
                                    logger.info(
                                        f"Factor {name}: KS 检验显著 (p={p_val:.4f}), 确认迁移"
                                    )
                                    weights = _merge_transition_weights(
                                        weights, trans_weights, alpha=self.config.merge_alpha
                                    )
                                    logger.info(
                                        f"Factor {name} in migration: merged weights={weights}"
                                    )
                                else:
                                    logger.info(
                                        f"Factor {name}: KS 检验不显著 (p={p_val:.4f}), "
                                        f"忽略噪声迁移"
                                    )
                            else:
                                # 数据不足，使用原始迁移权重（保守处理）
                                weights = _merge_transition_weights(
                                    weights, trans_weights, alpha=self.config.merge_alpha
                                )
                        else:
                            # 无原始数据，直接合并
                            weights = _merge_transition_weights(
                                weights, trans_weights, alpha=self.config.merge_alpha
                            )

            # 构建管道字典 — P4'.3: 优先使用 per-factor 管道, 回退共享管道
            factor_pipes = self.factor_pipelines.get(name, {})
            pipelines = {
                'static': factor_pipes.get('static', self.static_pipeline),
                'dynamic': factor_pipes.get('dynamic', self.dynamic_pipeline),
                'mixed': factor_pipes.get('mixed', self.mixed_pipeline),
            }

            # 过滤掉权重为 0 的管道
            active_pipelines = {
                k: v for k, v in pipelines.items()
                if k in weights and weights[k] > 0.001
            }
            active_weights = {
                k: v for k, v in weights.items()
                if k in active_pipelines
            }

            if not active_pipelines:
                logger.warning(f"因子 {name} 无有效管道权重，跳过")
                continue

            if len(active_pipelines) == 1:
                pipe_name = list(active_pipelines.keys())[0]
                logger.info(
                    f"Transforming {name} → {pipe_name} pipeline "
                    f"(hard routing, prob={active_weights[pipe_name]:.3f})"
                )
            else:
                pipe_names = ', '.join(
                    f"{k}({v:.2f})" for k, v in active_weights.items()
                )
                logger.info(
                    f"Transforming {name} → soft routing: {pipe_names}"
                )

            results[name] = _apply_weighted_transform(
                data, active_pipelines, active_weights, **kwargs
            )

        # v2.5.0: post_transform_hooks (Layer 2 正交化等, O2.8.3)
        # 半侵入式: per-factor 循环外, return 之前
        for hook in self.post_transform_hooks:
            if not getattr(hook, 'is_fitted_', False):
                results = hook.fit_transform(results, **kwargs)
            else:
                results = hook.transform(results, **kwargs)

        return results

    def fit_transform(self,
                      factor_data: Dict[str, pd.DataFrame],
                      industry_data: Optional[pd.Series] = None,
                      **kwargs) -> Dict[str, pd.DataFrame]:
        """拟合并变换"""
        return self.fit(factor_data, industry_data=industry_data, **kwargs).transform(factor_data, **kwargs)

    def _create_pipeline(self, pipe_type: str, neutralizer_params: dict):
        """创建指定类型的管道实例 (P4'.3 per-factor 方案).

        Args:
            pipe_type: 'static' | 'dynamic' | 'mixed'
            neutralizer_params: 中性化参数 (含 industry_data)
        """
        if pipe_type == 'static':
            return StaticFactorPipeline(
                neutralizer_params=neutralizer_params,
                enable_garch=self.config.static_enable_garch,
                garch_params={
                    'p': self.config.static_garch_p,
                    'q': self.config.static_garch_q,
                    'vol': self.config.static_garch_vol,
                    'min_obs': self.config.static_garch_min_obs,
                } if self.config.static_enable_garch else None
            )
        elif pipe_type == 'dynamic':
            return DynamicFactorPipeline(
                decorrelation_strength=self.config.dynamic_decorrelation_strength,
                max_ar_order=self.config.dynamic_max_ar_order,
                ar_criterion=self.config.dynamic_ar_criterion,
                neutralizer_params=neutralizer_params
            )
        elif pipe_type == 'mixed':
            return MixedFactorPipeline(
                conditional_transform=self.config.mixed_conditional_transform,
                skew_threshold=self.config.mixed_skew_threshold,
                kurt_threshold=self.config.mixed_kurt_threshold,
                mixed_winsor_sigma=self.config.mixed_winsor_sigma,
                neutralizer_params=neutralizer_params
            )
        else:
            raise ValueError(f"Unknown pipeline type: {pipe_type}")

    def _get_pipeline(self, factor_type: FactorType):
        """根据因子类型获取对应管道"""
        return {
            FactorType.STATIC: self.static_pipeline,
            FactorType.DYNAMIC: self.dynamic_pipeline,
            FactorType.MIXED: self.mixed_pipeline,
        }.get(factor_type)

    def monitor_cusum_drift(
        self,
        factor_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Dict]:
        """v3.0.0 T3.4: CUSUM 事后漂移诊断

        对因子值矩阵的横截面统计量 (均值/标准差) 做 CUSUM 监测.
        事后诊断工具, 不侵入 fit/transform 循环, 不自动重训练.

        监测对象 (非 IC, 因 IC 需 forward returns, 管线内部不计算):
        - 'mean': 横截面均值时序 (检测 level shift)
        - 'std': 横截面标准差时序 (检测 volatility regime change)

        两个 CUSUM 独立监测 (序贯检验无需 BH-FDR), h=5.5σ 补偿误报率叠加.

        Args:
            factor_data: Dict[因子名, DataFrame(T×N)] — 因子值矩阵

        Returns:
            {'mean': {'detected': bool, 'direction': str, ...},
             'std':  {'detected': bool, 'direction': str, ...}}
            enable_cusum_drift_monitor=False 时返回 {}

        Side effect:
            触发时填充 self.drift_alerts['cusum_mean'/'cusum_std']
        """
        if not self.cusum_monitors:
            return {}

        if not factor_data:
            return {}

        # 合并所有因子的横截面统计量 (多因子平均)
        import numpy as _np
        mean_series_list = []
        std_series_list = []
        for fname, df in factor_data.items():
            if df is None or df.empty:
                continue
            # 每期的横截面均值/标准差
            cs_mean = df.mean(axis=1).dropna()
            cs_std = df.std(axis=1).dropna()
            mean_series_list.append(cs_mean)
            std_series_list.append(cs_std)

        if not mean_series_list:
            return {}

        # 多因子平均 (或单因子直接用)
        mean_series = pd.concat(mean_series_list, axis=1).mean(axis=1).dropna()
        std_series = pd.concat(std_series_list, axis=1).mean(axis=1).dropna()

        # 重置监测器 (每次调用是独立诊断)
        for monitor in self.cusum_monitors.values():
            monitor.reset()

        # 估算 baseline (用前 50% 数据或全部)
        n_mean = len(mean_series)
        n_std = len(std_series)
        if n_mean < 10:
            return {'mean': {'detected': False, 'reason': 'insufficient data'},
                    'std': {'detected': False, 'reason': 'insufficient data'}}

        split_mean = max(n_mean // 2, 10)
        split_std = max(n_std // 2, 10)
        baseline_mean_val = float(mean_series.iloc[:split_mean].mean())
        baseline_mean_std = float(mean_series.iloc[:split_mean].std()) or 1e-6
        baseline_std_val = float(std_series.iloc[:split_std].mean())
        baseline_std_std = float(std_series.iloc[:split_std].std()) or 1e-6

        # 更新 baseline
        self.cusum_monitors['mean'].baseline_mean = baseline_mean_val
        self.cusum_monitors['mean'].baseline_std = baseline_mean_std
        self.cusum_monitors['std'].baseline_mean = baseline_std_val
        self.cusum_monitors['std'].baseline_std = baseline_std_std

        # 逐期更新 CUSUM
        results = {}
        for key, series, monitor in [
            ('mean', mean_series, self.cusum_monitors['mean']),
            ('std', std_series, self.cusum_monitors['std']),
        ]:
            last_result = {'detected': False, 'direction': None}
            for x in series:
                last_result = monitor.update(float(x))
            results[key] = last_result

            # 触发时填充 drift_alerts
            if last_result['detected']:
                alert_key = f'cusum_{key}'
                self.drift_alerts[alert_key] = {
                    'monitor': 'cusum',
                    'stat': key,
                    'direction': last_result['direction'],
                    'S_pos': last_result.get('S_pos', 0.0),
                    'S_neg': last_result.get('S_neg', 0.0),
                    'baseline_mean': monitor.baseline_mean,
                    'baseline_std': monitor.baseline_std,
                }
                logger.warning(
                    f"CUSUM 漂移检测 ({key}): direction={last_result['direction']}, "
                    f"baseline_mean={monitor.baseline_mean:.4f}, "
                    f"baseline_std={monitor.baseline_std:.4f}"
                )

        return results

    def get_classification_summary(self) -> pd.DataFrame:
        """获取分类汇总表"""
        return self.classifier.get_classification_summary(self.factor_classifications)

    def get_fingerprint_summary(self) -> pd.DataFrame:
        """获取指纹汇总表"""
        data = []
        for name, fp in self.monitor.fingerprint_history.items():
            if fp:
                latest = fp[-1]
                data.append({
                    'factor_name': name,
                    'ar1_median': latest.ar1_median,
                    'rank_autocorr': latest.rank_autocorr,
                    'sd_score': latest.sd_score,
                    'complexity_need': latest.complexity_need,
                    'snr_estimate': latest.snr_estimate,
                })
        return pd.DataFrame(data)

    def check_migrations(self,
                         factor_data: Dict[str, pd.DataFrame]
                         ) -> Dict[str, List[Any]]:
        """检查所有因子的类型迁移"""
        alerts = {}

        for name, data in factor_data.items():
            fp = self.fingerprinter.extract_fingerprint(data)
            migration_alerts = self.monitor.check_type_migration(name, fp)
            if migration_alerts:
                alerts[name] = migration_alerts

        return alerts

    def get_execution_summary(self) -> str:
        """获取执行摘要"""
        lines = ["=" * 60]
        lines.append("FactorProcessingPipelineV2 执行摘要")
        lines.append("=" * 60)

        # 分类结果
        lines.append("\n[因子分类结果]")
        summary = self.get_classification_summary()
        if not summary.empty:
            for _, row in summary.iterrows():
                lines.append(f"  {row['factor_name']}: {row['primary_type']} "
                           f"(prob={row['primary_prob']:.2f}, confidence={row['confidence']:.2f})")

        # 指纹摘要
        lines.append("\n[因子指纹摘要]")
        fp_summary = self.get_fingerprint_summary()
        if not fp_summary.empty:
            for _, row in fp_summary.iterrows():
                lines.append(f"  {row['factor_name']}: AR(1)={row['ar1_median']:.4f}, "
                           f"SD_Score={row['sd_score']:.4f}, SNR={row['snr_estimate']:.4f}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
