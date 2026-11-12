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
    infer_sampling_frequency,
)
# 引入因子解耦模块
from factor_pipeline.modules.factor_decoupler import (
    CompositeDecoupler,
    DecouplerConfig
)

logger = logging.getLogger(__name__)


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
    # 变换配置 (Static / Mixed 共用一套, PL-02)
    static_transformation_method: str = 'rank'
    static_target_distribution: str = 'normal'
    mixed_transformation_method: str = 'rank'
    mixed_target_distribution: str = 'normal'
    # 静态因子是否启用GARCH白化（默认关闭）
    static_enable_garch: bool = False
    # GARCH白化参数
    static_garch_p: int = 1
    static_garch_q: int = 1
    static_garch_vol: str = 'Garch'
    static_garch_min_obs: int = 50

    # v2.6.0 E2 (P3-10'): migration_threshold 字段位置修正
    # 修正前: optimizer.py:155-158 错误设置到 config.monitor.migration_threshold
    #         (MonitorConfig 无此字段, hasattr 静默跳过, 参数被丢弃)
    # 修正后: 字段位于 config 本身, 默认值与 PipelineV2ConfigUnified.migration_threshold 对齐
    migration_threshold: float = 0.10

    # v2.5.0 正交化配置 (Layer 2, ADR-020) — Optional[Any] 避免循环导入
    # 接收 OrthogonalizationConfig (Pydantic) 整对象, enabled=False 时 None
    orthogonalization: Optional[Any] = None

    # v3.4.0 ADR-042: 统一管道模式 ('unified' | 'dynamic_ab')
    pipeline_mode: str = 'unified'
    # 指纹诊断标签开关 (只读, 不参与路由; 指纹提取本身不受此开关影响)
    enable_fingerprint_diagnostics: bool = True
    # A/B 实验标识 (写入规格日志; 非 A/B 为 None)
    ab_experiment_id: Optional[str] = None

    # v3.4.0 ADR-042: 结构突变监控 (opt-in, 只告警)
    enable_break_monitor: bool = False
    break_monitor_window: int = 250
    break_monitor_stride: int = 20
    break_monitor_alpha: float = 0.05
    break_monitor_n_bootstrap: int = 400

    # v3.0.0 T3.4: CUSUM 在线漂移监测开关 (默认 False, 向后兼容)
    # True: 启用 CUSUM 监测因子值矩阵的横截面统计量 (均值/标准差)
    # 两个 CUSUM 独立监测 (序贯检验, 无需 BH-FDR), h=5.5σ 补偿误报率叠加
    enable_cusum_drift_monitor: bool = False
    cusum_k: float = 0.5       # slack (0.5σ, 检测半漂移, T3.3 校准验证)
    cusum_h: float = 5.5       # trigger (5.5σ, 两个 CUSUM 叠加补偿)

    # ABLATION E1: 模块级 enabled 开关 (默认 None = 全启用, 向后兼容)
    # 格式: {'imputer': False, 'winsorizer': False, 'scaler': False,
    #        'neutralizer': False, 'decoupler': False}
    # decoupler 仅作用于 Dynamic 管道 (AR 解耦), 其余管道忽略 (v3.4.3 O2)
    # E2 AblationRunner 通过此字段控制 L1 组件消融
    module_enabled: Optional[Dict[str, bool]] = None

    # v3.1.0 E1 (§2): 隐藏效应诊断 (默认关闭, opt-in, ADR-030)
    # True: FactorProcessingPipelineV2.diagnose_hidden_effects 委托到 decoupler
    # False: 管线行为与 v3.0.0 完全一致 (零回归)
    enable_hidden_effect_diagnosis: bool = False

    # v3.1.0 E2 (§3): P-hacking 防御 (默认关闭, opt-in, ADR-031)
    # L2 事中记录: SpecificationLogger (append-only JSONL)
    enable_specification_logger: bool = False
    spec_log_dir: str = "logs/specifications/"
    # L1 test set 一次性原则: 禁止对同一 test set 多次评估
    enforce_test_set_once: bool = False

    # v3.1.0 E3 (§1): 内生性检验 (四阶段 S1-S4)
    # 独立新模块 modules/endogeneity_check/, 事后诊断不侵入 fit/transform
    # v1.3 术语: Oster δ (非 ITCV), R_max=min(1, 1.3×R̃), IFE lambda_i'*F_t, Lewbel (Z-Z̄)×ê²
    enable_endogeneity_check: bool = False             # 四阶段检验总开关
    endogeneity_methods: List[str] = field(default_factory=lambda: ['oster_delta', 'aet'])
    enable_ife_endogeneity_check: bool = False         # IFE 高级方法, 按需 opt-in
    enable_lewbel_endogeneity_check: bool = False      # Lewbel 高级方法, 按需 opt-in
    enable_missingness_diagnosis: bool = False         # S1 缺失机制诊断 (插补前)
    enable_s3_neutralization_check: bool = False       # S3 中性化后检验 (高 stakes 场景)
    endogeneity_ife_max_dim: int = 5
    endogeneity_alert_threshold: float = 0.1
    oster_r_max_multiplier: float = 1.3                # v1.3: 1.3 (非 2.75)
    oster_threat_threshold: float = 0.1

    # v3.1.0 E4 (§4): 格兰杰检验 (Toda-Yamamoto 1995)
    # 独立新模块 backtest/granger_attribution/, 事后诊断
    enable_granger_attribution: bool = False
    granger_max_lag: int = 12
    granger_use_toda_yamamoto: bool = True     # 默认 Toda-Yamamoto
    granger_use_bootstrap: bool = False

    # RESEARCH_NOTES E4: 指纹性能日志 (FingerprintPerformanceLogger)
    # DuckDB 持久化 21 维指纹 + 表现 + 管道权重, 供 E5 AttributionAnalyzer 使用
    enable_fingerprint_performance_log: bool = False
    fp_log_db_path: str = 'factor_db.duckdb'
    fp_log_table_name: str = 'fingerprint_performance_log'

    # v3.1.0 E5 (§5): 三层决策正则化 (硬依赖 E3, opt-in)
    # L1 预处理层: 调整 DualNeutralizer 中性化强度
    # L2 检验层:   调整 factor_significance 显著性阈值 α
    # L3 组合层:   调整 optimizer 因子权重惩罚
    enable_endogeneity_regularization: bool = False       # 硬依赖 E3, 默认关闭
    regularizer_gamma: float = 0.5                        # L2 α 调整系数 γ (spec: endogeneity_reg_gamma)
    regularizer_rho: float = 0.3                          # L3 权重惩罚系数 ρ (spec: endogeneity_reg_strength)
    endogeneity_skip_stage2_threshold: float = 0.3        # L1 跳过 Stage 2 阈值
    endogeneity_extra_check_threshold: float = 0.7        # L1 额外 β' 检查阈值
    lambda_endogeneity: float = 0.0                       # optimizer 内生性惩罚 (默认 0, 向后兼容)

    # v3.1.0 E6 (§5.10): 估计层方法 (opt-in, 与 E5 互补)
    # 四种内生性缓解估计器 + 方法选择器, 全部默认关闭
    enable_endogeneity_estimators: bool = False           # 估计层总开关
    estimator_method: str = 'auto'                        # 'auto'/'profile_gmm'/'ivx'/'dols'/'pfgmm'
    enable_profile_gmm: bool = False                      # Profile GMM (Hong-Su-Jiang 2022)
    profile_gmm_nuclear_lambda: float = 0.1               # 核范数正则化强度 λ
    enable_ivx: bool = False                              # IVX (Kostakis 2015)
    ivx_alpha: Optional[float] = None                     # 指数衰减速率 (None=自适应)
    enable_regularized_dols: bool = False                 # 正则化 DOLS (Stock-Watson 1993)
    dols_lag_order: int = 3
    dols_lambda_l1: float = 0.0
    dols_lambda_l2: float = 0.0
    enable_pfgmm: bool = False                            # PFGMM (Ghosh-Thoresen 2019, 仅理论)
    pfgmm_penalty: str = 'scad'
    pfgmm_lambda: float = 0.1
    enable_method_selector: bool = False                  # 自动方法选择 (基于 E3 诊断)

    # RESEARCH_NOTES E7 (§2B): 状态归因 (opt-in, 默认关闭)
    enable_state_attribution: bool = False                 # 状态归因总开关
    state_data_source: str = 'akshare'                     # 数据源 ('akshare'/'synthetic')
    state_min_observations: int = 252                      # 最小观测数
    regime_n_states: int = 2                               # Markov 体制数 (默认 2: bull/bear)

    # RESEARCH_NOTES E10 (§4): 统计→决策桥接 (opt-in, 默认关闭)
    enable_decision_bridge: bool = False                   # 决策桥接总开关
    bridge_learning_rate: float = 0.1                      # Q2 soft-update 学习率
    bridge_decision_freq: str = 'M'                        # 决策频率 ('D'/'W'/'M'/'Q')

    def __post_init__(self):
        """v3.4.0 ADR-042: pipeline_mode 合法性校验."""
        if self.pipeline_mode not in ('unified', 'dynamic_ab'):
            raise ValueError(
                f"pipeline_mode 必须为 'unified' 或 'dynamic_ab', "
                f"实际: {self.pipeline_mode!r}"
            )

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


# =============================================================================
# v3.4.0 ADR-042: 统一路由记录数据类
# =============================================================================

@dataclass(frozen=True)
class FingerprintMeta:
    """指纹采集元数据 — 不进入 21 维数值指纹契约."""
    sampling_frequency: str = 'unknown'
    n_obs: int = 0
    n_columns: int = 0
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass(frozen=True)
class FactorRoutingRecord:
    """单因子的执行事实 + 诊断标签 (唯一可信来源)."""
    factor_name: str
    pipeline_mode: str
    execution_pipe_type: str
    diagnostic_type: str
    diagnostic_prob: float
    diagnostic_confidence: float
    ar1_median: float
    fingerprint_meta: FingerprintMeta


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

    P1 修复: 中性化顺序从 transform→neutralize 改为 neutralize→transform.
    理由: 先剥离行业暴露 (原始值), 再对纯净 alpha 做 transform.
    旧顺序下 Box-Cox 可能放大行业信号, neutralize 虽然数学上能移除但
    transform 的扭曲已经锁定到值空间中, 影响下游多因子组合的信号结构.

    PL-02: 变换默认 rank (逐日截面 PIT), 方法由 transformation_params 固定.
    """

    def __init__(self,
                 neutralizer_params: Optional[Dict] = None,
                 transformation_params: Optional[Dict] = None,
                 enable_garch: bool = False,
                 garch_params: Optional[Dict] = None,
                 module_enabled: Optional[Dict[str, bool]] = None):
        super().__init__()
        me = module_enabled or {}
        tp = transformation_params or {}
        transform_method = tp.get('method', 'rank')
        transform_target = tp.get('target_distribution', 'normal')
        transform_extra = {
            k: v for k, v in tp.items()
            if k not in ('method', 'target_distribution')
        }
        self.steps = [
            ('imputer', ImputerAdapter(strategy='ffill_ts', enabled=me.get('imputer', True))),
            ('outlier', ProcessingAdapter(process_type='outlier', method='percentile',
                                          percentile_lower=1.0, percentile_upper=99.0,
                                          enabled=me.get('winsorizer', True))),
            # P1: neutralize before transform — 先剥离行业暴露再变换
            ('neutralize', NeutralizerAdapter(enabled=me.get('neutralizer', True),
                                              **(neutralizer_params or {}))),
            ('transform', ProcessingAdapter(
                process_type='transformation',
                method=transform_method,
                target_distribution=transform_target,
                **transform_extra,
            )),
        ]

        # 可选：GARCH白化（默认关闭）
        if enable_garch:
            garch_kwargs = garch_params or {}
            self.steps.append(('garch_whiten', GarchWhiteningAdapter(**garch_kwargs)))

        self.steps.append(
            ('standardize', ProcessingAdapter(process_type='standardization', method='auto',
                                              enabled=me.get('scaler', True))),
        )

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
                 neutralizer_params: Optional[Dict] = None,
                 module_enabled: Optional[Dict[str, bool]] = None):
        super().__init__()
        self.decorrelation_strength = decorrelation_strength
        self.max_ar_order = max_ar_order
        self.ar_criterion = ar_criterion
        self.neutralizer_params = neutralizer_params or {}

        # ABLATION E1: 模块级 enabled 开关 (默认全 True, 向后兼容)
        me = module_enabled or {}
        self._imputer_enabled = me.get('imputer', True)
        self._neutralizer_enabled = me.get('neutralizer', True)
        # v3.4.3 O2: AR 解耦独立开关, 不再与 neutralizer 绑定
        self._decoupler_enabled = me.get('decoupler', True)
        self._scaler_enabled = me.get('scaler', True)

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
        self._imputer = ImputerAdapter(strategy='ffill_ts', enabled=self._imputer_enabled)
        self._imputer.fit(X, **kwargs)
        X_imputed = self._imputer.transform(X, **kwargs)
        self._intermediate_data['imputation'] = X_imputed.copy()

        # Step 2: 初始化并拟合组合解耦器（三重中性化核心）
        # v3.4.3 O2: 中性化与 AR 解耦使用独立开关; 任一开启即需要解耦器
        if self._neutralizer_enabled or self._decoupler_enabled:
            logger.info(
                "[DynamicPipeline] Step 2: 拟合解耦器 (neutralizer=%s, decoupler=%s)",
                self._neutralizer_enabled, self._decoupler_enabled,
            )
            self._decoupler = CompositeDecoupler(
                industry_data=self.industry_data,
                market_cap_data=self.market_cap_data,
                max_ar_order=self.max_ar_order,
                ar_criterion=self.ar_criterion,
                decorrelation_strength=self.decorrelation_strength,
                enable_neutralization=self._neutralizer_enabled,
                enable_ar=self._decoupler_enabled,
            )
            self._decoupler.fit(X_imputed, **kwargs)
            X_decoupled = self._decoupler.transform(X_imputed, **kwargs)
        else:
            logger.info("[DynamicPipeline] Step 2: neutralizer/decoupler disabled, 跳过解耦 (identity)")
            self._decoupler = None
            X_decoupled = X_imputed
        self._intermediate_data['decoupling'] = X_decoupled.copy()

        # Step 3: 应用解耦得到残差，用于拟合标准化器
        logger.info("[DynamicPipeline] Step 3: 拟合标准化器")
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score',
                                               enabled=self._scaler_enabled)
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
        # v3.4.3 O2: 组件开关已下沉到 CompositeDecoupler, 此处仅判断解耦器是否存在
        if self._decoupler is not None:
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
        缺失插补 → 逐日截面 3σ 缩尾 → 原始值中性化 → 固定 rank 变换 → 线性Z-Score

    为何这样处理：
        这类因子介于两者之间，最保守的策略是降级处理。
        只做逐日截面 3σ 缩尾和中性化，固定做 rank 变换（I-INT：先中性化再 rank）。
        宁可保留一些原始噪声，也不冒险破坏其信号结构。
    """

    def __init__(self,
                 mixed_winsor_sigma: float = 3.0,
                 transformation_params: Optional[Dict] = None,
                 neutralizer_params: Optional[Dict] = None,
                 module_enabled: Optional[Dict[str, bool]] = None):
        super().__init__()
        self.mixed_winsor_sigma = mixed_winsor_sigma
        self._transformation_params = transformation_params or {}
        self.neutralizer_params = neutralizer_params or {}
        self._transformer = None  # 显式初始化，避免状态不一致

        # ABLATION E1: 模块级 enabled 开关 (默认全 True, 向后兼容)
        me = module_enabled or {}
        self._imputer_enabled = me.get('imputer', True)
        self._winsorizer_enabled = me.get('winsorizer', True)
        self._neutralizer_enabled = me.get('neutralizer', True)
        self._scaler_enabled = me.get('scaler', True)

    def fit(self, X: pd.DataFrame, **kwargs) -> 'MixedFactorPipeline':
        self._intermediate_data = {}

        # Step 1: 插补
        logger.info("[MixedPipeline] Fitting imputer...")
        self._imputer = ImputerAdapter(strategy='ffill_ts', enabled=self._imputer_enabled)
        self._imputer.fit(X, **kwargs)
        X = self._imputer.transform(X, **kwargs)
        self._intermediate_data['imputation'] = X.copy()

        # Step 2: 逐日截面 3σ 缩尾 (PL-06: fit no-op, 无跨期参数)
        if self._winsorizer_enabled:
            logger.info("[MixedPipeline] Applying cross-sectional winsorization...")
            self._winsorize_params = None   # 显式标记: 无跨期参数
            X = self._apply_winsorize(X)
        else:
            logger.info("[MixedPipeline] winsorizer disabled, 跳过去极值 (identity)")
            self._winsorize_params = None
        self._intermediate_data['outlier'] = X.copy()

        # Step 3: 中性化 (I-INT: 先剥离暴露)
        logger.info("[MixedPipeline] Fitting neutralizer...")
        self._neutralizer = NeutralizerAdapter(enabled=self._neutralizer_enabled,
                                               **self.neutralizer_params)
        self._neutralizer.fit(X, **kwargs)
        X = self._neutralizer.transform(X, **kwargs)
        self._intermediate_data['neutralize'] = X.copy()

        # Step 4: 变换 (fit 与 transform 使用同一输入)
        logger.info("[MixedPipeline] Fitting transformer...")
        tp = self._transformation_params
        extra = {
            k: v for k, v in tp.items()
            if k not in ('method', 'target_distribution')
        }
        self._transformer = ProcessingAdapter(
            process_type='transformation',
            method=tp.get('method', 'rank'),
            target_distribution=tp.get('target_distribution', 'normal'),
            **extra,
        )
        self._transformer.fit(X, **kwargs)
        X = self._transformer.transform(X, **kwargs)
        self._intermediate_data['transform'] = X.copy()

        # Step 5: 标准化
        logger.info("[MixedPipeline] Fitting standardizer...")
        self._standardizer = ProcessingAdapter(process_type='standardization', method='z_score',
                                               enabled=self._scaler_enabled)
        self._standardizer.fit(X, **kwargs)

        self.is_fitted = True
        return self

    def transform(self, X: pd.DataFrame, **kwargs) -> pd.DataFrame:
        super().transform(X, **kwargs)  # 检查 is_fitted

        # Step 1: 插补
        X = self._imputer.transform(X, **kwargs)

        # Step 2: 温和缩尾
        # ABLATION E1: winsorizer 关闭时跳过 (identity)
        if self._winsorizer_enabled:
            X = self._apply_winsorize(X)

        # Step 3: 中性化
        X = self._neutralizer.transform(X, **kwargs)

        # Step 4: 固定变换
        X = self._transformer.transform(X, **kwargs)

        # Step 5: 标准化
        X = self._standardizer.transform(X, **kwargs)

        return X

    def _apply_winsorize(self, X: pd.DataFrame) -> pd.DataFrame:
        """逐日截面 3σ 缩尾: 边界只由当日行计算, 无跨期参数.

        mu = X.mean(axis=1); sd = X.std(axis=1, ddof=1)
        lower/upper 按 index (日期) 对齐, 因此 clip(axis=0).
        """
        sigma = self.mixed_winsor_sigma
        mu = X.mean(axis=1)
        sd = X.std(axis=1, ddof=1)
        return X.clip(lower=mu - sigma * sd,
                      upper=mu + sigma * sd,
                      axis=0)


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
        # v3.4.0 ADR: 统一路由记录 (执行事实 + 诊断标签)
        self.factor_routing: Dict[str, FactorRoutingRecord] = {}
        # v3.4.0 ADR: 结构突变告警 (只读, monitor_structural_breaks 填充)
        self.break_alerts: Dict[str, Dict] = {}
        self.is_fitted = False

        # P2: 中间数据日志 — 每个因子的每步输出 (transform 后填充)
        self._intermediate_data: Dict[str, Dict[str, pd.DataFrame]] = {}

        # v3.1.0 E1 (§2): 隐藏效应诊断 — 当前激活的解耦器引用 (fit 后填充)
        # 由 diagnose_hidden_effects 委托调用; 未 fit 时为 None.
        # 测试可直接注入已拟合的解耦器以聚焦委托逻辑 (见 E1-T15).
        self.decoupler: Optional[Any] = None
        self._hidden_effect_report: Optional[Dict[str, Any]] = None

        # v3.1.0 E2 (§3): P-hacking 防御 — SpecificationLogger 引用 (懒初始化)
        # 由 log_specification 委托调用; enable_specification_logger=False 时不创建.
        self._spec_logger: Optional[Any] = None

        # v3.1.0 E3 (§1): 内生性检验 — 编排器引用 (懒初始化, 按需创建)
        # 由 check_endogeneity 委托调用; enable_endogeneity_check=False 时不创建.
        self._endogeneity_orchestrator: Optional[Any] = None
        self._endogeneity_report: Optional[Dict[str, Any]] = None

        # v3.1.0 E4 (§4): 格兰杰检验 — 测试器引用 (懒初始化)
        # 由 check_granger_causality 委托调用; enable_granger_attribution=False 时不创建.
        self._granger_report: Optional[Dict[str, Any]] = None

        # RESEARCH_NOTES E4: 指纹性能日志 — Logger 引用 (懒初始化)
        # 由 log_fingerprint_performance 委托调用; enable_fingerprint_performance_log=False 时不创建.
        self._fp_logger: Optional[Any] = None

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
            market_cap_data: Optional[pd.DataFrame] = None,
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
        market_cap_data : pd.DataFrame, optional
            市值数据 (日期×股票), 用于市值中性化
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

        # Step 2: 诊断标签 (受开关控制; 只产标签, 不选管道)
        # v3.4.0 ADR: 指纹提取与 monitor.add_fingerprint 始终执行,
        #   开关只控制分类标签 (否则连带关闭 get_fingerprint_summary/check_migrations)
        logger.info("Step 2: Classifying factors (diagnostics only)...")
        classifications = self._classify_diagnostics(
            fingerprints, descriptions, kwargs)

        # Step 3+4: 执行管道由 pipeline_mode 唯一决定 (不再调用 StatisticalClassifier;
        # 保留 P4'.3 per-factor 方案: 每因子独立 pipeline 实例, 列名唯一)
        logger.info("Step 3+4: Creating and fitting per-factor pipelines...")
        neutralizer_params = self._build_neutralizer_params(
            industry_data, market_cap_data)

        pipe_type = 'static' if self.config.pipeline_mode == 'unified' else 'dynamic'
        logger.info(
            f"  pipeline_mode={self.config.pipeline_mode} → execution pipe '{pipe_type}'"
        )

        for name, df in factor_data.items():
            pipe = self._create_pipeline(
                pipe_type, neutralizer_params, self.config.module_enabled)
            logger.info(f"Fitting {name} → {pipe_type} pipeline")
            pipe.fit(df, **kwargs)
            self.factor_pipelines[name] = {pipe_type: pipe}

            # v3.4.0 ADR: 诊断标签 (开关关闭时为 unknown) + 路由记录
            fp = fingerprints.get(name, FactorFingerprint())
            cls = classifications.get(name, self._unknown_classification())
            self.factor_classifications[name] = cls

            self.factor_routing[name] = FactorRoutingRecord(
                factor_name=name,
                pipeline_mode=self.config.pipeline_mode,
                execution_pipe_type=pipe_type,
                diagnostic_type=cls.primary_type.value,
                diagnostic_prob=cls.primary_prob,
                diagnostic_confidence=cls.confidence,
                ar1_median=fp.ar1_median,
                fingerprint_meta=FingerprintMeta(
                    sampling_frequency=infer_sampling_frequency(df.index),
                    n_obs=int(df.shape[0]),
                    n_columns=int(df.shape[1]),
                    start=self._fmt_ts(df.index.min()) if len(df.index) else None,
                    end=self._fmt_ts(df.index.max()) if len(df.index) else None,
                ),
            )
            self._log_spec(self.factor_routing[name])

        # Backward compat: 保留共享管道属性引用 (测试中可能被 mock)
        if self.factor_pipelines:
            first_pipes = next(iter(self.factor_pipelines.values()))
            self.static_pipeline = first_pipes.get('static')
            self.dynamic_pipeline = first_pipes.get('dynamic')
            self.mixed_pipeline = None

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
        应用流水线（v3.4.0 ADR-042: 统一执行）

        路由规则：
        - 生产路径: 按 fit 阶段写入的 `factor_pipelines[name]` 取管道
          (unified → 'static'; dynamic_ab → 'dynamic'), 每因子单管道
        - 兜底路径 (mock / 旧调用): fit 未写 `factor_pipelines` 时按
          `diagnostic_type` 取扁平属性; 两者皆无 → 跳过 (strict_mode 抛错)

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
            factor_pipes = self.factor_pipelines.get(name)
            if factor_pipes:
                # v3.4.0 ADR: 生产路径 — fit 恒填 factor_pipelines, 键恒为
                # 'static' (unified) 或 'dynamic' (dynamic_ab)
                pipe_type = next(iter(factor_pipes))
                pipe = factor_pipes[pipe_type]
            else:
                # 兜底 (mock/旧调用): 按诊断类型取扁平属性; 仅当 fit 未填
                # factor_pipelines 时可达, 生产路径不会进入
                if classification is None:
                    if self.strict_mode:
                        raise ValueError(f"因子 {name} 未在 fit 阶段分类/拟合，请在 strict_mode=False 时使用或重新拟合")
                    logger.warning(f"因子 {name} 未拟合，跳过")
                    continue
                pipe = self._get_pipeline(classification.primary_type)
                if pipe is None:
                    logger.warning(f"因子 {name} 无可用管线，跳过")
                    continue
            try:
                processed = pipe.transform(data)
            except (ValueError, TypeError, RuntimeError) as e:
                logger.warning(f"因子 {name} 变换失败: {e}")
                continue

            results[name] = processed

            # P2: 收集中间数据 — 从子管线提升到主管线
            if hasattr(pipe, '_intermediate_data') and pipe._intermediate_data:
                self._intermediate_data[name] = {
                    k: v.copy() for k, v in pipe._intermediate_data.items()
                    if isinstance(v, pd.DataFrame)
                }
                logger.debug(f"  中间数据已记录: {name} ({list(self._intermediate_data[name].keys())})")

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

    def get_intermediate_data(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """返回 transform 后每步中间输出的浅拷贝.

        Returns:
            {factor_name: {step_name: DataFrame}}, e.g.
            {'momentum_1m': {'imputation': df, 'outlier': df, 'decoupling': df, ...}}
        """
        return {k: dict(v) for k, v in self._intermediate_data.items()}

    def _create_pipeline(self, pipe_type: str, neutralizer_params: dict,
                         module_enabled: Optional[Dict[str, bool]] = None):
        """创建指定类型的管道实例 (P4'.3 per-factor 方案).

        Args:
            pipe_type: 'static' | 'dynamic' | 'mixed'
            neutralizer_params: 中性化参数 (含 industry_data)
            module_enabled: ABLATION E1 模块级 enabled 开关 (None = 全启用)
        """
        if pipe_type == 'static':
            return StaticFactorPipeline(
                neutralizer_params=neutralizer_params,
                transformation_params={
                    'method': self.config.static_transformation_method,
                    'target_distribution': self.config.static_target_distribution,
                },
                enable_garch=self.config.static_enable_garch,
                garch_params={
                    'p': self.config.static_garch_p,
                    'q': self.config.static_garch_q,
                    'vol': self.config.static_garch_vol,
                    'min_obs': self.config.static_garch_min_obs,
                } if self.config.static_enable_garch else None,
                module_enabled=module_enabled,
            )
        elif pipe_type == 'dynamic':
            return DynamicFactorPipeline(
                decorrelation_strength=self.config.dynamic_decorrelation_strength,
                max_ar_order=self.config.dynamic_max_ar_order,
                ar_criterion=self.config.dynamic_ar_criterion,
                neutralizer_params=neutralizer_params,
                module_enabled=module_enabled,
            )
        elif pipe_type == 'mixed':
            # v3.4.0 ADR: mixed_winsor_sigma 配置字段已删; winsor 阈值由
            # MixedFactorPipeline.__init__ 默认值 3.0 承担
            return MixedFactorPipeline(
                transformation_params={
                    'method': self.config.mixed_transformation_method,
                    'target_distribution': self.config.mixed_target_distribution,
                },
                neutralizer_params=neutralizer_params,
                module_enabled=module_enabled,
            )
        else:
            raise ValueError(f"Unknown pipeline type: {pipe_type}")

    def _get_pipeline(self, factor_type: FactorType):
        """mock/旧调用兜底: 按类型取扁平属性, 再按 pipeline_mode 兜底.

        v3.4.0 ADR: 生产 fit 总会填充 factor_pipelines, 因此生产路径不调用本方法;
        保留是为兼容 test_fix1_self_factors_bug / test_p0_fixes 的 mock 场景
        (直接注入 self.static_pipeline 等扁平属性).
        """
        # 兼容 mock: 优先按类型取扁平属性 (既有测试直接注入三条管道)
        pipe = {
            FactorType.STATIC: self.static_pipeline,
            FactorType.DYNAMIC: self.dynamic_pipeline,
            FactorType.MIXED: self.mixed_pipeline,
        }.get(factor_type)
        if pipe is not None:
            return pipe
        # 模式兜底
        if self.config.pipeline_mode == 'dynamic_ab':
            return self.dynamic_pipeline
        return self.static_pipeline

    # ------------------------------------------------------------------
    # v3.4.0 ADR-042: 统一路由私有方法
    # ------------------------------------------------------------------

    def _classify_diagnostics(
        self,
        fingerprints: Dict[str, FactorFingerprint],
        descriptions: Optional[Dict[str, str]],
        kwargs: dict,
    ) -> Dict[str, ClassificationResult]:
        """只产诊断标签, 不选管道. 逻辑与 v3.3.7 fit Step 2 一致.

        enable_fingerprint_diagnostics=False 时返回 {} (调用方回填 unknown 标签);
        指纹提取与 monitor.add_fingerprint 不受此开关影响 (E1 设计决策).
        """
        if not getattr(self.config, 'enable_fingerprint_diagnostics', True):
            return {}
        if descriptions:
            logger.info("Using semantic-statistical fusion...")
            data_months = kwargs.get('data_months', {})
            out = {}
            for name in fingerprints:
                desc = descriptions.get(name, "")
                fp = fingerprints.get(name, FactorFingerprint())
                months = data_months.get(name, 0) if isinstance(data_months, dict) else 0
                if desc:
                    result = self.semantic_fusion.classify(desc, fp, months)
                else:
                    result = self.classifier.classify(fp)
                out[name] = result
                if hasattr(result, 'conflict_reason') and result.conflict_reason:
                    logger.warning(
                        f"Factor {name}: semantic-statistical conflict - "
                        f"{result.conflict_reason}"
                    )
            return out
        # 纯统计分类
        return self.classifier.batch_classify(fingerprints)

    @staticmethod
    def _build_neutralizer_params(industry_data, market_cap_data) -> dict:
        """构造中性化参数 (P0-5: market_cap 透传 + 自动切换 neutralization_type)."""
        params = {}
        if industry_data is not None:
            params['industry_data'] = industry_data
        if market_cap_data is not None:
            params['market_cap_data'] = market_cap_data
            params['neutralization_type'] = 'industry_marketcap'
        return params

    @staticmethod
    def _unknown_classification() -> ClassificationResult:
        """诊断开关关闭 / 指纹缺失时的占位标签."""
        return ClassificationResult(
            primary_type=FactorType.UNKNOWN, primary_prob=0.0, confidence=0.0)

    @staticmethod
    def _fmt_ts(ts) -> Optional[str]:
        if ts is None or pd.isna(ts):
            return None
        try:
            return pd.Timestamp(ts).isoformat()
        except Exception:
            return None

    def _log_spec(self, record: FactorRoutingRecord) -> Optional[str]:
        """v3.4.0 ADR: 规格日志 — 按执行臂派生 winsor/transformation (E4).

        全函数 try/except 包裹, 失败仅 warning 不影响拟合;
        懒初始化的是管道侧 self._spec_logger (SpecificationLogger.__init__
        本身构造即建目录, 因此"关闭时目录不创建"由"构造从未发生"保证).
        """
        if not getattr(self.config, 'enable_specification_logger', False):
            return None
        try:
            if self._spec_logger is None:
                from backtest.specification_logger import SpecificationLogger
                self._spec_logger = SpecificationLogger(
                    log_dir=self.config.spec_log_dir)
            try:
                from backtest.cache_manager import CODE_VERSION as _CACHE_VERSION
            except Exception:
                _CACHE_VERSION = 'unknown'
            is_static = record.execution_pipe_type == 'static'
            return self._spec_logger.log_run(
                config={
                    'pipeline_mode': record.pipeline_mode,
                    'execution_pipe_type': record.execution_pipe_type,
                    'diagnostic_type': record.diagnostic_type,
                    'diagnostic_prob': record.diagnostic_prob,
                    'ar1_median': record.ar1_median,
                    'sampling_frequency': record.fingerprint_meta.sampling_frequency,
                    'n_obs': record.fingerprint_meta.n_obs,
                    'n_columns': record.fingerprint_meta.n_columns,
                    'winsor': 'percentile(1,99)' if is_static else 'none',
                    'transformation': (
                        f"{self.config.static_transformation_method}"
                        f"->{self.config.static_target_distribution}"
                        if is_static else 'ar_residual->z_score'),
                    'ab_experiment_id': self.config.ab_experiment_id,
                    'cache_version': _CACHE_VERSION,
                },
                result={'n_columns': record.fingerprint_meta.n_columns},
                run_type=('validation' if self.config.ab_experiment_id
                          else 'exploratory'),
                factor_name=record.factor_name,
            )
        except Exception as e:
            logger.warning(f"规格日志写入失败 (不影响拟合): {e}")
            return None

    def monitor_structural_breaks(
        self,
        factor_data: Dict[str, pd.DataFrame],
        *,
        method: str = 'sup_f',
        window: Optional[int] = None,
        stride: Optional[int] = None,
    ) -> Dict[str, Dict]:
        """v3.4.0 ADR: 结构突变监控 (只告警, 不改因子值/不参与路由).

        Args:
            factor_data: Dict[因子名, DataFrame(rows=日期)]
            method: 'sup_f' | 'cusum'
            window/stride: 滚动窗口与步长; None 时取 config.break_monitor_*.
                用 `is not None` 而非 `or` — 显式传 0 时应交给
                compute_ar1_path 抛 ValueError, 不被 falsy 吞掉回退默认.

        Returns:
            {因子名: 告警字典}; enable_break_monitor=False 时返回 {}.
            触发告警的因子写入 self.break_alerts (只读) 并 logger.warning.
        """
        if not getattr(self.config, 'enable_break_monitor', False):
            return {}
        from backtest.structural_break_monitor import (
            BreakMonitorConfig, StructuralBreakMonitor,
        )
        cfg = BreakMonitorConfig(
            method=method,
            window=window if window is not None else self.config.break_monitor_window,
            stride=stride if stride is not None else self.config.break_monitor_stride,
            alpha=self.config.break_monitor_alpha,
            n_bootstrap=self.config.break_monitor_n_bootstrap,
        )
        monitor = StructuralBreakMonitor(cfg)
        out = {}
        for name, df in factor_data.items():
            if df is None or df.empty:
                continue
            path = self.fingerprinter.compute_ar1_path(
                df, cfg.window, cfg.stride)
            res = monitor.detect(path)
            out[name] = res
            if res.get('detected'):
                self.break_alerts[name] = res
                logger.warning(
                    f"结构突变告警: {name} ({res['method']}), "
                    f"p={res['p_value']:.4f}, date={res.get('break_date')}")
        return out

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

    def diagnose_hidden_effects(
        self,
        factor_data: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
        returns: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """v3.1.0 E1 (§2): 事后隐藏效应诊断

        委托到 self.decoupler.diagnose_hidden_effects (CompositeDecoupler /
        ARDecoupler 通过 HiddenEffectDiagnosticMixin 提供). 不侵入 fit/transform,
        与 monitor_cusum_drift 模式一致.

        Args:
            factor_data: 原始因子数据 (T, N)
            controls: 行业/市值控制变量 (T, N, K), 用于增量内生性检验
            returns: 未来收益 (T, N), 用于 IC 衰减对比

        Returns:
            4 键诊断 dict, 或 None (功能关闭 / 无可用解耦器).
            enable_hidden_effect_diagnosis=False 时返回 None.
        """
        if not getattr(self.config, 'enable_hidden_effect_diagnosis', False):
            return None
        decoupler = getattr(self, 'decoupler', None)
        if decoupler is None or not hasattr(decoupler, 'diagnose_hidden_effects'):
            return None
        self._hidden_effect_report = decoupler.diagnose_hidden_effects(
            factor_data, controls, returns
        )
        return self._hidden_effect_report

    def log_specification(
        self,
        config: Dict[str, Any],
        result: Dict[str, Any],
        run_type: str = 'exploratory',
        factor_name: Optional[str] = None,
    ) -> Optional[str]:
        """v3.1.0 E2 (§3 L2): 记录运行规格 (P-hacking 防御)

        委托到 SpecificationLogger.log_run (append-only JSONL).
        enable_specification_logger=False 时返回 None.

        Args:
            config: 运行配置 (滞后阶数、中性化变量、样本期等)
            result: 运行结果 (IC、p_value、显著数等)
            run_type: 'exploratory' / 'validation' / 'final'
            factor_name: 因子名 (可选, 用于按因子查询)

        Returns:
            commit_hash (8 字符 SHA1 前缀), 或 None (功能关闭).
        """
        if not getattr(self.config, 'enable_specification_logger', False):
            return None
        if self._spec_logger is None:
            from backtest.specification_logger import SpecificationLogger
            self._spec_logger = SpecificationLogger(
                log_dir=getattr(self.config, 'spec_log_dir', 'logs/specifications/'),
            )
        return self._spec_logger.log_run(
            config, result, run_type=run_type, factor_name=factor_name,
        )

    def check_endogeneity(
        self,
        raw_factor_with_missing: Optional[pd.DataFrame] = None,
        imputed_factor: Optional[pd.DataFrame] = None,
        neutralized_factor: Optional[pd.DataFrame] = None,
        decoupled_factor: Optional[pd.DataFrame] = None,
        returns: Optional[pd.DataFrame] = None,
        controls: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """v3.1.0 E3 (§1): 事后内生性四阶段诊断 (S1-S4).

        委托到 EndogeneityDiagnosticOrchestrator. 不侵入 fit/transform,
        与 monitor_cusum_drift / diagnose_hidden_effects 模式一致.

        四阶段 (v1.3 修正):
        - S1 插补前缺失机制 (MCAR/MAR/MNAR): 分类标签 + mnar_risk_prior
        - S2 插补后基线: 连续 τ ∈ [0,1]
        - S3 中性化后残留 (可选): 连续 τ
        - S4 解耦后最终: 连续 τ_i
        - S1→S2 上下文衔接 (逻辑衔接, 非数值乘法/非数值差分)
        - S3-S2, S4-S3, S4-S2 是数值差分

        Args:
            raw_factor_with_missing: 原始含缺失因子 (T, N), 用于 S1
            imputed_factor: 插补后因子 (T, N), 用于 S2
            neutralized_factor: 中性化后因子 (T, N), 用于 S3 (可选)
            decoupled_factor: 解耦后因子 (T, N), 用于 S4
            returns: 未来收益 (T, N)
            controls: 控制变量 (T, N, K), 可选

        Returns:
            诊断 dict (含 s1/s2/s4 报告与 final_threat_tau), 或 None (功能关闭).
            enable_endogeneity_check=False 时返回 None.
        """
        if not getattr(self.config, 'enable_endogeneity_check', False):
            return None

        from factor_pipeline.modules.endogeneity_check import (
            EndogeneityDiagnosticOrchestrator,
        )

        methods = list(getattr(self.config, 'endogeneity_methods', ['oster_delta', 'aet']))
        enable_ife = getattr(self.config, 'enable_ife_endogeneity_check', False)
        enable_lewbel = getattr(self.config, 'enable_lewbel_endogeneity_check', False)
        enable_s3 = getattr(self.config, 'enable_s3_neutralization_check', False)
        threat_threshold = getattr(self.config, 'oster_threat_threshold', 0.1)
        r_max_multiplier = getattr(self.config, 'oster_r_max_multiplier', 1.3)
        ife_max_dim = getattr(self.config, 'endogeneity_ife_max_dim', 5)
        if enable_ife and 'ife' not in methods:
            methods.append('ife')
        if enable_lewbel and 'lewbel' not in methods:
            methods.append('lewbel')

        orch = EndogeneityDiagnosticOrchestrator(
            methods=methods,
            threat_threshold=threat_threshold,
            enable_s3=enable_s3,
            enable_ife=enable_ife,
            enable_lewbel=enable_lewbel,
            r_max_multiplier=r_max_multiplier,
            ife_max_dim=ife_max_dim,
        )

        report: Dict[str, Any] = {}
        # S1: 缺失机制诊断 (插补前)
        if raw_factor_with_missing is not None and getattr(
            self.config, 'enable_missingness_diagnosis', False
        ):
            report['s1'] = orch.diagnose_s1_pre_imputation(
                raw_factor_with_missing, returns
            )
        else:
            report['s1'] = None

        # S2: 插补后基线
        s2_data = imputed_factor if imputed_factor is not None else raw_factor_with_missing
        if s2_data is not None and returns is not None:
            try:
                report['s2'] = orch.diagnose_s2_post_imputation(s2_data, returns, controls)
            except Exception as e:
                logger.warning(f"S2 内生性诊断失败: {e}")
                report['s2'] = None
        else:
            report['s2'] = None

        # S3: 中性化后残留 (可选)
        if neutralized_factor is not None and returns is not None:
            try:
                report['s3'] = orch.diagnose_s3_post_neutralization(
                    neutralized_factor, returns, controls
                )
            except Exception as e:
                logger.warning(f"S3 内生性诊断失败: {e}")
                report['s3'] = None
        else:
            report['s3'] = None

        # S4: 解耦后最终
        s4_data = decoupled_factor if decoupled_factor is not None else imputed_factor
        if s4_data is not None and returns is not None:
            try:
                report['s4'] = orch.diagnose_s4_post_decoupling(s4_data, returns, controls)
            except Exception as e:
                logger.warning(f"S4 内生性诊断失败: {e}")
                report['s4'] = None
        else:
            report['s4'] = None

        report['final_assessment'] = orch.get_final_threat_assessment()
        self._endogeneity_orchestrator = orch
        self._endogeneity_report = report
        return report

    def check_granger_causality(
        self,
        factor_series: pd.Series,
        return_series: pd.Series,
    ) -> Optional[Dict[str, Any]]:
        """v3.1.0 E4 (§4): 事后格兰杰因果检验 (Toda-Yamamoto 1995).

        委托到 TodaYamamotoGrangerTester. 不侵入 fit/transform.
        ADF → VAR(p+d) → Wald 完整流程; contemporaneous_causality='unidentified'.

        Args:
            factor_series: 因子时序 (T,)
            return_series: 收益时序 (T,)

        Returns:
            诊断 dict (含 wald_factor_to_return / wald_return_to_factor /
            f_granger_cause_r / contemporaneous_causality 等), 或 None (功能关闭).
            enable_granger_attribution=False 时返回 None.
        """
        if not getattr(self.config, 'enable_granger_attribution', False):
            return None

        from factor_pipeline.backtest.granger_attribution import (
            TodaYamamotoGrangerTester,
        )

        tester = TodaYamamotoGrangerTester(
            max_lag=getattr(self.config, 'granger_max_lag', 12),
            use_bootstrap=getattr(self.config, 'granger_use_bootstrap', False),
        )
        try:
            tester.fit(factor_series, return_series)
            report = tester.get_diagnostics()
        except Exception as e:
            logger.warning(f"格兰杰因果检验失败: {e}")
            report = {
                'integration_order': 0,
                'selected_lag': 1,
                'wald_factor_to_return': {},
                'wald_return_to_factor': {},
                'f_granger_cause_r': False,
                'r_granger_cause_f': False,
                'contemporaneous_causality': 'unidentified',
                'bootstrap_result': None,
                'interpretation': f'检验失败: {e}',
                'warning': '格兰杰因果 ≠ 结构因果 — 仅为伪回归初筛',
            }
        self._granger_report = report
        return report

    def log_fingerprint_performance(
        self,
        factor_data: Optional[Dict[str, pd.DataFrame]] = None,
        returns: Optional[pd.DataFrame] = None,
    ) -> Optional[Any]:
        """RESEARCH_NOTES E4: 记录指纹性能日志 (事后诊断, 不侵入 fit/transform).

        将当前 self.fingerprints_ 的 21 维指纹 + 因子表现 + 管道权重
        持久化到 DuckDB, 供 E5 AttributionAnalyzer 使用.

        Args:
            factor_data: 因子数据字典 (可选, 默认用 self.processed_data_)
            returns: 未来收益 (可选, 用于计算因子表现)

        Returns:
            FingerprintPerformanceLogger 实例 (enable=False 时返回 None)
        """
        if not getattr(self.config, 'enable_fingerprint_performance_log', False):
            return None

        from factor_pipeline.backtest.fingerprint_performance_logger import (
            FingerprintPerformanceLogger,
        )

        if self._fp_logger is None:
            self._fp_logger = FingerprintPerformanceLogger(
                db_path=getattr(self.config, 'fp_log_db_path', 'factor_db.duckdb'),
                table_name=getattr(self.config, 'fp_log_table_name', 'fingerprint_performance_log'),
                enable=True,
            )

        # 遍历已拟合的指纹, 记录每因子的指纹 + 表现
        fingerprints = getattr(self, 'fingerprints_', {})
        for fname, fp in fingerprints.items():
            # 计算因子表现 (如有 returns)
            performance: Dict[str, float] = {}
            if returns is not None and factor_data is not None and fname in factor_data:
                f_vals = factor_data[fname].iloc[:, 0] if hasattr(factor_data[fname], 'iloc') else factor_data[fname]
                aligned = pd.concat([f_vals, returns.iloc[:, 0] if returns.ndim > 1 else returns], axis=1).dropna()
                if len(aligned) > 5:
                    from scipy.stats import spearmanr
                    ic_series = aligned.apply(
                        lambda row: spearmanr(row.iloc[0], row.iloc[1])[0]
                        if len(row) == 2 else float('nan'),
                        axis=1,
                    ) if aligned.shape[1] == 2 else pd.Series(dtype=float)
                    # 简化: 用整体 IC
                    if aligned.shape[1] == 2:
                        ic_val, _ = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
                        performance = {
                            'ic_mean': float(ic_val) if not np.isnan(ic_val) else 0.0,
                            'ic_std': 0.0,
                            'ic_ir': 0.0,
                            'turnover': 0.0,
                            'max_drawdown': 0.0,
                            'sharpe_ratio': 0.0,
                        }

            # 管道权重
            weights = getattr(self, 'pipeline_weights_', {}).get(fname, {})
            pipeline_weights = {
                'weight_static': float(weights.get('static', 0.0)),
                'weight_dynamic': float(weights.get('dynamic', 0.0)),
                'weight_mixed': float(weights.get('mixed', 0.0)),
            }

            try:
                self._fp_logger.log(
                    factor_name=fname,
                    fingerprint=fp,
                    performance=performance,
                    pipeline_weights=pipeline_weights,
                )
            except Exception as e:
                logger.warning(f"指纹性能日志记录失败 (factor={fname}): {e}")

        return self._fp_logger

    def get_fingerprint_performance_log(self, **query_kwargs) -> pd.DataFrame:
        """RESEARCH_NOTES E4: 查询指纹性能日志.

        Args:
            **query_kwargs: 传递给 FingerprintPerformanceLogger.query()
                           (factor_name, start_date, end_date, regime)

        Returns:
            查询结果 DataFrame (enable=False 或无记录时返回空 DataFrame)
        """
        if self._fp_logger is None or not getattr(self._fp_logger, 'enable', False):
            return pd.DataFrame()
        return self._fp_logger.query(**query_kwargs)

    def apply_endogeneity_regularization(
        self,
        threat_assessment: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """v3.1.0 E5 (§5): 事后应用三层内生性正则化.

        基于 E3 的 final_threat_assessment, 协调三层正则化配置:
          L1 预处理层: DualNeutralizer 中性化强度 (skip_stage2/threat_level)
          L2 检验层:   factor_significance 显著性阈值 α (α = α_base × (1 - γ × τ))
          L3 组合层:   optimizer 因子权重惩罚 (w = w_raw × (1 - ρ × τ))

        硬依赖 E3: threat_assessment 必须含 final_threat_tau.
        enable_endogeneity_regularization=False 时返回 None (向后兼容).

        Args:
            threat_assessment: E3 EndogeneityDiagnosticOrchestrator.get_final_threat_assessment()
                              返回的 dict. None 时使用 self._endogeneity_report.

        Returns:
            三层正则化配置 dict, 或 None (功能关闭).
            {
                'l1_neutralizer': {...},
                'l2_significance': {...},
                'l3_optimizer': {...},
                'threat_tau': float,
            }
        """
        if not getattr(self.config, 'enable_endogeneity_regularization', False):
            return None

        # 优先用参数, 否则用缓存的 E3 报告
        assessment = threat_assessment
        if assessment is None:
            assessment = getattr(self, '_endogeneity_report', None)
            if assessment is not None and 'final_assessment' in assessment:
                assessment = assessment['final_assessment']
        if assessment is None:
            logger.warning(
                "E5 三层正则化: 未提供 threat_assessment, 且 E3 未运行. "
                "请先运行 check_endogeneity() 或直接传入 threat_assessment."
            )
            return None

        from factor_pipeline.modules.endogeneity_regularizer import (
            EndogeneityRegularizer,
        )

        reg = EndogeneityRegularizer(
            threat_assessment=assessment,
            reg_gamma=getattr(self.config, 'regularizer_gamma', 0.5),
            reg_strength_rho=getattr(self.config, 'regularizer_rho', 0.3),
        )

        tau = float(assessment.get('final_threat_tau', 0.0))
        result = {
            'l1_neutralizer': reg.apply_l1_neutralizer_config(tau),
            'l2_significance': reg.apply_l2_significance_config(tau),
            'l3_optimizer': reg.apply_l3_optimizer_config(tau, w_raw=1.0),
            'threat_tau': tau,
        }
        self._regularizer_config = result
        return result

    def estimate_with_endogeneity_mitigation(
        self,
        factor_data: pd.DataFrame,
        returns: pd.DataFrame,
        controls: Optional[pd.DataFrame] = None,
    ) -> Optional[Dict[str, Any]]:
        """v3.1.0 E6 (§5.10): 事后估计层内生性缓解.

        四种估计器 (Profile GMM / IVX / DOLS / PFGMM) + 方法选择器,
        全部 opt-in. 与 E5 互补: E6 先估计, E5 再正则化残留威胁.

        enable_endogeneity_estimators=False 时返回 None (向后兼容).

        Args:
            factor_data: 因子数据 (T, N)
            returns: 未来收益 (T, N)
            controls: 控制变量 (可选)

        Returns:
            估计结果 dict (含 method/beta/residual_threat_tau), 或 None (功能关闭).
        """
        if not getattr(self.config, 'enable_endogeneity_estimators', False):
            return None

        method = getattr(self.config, 'estimator_method', 'auto')

        # auto 模式: 用方法选择器 (软依赖 E3 诊断)
        if method == 'auto':
            assessment = getattr(self, '_endogeneity_report', None)
            final_assessment = None
            if assessment is not None and 'final_assessment' in assessment:
                final_assessment = assessment['final_assessment']
            elif assessment is not None and 'final_threat_tau' in assessment:
                final_assessment = assessment
            else:
                # E3 未运行, 降级为默认 Profile GMM
                final_assessment = {'final_threat_tau': 0.5}

            from factor_pipeline.modules.endogeneity_estimators.core.method_selector import (
                EndogeneityMethodSelector,
            )
            selector = EndogeneityMethodSelector()
            selection = selector.select(final_assessment, factor_data=factor_data)
            method = selection['recommended_method']
            # 'none' 时返回空结果 (仅三层正则化即可)
            if method == 'none':
                return {
                    'method': 'none',
                    'reason': selection['reason'],
                    'beta': float('nan'),
                    'residual_threat_tau': float(
                        final_assessment.get('final_threat_tau', 0.0)
                    ),
                }

        # 实例化对应估计器
        if method == 'profile_gmm' or (
            method != 'ivx' and method != 'dols' and method != 'pfgmm'
            and getattr(self.config, 'enable_profile_gmm', False)
        ):
            from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
                ProfileGMMEstimator,
            )
            est = ProfileGMMEstimator(
                nuclear_lambda=getattr(self.config, 'profile_gmm_nuclear_lambda', 0.1),
            )
        elif method == 'ivx':
            from factor_pipeline.modules.endogeneity_estimators.core.ivx import (
                IVXEstimator,
            )
            est = IVXEstimator(
                alpha=getattr(self.config, 'ivx_alpha', None),
            )
        elif method == 'dols':
            from factor_pipeline.modules.endogeneity_estimators.core.regularized_dols import (
                RegularizedDOLSEstimator,
            )
            est = RegularizedDOLSEstimator(
                lag_order=getattr(self.config, 'dols_lag_order', 3),
                lambda_l1=getattr(self.config, 'dols_lambda_l1', 0.0),
                lambda_l2=getattr(self.config, 'dols_lambda_l2', 0.0),
            )
        elif method == 'pfgmm':
            from factor_pipeline.modules.endogeneity_estimators.core.pfgmm import (
                PFGMMEstimator,
            )
            est = PFGMMEstimator(
                penalty=getattr(self.config, 'pfgmm_penalty', 'scad'),
                lambda_penalty=getattr(self.config, 'pfgmm_lambda', 0.1),
            )
        else:
            # 默认 Profile GMM
            from factor_pipeline.modules.endogeneity_estimators.core.profile_gmm import (
                ProfileGMMEstimator,
            )
            est = ProfileGMMEstimator(
                nuclear_lambda=getattr(self.config, 'profile_gmm_nuclear_lambda', 0.1),
            )

        est.fit(factor_data, returns, controls)
        diag = est.get_diagnostics()
        self._estimation_report = diag
        return diag

    def get_classification_summary(self) -> pd.DataFrame:
        """获取分类汇总表 (v3.4.0 ADR: 保留旧列 + 追加 2 列执行事实)"""
        rows = []
        for name, cls in self.factor_classifications.items():
            rec = self.factor_routing.get(name)
            rows.append({
                'factor_name': name,
                'primary_type': cls.primary_type.value,
                'primary_prob': cls.primary_prob,
                'secondary_type': cls.secondary_type.value if cls.secondary_type else None,
                'secondary_prob': cls.secondary_prob,
                'confidence': cls.confidence,
                'is_hard': cls.is_hard,
                'execution_pipe_type': rec.execution_pipe_type if rec else None,
                'sampling_frequency': (
                    rec.fingerprint_meta.sampling_frequency if rec else None),
            })
        return pd.DataFrame(rows)

    def get_routing_summary(self) -> pd.DataFrame:
        """v3.4.0 ADR: 路由记录汇总表 (执行事实 + 指纹元数据, 行数 = 因子数)"""
        rows = []
        for name, r in self.factor_routing.items():
            rows.append({
                'factor_name': name,
                'pipeline_mode': r.pipeline_mode,
                'execution_pipe_type': r.execution_pipe_type,
                'diagnostic_type': r.diagnostic_type,
                'diagnostic_prob': r.diagnostic_prob,
                'diagnostic_confidence': r.diagnostic_confidence,
                'ar1_median': r.ar1_median,
                'sampling_frequency': r.fingerprint_meta.sampling_frequency,
                'n_obs': r.fingerprint_meta.n_obs,
                'n_columns': r.fingerprint_meta.n_columns,
                'start': r.fingerprint_meta.start,
                'end': r.fingerprint_meta.end,
            })
        return pd.DataFrame(rows)

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
        """获取执行摘要 (v3.4.0 ADR: 执行管道 + 指纹诊断两段, 不再把诊断标签写成执行结果)"""
        lines = ["=" * 60]
        lines.append("FactorProcessingPipelineV2 执行摘要")
        lines.append("=" * 60)

        # 第一段: 执行管道事实 (唯一可信来源 = factor_routing)
        lines.append("\n[执行管道]")
        routing = self.get_routing_summary()
        if not routing.empty:
            for _, row in routing.iterrows():
                lines.append(
                    f"  {row['factor_name']}: pipe={row['execution_pipe_type']} "
                    f"(mode={row['pipeline_mode']}, freq={row['sampling_frequency']}, "
                    f"n_obs={row['n_obs']}, ar1={row['ar1_median']:.4f})")

        # 第二段: 指纹诊断 (只读标签, 不代表实际执行)
        lines.append("\n[指纹诊断标签]")
        summary = self.get_classification_summary()
        if not summary.empty:
            for _, row in summary.iterrows():
                lines.append(f"  {row['factor_name']}: {row['primary_type']} "
                             f"(prob={row['primary_prob']:.2f}, confidence={row['confidence']:.2f})")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
