# -*- coding: utf-8 -*-
"""
P3 Phase 3: 端到端阈值优化器

使用 Optuna TPE 贝叶斯优化 + 扩展窗口交叉验证，
自动搜索最优的流水线阈值参数。

目标函数: IC 主目标 + 约束惩罚
  - 主目标: mean IC (Information Coefficient)
  - 约束: IC 波动性惩罚、覆盖率惩罚、KS 分布保真度

Dependencies
------------
optuna >= 3.0.0
scipy >= 1.7.0
"""

from typing import Dict, Optional, List, Tuple, Callable
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 可选依赖: optuna — pyproject.toml [optimizer] extra
try:
    import optuna
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False
    optuna = None

# P2.5: scipy 现为 REQUIRED 依赖 (pyproject.toml 声明), 直接导入
from scipy import stats as scipy_stats

# P2.5: factor_pipeline.pipelines_v2 是自身模块, 不应该有 ImportError, 直接导入
from factor_pipeline.pipelines_v2 import (
    FactorProcessingPipelineV2, PipelineV2Config,
)
HAS_PIPELINE = True  # 保留向后兼容


# =============================================================================
# 搜索空间定义
# =============================================================================

DEFAULT_SEARCH_SPACE = {
    'hard_routing_prob':              {'type': 'float', 'low': 0.5,  'high': 1.0},
    'merge_alpha':                    {'type': 'float', 'low': 0.0,  'high': 1.0},
    'ks_alpha':                       {'type': 'float', 'low': 0.001, 'high': 0.5},
    'mixed_winsor_sigma':             {'type': 'float', 'low': 1.0,  'high': 10.0},
    'transform_aggressiveness':       {'type': 'float', 'low': 0.3,  'high': 5.0},
    'classification_threshold_static': {'type': 'float', 'low': 0.5, 'high': 1.0},
    'classification_threshold_dynamic': {'type': 'float', 'low': 0.0, 'high': 0.5},
    'migration_threshold':            {'type': 'float', 'low': 0.0,  'high': 1.0},
}


# v2.6.0 P3-13 (E5): 正交化参数搜索空间 (仅 search_orth=True 时激活)
# 不搜索 orth_enabled (用户决策, 非优化器决策)
DEFAULT_SEARCH_SPACE_ORTH = {
    'orth_method': {
        'type': 'categorical',
        'choices': ['symmetric', 'ridge', 'pca', 'gram_schmidt'],
    },
    'orth_align_mode': {
        'type': 'categorical',
        'choices': ['intersection', 'union_nan'],  # 不搜索 raise_on_mismatch
    },
    'orth_ridge_lambda': {
        'type': 'float', 'low': 0.01, 'high': 100.0,
        'log': True,  # log-uniform (λ 跨度大)
    },
}


class EndToEndThresholdOptimizer:
    """
    端到端阈值优化器。

    使用 Optuna TPE 贝叶斯优化在扩展窗口交叉验证框架下
    自动搜索最优流水线阈值参数。

    Parameters
    ----------
    n_trials : int
        优化试验次数（默认 100）
    cv_min_train : int
        CV 最小训练窗口大小（默认 12）
    cv_test_size : int
        CV 测试窗口大小（默认 3）
    lambda_volatility : float
        IC 波动性惩罚系数（默认 0.5）
    lambda_coverage : float
        覆盖率惩罚系数（默认 0.3）
    lambda_fidelity : float
        KS 分布保真度权重（默认 0.1）
    random_seed : int
        随机种子（默认 42）

    Examples
    --------
    >>> optimizer = EndToEndThresholdOptimizer(n_trials=50)
    >>> best_params = optimizer.optimize(factor_data, forward_returns)
    >>> best_config = optimizer._params_to_config(best_params)
    """

    def __init__(
        self,
        n_trials: int = 100,
        cv_min_train: int = 12,
        cv_test_size: int = 3,
        lambda_volatility: float = 0.5,
        lambda_coverage: float = 0.3,
        lambda_fidelity: float = 0.1,
        lambda_health: float = 0.4,  # v2.6.0 E4: health_penalty 代理权重
        lambda_redundancy: float = 0.05,  # v2.6.0 E6: 冗余惩罚 (v1.1 从 0.1 降为 0.05)
        random_seed: int = 42,
        search_orth: bool = False,  # v2.6.0 E5: 正交化参数搜索
    ):
        if not HAS_OPTUNA:
            raise ImportError(
                "EndToEndThresholdOptimizer 需要 optuna: pip install optuna"
            )

        self.n_trials = n_trials
        self.cv_min_train = cv_min_train
        self.cv_test_size = cv_test_size
        self.lambda_volatility = lambda_volatility
        self.lambda_coverage = lambda_coverage
        self.lambda_fidelity = lambda_fidelity
        self.lambda_health = lambda_health  # v2.6.0 E4
        self.lambda_redundancy = lambda_redundancy  # v2.6.0 E6
        self.random_seed = random_seed
        self.search_orth = search_orth  # v2.6.0 E5

        # v2.6.0 E5: 根据 search_orth 标志合并搜索空间
        self.search_space = dict(DEFAULT_SEARCH_SPACE)
        if search_orth:
            self.search_space.update(DEFAULT_SEARCH_SPACE_ORTH)

        # 优化结果
        self.study: Optional['optuna.Study'] = None
        self.best_params: Optional[Dict[str, float]] = None
        self.best_score: Optional[float] = None

    # =========================================================================
    # 搜索空间管理
    # =========================================================================

    def _params_to_config(self, params: Dict[str, float]) -> 'PipelineV2Config':
        """将优化参数字典映射到 PipelineV2Config (P0-2: 完整 8 参数映射)"""
        # P2.5: HAS_PIPELINE 永远为 True (自身模块), 删除死代码检查

        config = PipelineV2Config(
            hard_routing_prob=params.get('hard_routing_prob', 0.90),
            merge_alpha=params.get('merge_alpha', 0.50),
            ks_alpha=params.get('ks_alpha', 0.05),
            mixed_winsor_sigma=params.get('mixed_winsor_sigma', 3.0),
        )

        # classification_threshold_static/dynamic 位于 ClassificationConfig 子配置中
        if 'classification_threshold_static' in params:
            config.classification.static_ar1_threshold = params['classification_threshold_static']
        if 'classification_threshold_dynamic' in params:
            config.classification.dynamic_ar1_threshold = params['classification_threshold_dynamic']

        # P0-2: transform_aggressiveness — 通过 MixedFactorPipeline 的 winsor_sigma 间接影响
        # 用 mixed_winsor_sigma * transform_aggressiveness 组合控制
        if 'transform_aggressiveness' in params:
            aggr = params['transform_aggressiveness']
            # aggressiveness > 1 表示更激进,降低 winsor sigma 阈值
            config.mixed_winsor_sigma = max(
                1.0, config.mixed_winsor_sigma / max(aggr, 0.1)
            )

        # P3-10' (v2.6.0 E2): migration_threshold 字段位置修正
        # 修正前: 错误设置到 config.monitor.migration_threshold (MonitorConfig 无此字段,
        #         hasattr 静默跳过, 参数被丢弃)
        # 修正后: 字段位于 PipelineV2Config.migration_threshold (config 本身),
        #         默认值 0.10 与 PipelineV2ConfigUnified.migration_threshold 对齐
        if 'migration_threshold' in params:
            config.migration_threshold = params['migration_threshold']
            config.monitor.enable_smooth_transition = True

        # P3-13 (v2.6.0 E5): 正交化参数 (仅 search_orth=True 时存在)
        # 不搜索 orth_enabled (用户决策), 但设置 orth_method 后自动启用
        if 'orth_method' in params:
            # config.orthogonalization 默认 None, 需先实例化
            if config.orthogonalization is None:
                from factor_pipeline.config_v2 import OrthogonalizationConfig
                config.orthogonalization = OrthogonalizationConfig()
            config.orthogonalization.enabled = True  # 自动启用
            config.orthogonalization.method = params['orth_method']
        if 'orth_align_mode' in params:
            if config.orthogonalization is None:
                from factor_pipeline.config_v2 import OrthogonalizationConfig
                config.orthogonalization = OrthogonalizationConfig()
            config.orthogonalization.align_mode = params['orth_align_mode']
        # ridge_lambda 仅 method='ridge' 时设置 (避免污染其他方法)
        if ('orth_ridge_lambda' in params
                and config.orthogonalization is not None
                and config.orthogonalization.method == 'ridge'):
            config.orthogonalization.ridge_lambda = params['orth_ridge_lambda']

        return config

    def _config_to_params(self, config: 'PipelineV2Config') -> Dict[str, float]:
        """将 PipelineV2Config 映射回参数字典"""
        return {
            'hard_routing_prob': config.hard_routing_prob,
            'merge_alpha': config.merge_alpha,
            'ks_alpha': config.ks_alpha,
            'mixed_winsor_sigma': config.mixed_winsor_sigma,
            'transform_aggressiveness': 1.0,  # 默认值
            'classification_threshold_static': config.classification.static_ar1_threshold,
            'classification_threshold_dynamic': config.classification.dynamic_ar1_threshold,
            'migration_threshold': 0.10,  # 默认值
        }

    # =========================================================================
    # 目标函数组件
    # =========================================================================

    def _compute_ic(
        self,
        factor_values: np.ndarray,
        forward_returns: np.ndarray,
        weighting: str = 'equal',
        halflife: int = None,
    ) -> float:
        """
        计算 cross-sectional IC (v2.6.0 P3-1' 新增 EWMA 加权选项).

        输入 shape: (n_entities, n_periods) — 每行是一个实体 (stock),
        每列是一个时期。对每个时期 t 计算截面 corr, 取均值或 EWMA 加权.

        手工计算:
        - weighting='equal': IC = mean(corr(factor[:, t], return[:, t]) for each t)
        - weighting='ewma':  IC = sum(w[t] * corr(factor[:, t], return[:, t]))
                              其中 w[t] = (1-alpha)^(n-1-t), alpha = 1 - exp(-ln2/halflife)

        Parameters
        ----------
        factor_values, forward_returns : np.ndarray, shape (n_entities, n_periods)
        weighting : 'equal' | 'ewma'  (v2.6.0 P3-1' 新增)
            'equal': 等权 (默认, 向后兼容)
            'ewma': 指数加权, 近期 IC 权重更高
        halflife : int, optional
            EWMA 半衰期 (仅 weighting='ewma' 时生效)
            默认: max(1, n_periods // 4) (自适应)
        """
        if factor_values.shape != forward_returns.shape:
            logger.warning(
                f"shape 不匹配: factor={factor_values.shape}, "
                f"returns={forward_returns.shape}"
            )
            return float('nan')

        n_periods = factor_values.shape[1]
        ics = np.zeros(n_periods)

        for t in range(n_periods):
            f_t = factor_values[:, t]
            r_t = forward_returns[:, t]
            valid = ~(np.isnan(f_t) | np.isnan(r_t))
            if valid.sum() < 5:
                ics[t] = np.nan
                continue
            corr_matrix = np.corrcoef(f_t[valid], r_t[valid])
            ics[t] = corr_matrix[0, 1] if not np.isnan(corr_matrix[0, 1]) else np.nan

        # v2.6.0 P3-1': EWMA 时间加权
        if weighting == 'ewma':
            n = len(ics)
            if halflife is None:
                halflife = max(1, n // 4)
            alpha = 1.0 - np.exp(-np.log(2.0) / max(halflife, 1))
            weights = (1.0 - alpha) ** np.arange(n)[::-1]
            weights /= weights.sum()
            return float(np.nansum(ics * weights))

        return float(np.nanmean(ics))

    def _ic_volatility_penalty(self, ic_array: np.ndarray) -> float:
        """
        IC 波动性惩罚。

        手工计算: 当 std(IC) > 0.1 时施加惩罚。
        penalty = max(0, std(IC) - 0.1)
        """
        ic_std = float(np.nanstd(ic_array))
        return max(0.0, ic_std - 0.1)

    def _ks_distribution_fidelity(
        self,
        before: np.ndarray,
        after: np.ndarray,
    ) -> float:
        """
        KS 分布保真度 (v2.6.0 E4 修正语义).

        手工计算: 对变换前后的因子分别做 KS 检验.
        - p 高 = 分布相似 = 高保真 (fidelity 接近 1)
        - p 低 = 分布不同 = 低保真 (fidelity 接近 0)

        v2.6.0 E4 修正:
        - 原实现: fidelity = -log10(min_p) / 10 (p 高 → fidelity 低, 语义反, 实际是 distortion)
        - 新实现: fidelity = 1 - distortion (p 高 → fidelity 高, 语义正)
        """
        # P2.5: scipy 现为 REQUIRED 依赖, 不再有 HAS_SCIPY fallback
        if before.ndim == 1:
            before = before.reshape(-1, 1)
        if after.ndim == 1:
            after = after.reshape(-1, 1)

        n_cols = min(before.shape[1], after.shape[1])
        p_values = []

        for i in range(n_cols):
            b = before[:, i]
            a = after[:, i]
            valid_b = ~np.isnan(b)
            valid_a = ~np.isnan(a)
            if valid_b.sum() < 5 or valid_a.sum() < 5:
                continue
            _, p = scipy_stats.ks_2samp(b[valid_b], a[valid_a])
            p_values.append(p)

        if not p_values:
            return 1.0

        min_p = min(p_values)
        # distortion: p 低 → distortion 高 (分布不同)
        # -log10 变换: p=0.01 → 2, p=0.001 → 3, p=1e-10 → 10
        # 除以 10 归一化到 [0, 1]
        distortion = min(1.0, -np.log10(max(min_p, 1e-10)) / 10.0)
        # fidelity: 1 - distortion (p 高 → fidelity 高, 语义正)
        fidelity = 1.0 - distortion
        return float(fidelity)

    def _coverage_penalty(
        self,
        n_processed: int,
        n_total: int,
    ) -> float:
        """
        覆盖率惩罚。

        手工计算: 当覆盖率 < 50% 时施加惩罚。
        penalty = max(0, 0.5 - n_processed / n_total)
        """
        if n_total <= 0:
            return 0.5
        coverage = n_processed / n_total
        return max(0.0, 0.5 - coverage)

    def _health_penalty_proxy(self, ic_array: np.ndarray) -> float:
        """HealthMonitor 代理惩罚 (v2.6.0 E4 / P3-9')

        用 IC decay / hit rate / volatility 作为 health_score 的近似,
        避免 HealthMonitorAdapter.build_report_from_engine 的 engine_results 时序依赖.

        ADR-004 第 153 行:
            HealthMonitor 综合得分 (< 40 → -0.5, < 60 → -0.2)

        代理指标映射:
        - IC decay ratio (后半段/前半段): < 0.5 → 健康度低
        - IC hit rate: < 0.4 → 健康度低
        - IC volatility: > 0.2 → 健康度低

        Returns
        -------
        float
            0.5 (低健康度), 0.2 (中健康度), 0.0 (高健康度)
        """
        clean = ic_array[~np.isnan(ic_array)]
        if len(clean) < 6:
            return 0.0  # 数据不足, 不惩罚

        mid = len(clean) // 2
        ic_early = float(np.mean(clean[:mid]))
        ic_late = float(np.mean(clean[mid:]))

        # IC decay ratio
        if abs(ic_early) < 1e-10:
            decay_ratio = 1.0
        else:
            decay_ratio = ic_late / ic_early

        # IC hit rate
        hit_rate = float(np.mean(clean > 0))

        # IC volatility
        ic_vol = float(np.std(clean))

        # 代理 health_score: decay_ratio > 0.8 + hit_rate > 0.55 + ic_vol < 0.1 → 健康
        if decay_ratio < 0.5 or hit_rate < 0.4 or ic_vol > 0.2:
            return 0.5  # ADR-004: < 40 → -0.5
        elif decay_ratio < 0.8 or hit_rate < 0.5 or ic_vol > 0.15:
            return 0.2  # ADR-004: < 60 → -0.2
        return 0.0

    def _composite_objective(
        self,
        ic_array: np.ndarray,
        n_processed: int,
        n_total: int,
        before: Optional[np.ndarray] = None,
        after: Optional[np.ndarray] = None,
        redundancy_penalty: float = 0.0,  # v2.6.0 E6: 冗余惩罚
    ) -> float:
        """
        复合目标函数 (v2.6.0 E4 对齐 ADR-004, E6 新增 redundancy).

        ADR-004 第 147 行:
            score = IC_score - stability_penalty - ks_penalty - health_penalty - coverage_penalty

        v2.6.0 E4 修正:
        1. fidelity 符号方向: 奖励 → 惩罚 (ks_distortion_penalty = 1 - fidelity)
        2. 新增 health_penalty (代理指标, 解决 health_bridge 时序问题)

        v2.6.0 E6 新增:
        3. redundancy_penalty (基于 VRR, ADR-020): VRR < threshold 的因子扣分
        """
        ic_mean = float(np.nanmean(ic_array))
        vol_penalty = self._ic_volatility_penalty(ic_array)
        cov_penalty = self._coverage_penalty(n_processed, n_total)

        # 修正 1: KS 分布扭曲惩罚 (原 + λ_fid * fidelity 奖励, 符号方向相反)
        ks_distortion_penalty = 0.0
        if before is not None and after is not None:
            fidelity = self._ks_distribution_fidelity(before, after)
            ks_distortion_penalty = 1.0 - fidelity

        # 修正 2: HealthMonitor 代理惩罚 (基于 IC 系列特征)
        health_penalty = self._health_penalty_proxy(ic_array)

        # v2.6.0 E6: 冗余惩罚 (基于 VRR, ADR-020)
        # redundancy_penalty 已由 _redundancy_penalty 计算并传入

        objective = (
            ic_mean
            - self.lambda_volatility * vol_penalty
            - self.lambda_coverage * cov_penalty
            - self.lambda_fidelity * ks_distortion_penalty  # 修正: + → -
            - self.lambda_health * health_penalty            # 新增 (v2.6.0 E4)
            - self.lambda_redundancy * redundancy_penalty    # 新增 (v2.6.0 E6)
        )
        return float(objective)

    def _redundancy_penalty(
        self,
        pipeline: 'FactorProcessingPipelineV2',
        config: 'PipelineV2Config',
    ) -> float:
        """冗余惩罚 (v2.6.0 P3-14 / E6, 基于 VRR, ADR-020)

        VRR_k = Var(T_k)/Var(F_k), VRR << 1 表示因子 k 高度冗余.
        惩罚 = mean(max(0, vrr_threshold - VRR_k))  # VRR < threshold 的因子扣分

        lambda_redundancy = 0.05 (v1.1 从 0.1 降为 0.05, 避免与 IC 主目标双重惩罚)

        look-ahead bias 防护:
        - 正交化作为 post_transform_hook, 随 pipeline.fit(train_factor) 在 train 上估计 W
        - transform 时用 train 的 W 应用到 test
        - get_diagnostics() 返回的 F/T 是 train 上的, 无 look-ahead
        """
        # config.orthogonalization 默认 None (PipelineV2Config), 需先检查
        if config.orthogonalization is None or not config.orthogonalization.enabled:
            return 0.0  # 正交化未启用, 无冗余诊断

        # 从 OrthogonalizerAdapter (post_transform_hook) 获取 F/T 矩阵
        for hook in getattr(pipeline, 'post_transform_hooks', []):
            if hasattr(hook, 'get_diagnostics'):
                diag = hook.get_diagnostics()
                if 'F_stacked' in diag and diag['F_stacked'] is not None:
                    from factor_pipeline.modules.factor_orthogonalizer.core.diagnostics import (
                        OrthogonalizationDiagnostics
                    )
                    vrr = OrthogonalizationDiagnostics.compute_vrr(
                        diag['F_stacked'], diag['T_stacked']
                    )
                    vrr_threshold = config.orthogonalization.vrr_threshold
                    penalty = float(np.mean([
                        max(0.0, vrr_threshold - v) for v in vrr
                    ]))
                    return penalty
        return 0.0

    # =========================================================================
    # 扩展窗口交叉验证
    # =========================================================================

    def _generate_cv_folds(self, n_periods: int) -> List[Dict[str, Tuple[int, int]]]:
        """
        生成扩展窗口 CV folds。

        手工计算: 对于 n_periods=20, min_train=10, test_size=3
          fold 0: train=[0:10], test=[10:13]
          fold 1: train=[0:13], test=[13:16]
          fold 2: train=[0:16], test=[16:19]
        """
        folds = []
        train_end = self.cv_min_train

        while train_end + self.cv_test_size <= n_periods:
            folds.append({
                'train': (0, train_end),
                'test': (train_end, train_end + self.cv_test_size),
            })
            train_end += self.cv_test_size

        return folds

    def _cv_evaluate(
        self,
        factor_data: Dict[str, pd.DataFrame],
        forward_returns: pd.DataFrame,
        config: 'PipelineV2Config',
    ) -> float:
        """
        扩展窗口 CV 评估 (P2-2 改进)。

        对每个 fold:
          1. 在 train 期间的数据上 fit Pipeline (无 look-ahead)
          2. 在 test 期间的数据上 transform Pipeline
          3. 计算 test 期间的 IC

        返回各 fold 的平均复合目标分数。

        Args:
            factor_data: 因子名称到因子数据 (n_periods × n_stocks) 的映射
            forward_returns: 前向收益率 (n_periods × n_stocks)
            config: PipelineV2Config 配置

        Returns:
            平均 CV 分数 (float)
        """
        # P2.5: HAS_PIPELINE 永远为 True (自身模块), 删除死代码检查

        if not factor_data:
            return -1.0

        # 获取期数 (从第一个因子)
        first_factor = next(iter(factor_data.values()))
        n_periods = first_factor.shape[0]

        folds = self._generate_cv_folds(n_periods)

        if not folds:
            # 数据不足: 回退到全量评估 (Pipeline fit 1 次)
            logger.info(
                f"[CV] 数据不足 ({n_periods} 期 < {self.cv_min_train}+{self.cv_test_size}),"
                f" 回退到全量评估"
            )
            return self._full_evaluate(factor_data, forward_returns, config)

        scores = []
        all_fold_ics = []  # 跨 fold 的 IC (用于 vol_penalty)
        last_before = None
        last_after = None

        for fold_idx, fold in enumerate(folds):
            train_start, train_end = fold['train']
            test_start, test_end = fold['test']

            # 切分 train/test (按日期索引)
            train_factor = {
                name: df.iloc[train_start:train_end]
                for name, df in factor_data.items()
            }
            test_factor = {
                name: df.iloc[test_start:test_end]
                for name, df in factor_data.items()
            }
            test_returns = forward_returns.iloc[test_start:test_end]

            try:
                # P2-2: Pipeline 只在 train 上 fit (无 look-ahead)
                pipeline = FactorProcessingPipelineV2(
                    config=config, strict_mode=False,
                )
                pipeline.fit(train_factor)
                processed_test = pipeline.transform(test_factor)

                if not processed_test:
                    logger.debug(f"[CV] fold {fold_idx}: 无处理结果, 跳过")
                    continue

                # 计算 test IC
                fold_ics = []
                for name in processed_test:
                    if name not in test_factor:
                        continue
                    after_df = processed_test[name]
                    before_df = test_factor[name]

                    # 对齐索引
                    common_idx = after_df.index.intersection(test_returns.index)
                    common_cols = after_df.columns.intersection(test_returns.columns)
                    if len(common_idx) < 2 or len(common_cols) < 5:
                        continue

                    after_aligned = after_df.loc[common_idx, common_cols].T.values
                    returns_aligned = test_returns.loc[common_idx, common_cols].T.values
                    ic = self._compute_ic(after_aligned, returns_aligned)
                    if not np.isnan(ic):
                        fold_ics.append(ic)
                        # 保留最后一个 fold 的 before/after 用于 KS fidelity
                        if fold_idx == len(folds) - 1:
                            before_aligned = before_df.loc[common_idx, common_cols].T.values
                            last_before = before_aligned
                            last_after = after_aligned

                if fold_ics:
                    all_fold_ics.extend(fold_ics)
                    # 单 fold 的复合分数
                    ic_array = np.array(fold_ics)
                    fold_score = self._composite_objective(
                        ic_array,
                        n_processed=len(fold_ics),
                        n_total=len(processed_test),
                    )
                    scores.append(fold_score)

            except Exception as e:
                logger.warning(f"[CV] fold {fold_idx} 失败: {e}")
                continue

        if not scores:
            return -1.0

        # 跨 fold 的平均分数
        avg_score = float(np.mean(scores))

        # 用跨 fold 的 IC 计算额外的波动性惩罚
        if len(all_fold_ics) >= 3:
            ic_array = np.array(all_fold_ics)
            vol_penalty = self._ic_volatility_penalty(ic_array)
            avg_score -= self.lambda_volatility * vol_penalty * 0.5  # 半权重 (避免双重惩罚)

        return avg_score

    def _full_evaluate(
        self,
        factor_data: Dict[str, pd.DataFrame],
        forward_returns: pd.DataFrame,
        config: 'PipelineV2Config',
    ) -> float:
        """
        全量评估 (数据不足时的回退)。

        Pipeline 在全量数据上 fit + transform,计算 IC。
        """
        try:
            pipeline = FactorProcessingPipelineV2(
                config=config, strict_mode=False,
            )
            pipeline.fit(factor_data)
            processed = pipeline.transform(factor_data)

            if not processed:
                return -1.0

            all_ics = []
            before_sample = None
            after_sample = None

            for name in processed:
                if name not in factor_data:
                    continue
                after_df = processed[name]
                before_df = factor_data[name]

                common_idx = after_df.index.intersection(forward_returns.index)
                common_cols = after_df.columns.intersection(forward_returns.columns)
                if len(common_idx) < 5 or len(common_cols) < 5:
                    continue

                after_aligned = after_df.loc[common_idx, common_cols].T.values
                before_aligned = before_df.loc[common_idx, common_cols].T.values
                returns_aligned = forward_returns.loc[common_idx, common_cols].T.values

                ic = self._compute_ic(after_aligned, returns_aligned)
                if not np.isnan(ic):
                    all_ics.append(ic)
                    if before_sample is None:
                        before_sample = before_aligned
                        after_sample = after_aligned

            if not all_ics:
                return -1.0

            ic_array = np.array(all_ics)
            return self._composite_objective(
                ic_array,
                n_processed=len(all_ics),
                n_total=len(factor_data),
                before=before_sample,
                after=after_sample,
            )
        except Exception as e:
            logger.warning(f"全量评估失败: {e}")
            return -1.0

    # =========================================================================
    # 优化主流程
    # =========================================================================

    def optimize(
        self,
        factor_data: Dict[str, pd.DataFrame],
        forward_returns: pd.DataFrame,
        n_jobs: int = 1,
        show_progress: bool = True,
        validate_significance: bool = False,  # v2.6.0 E7: Layer 3 显著性最终验证
    ) -> Dict[str, float]:
        """
        执行端到端阈值优化。

        Parameters
        ----------
        factor_data : Dict[str, pd.DataFrame]
            因子名称到因子数据的映射
        forward_returns : pd.DataFrame
            前向收益率数据
        n_jobs : int
            并行任务数（默认 1）
        show_progress : bool
            是否显示进度条
        validate_significance : bool
            v2.6.0 E7: 是否在最优解找到后运行 Layer 3 显著性检验
            (默认 False, 仅最终验证, 计算成本约束)

        Returns
        -------
        Dict[str, float]
            最优参数字典
        """
        if not HAS_OPTUNA:
            raise ImportError("optuna 未安装: pip install optuna")

        # P2.5: HAS_PIPELINE 永远为 True (自身模块), 删除死代码检查

        n_total = len(factor_data)
        n_periods = forward_returns.shape[0]

        def objective(trial: 'optuna.Trial') -> float:
            """Optuna 目标函数 (P2-2: 使用 CV 评估,消除 look-ahead bias)"""
            # 采样参数
            params = {}
            for name, spec in self.search_space.items():
                if spec['type'] == 'float':
                    if spec.get('log', False):
                        # v2.6.0 E5: log-uniform 采样 (λ 跨度大)
                        params[name] = trial.suggest_float(
                            name, spec['low'], spec['high'], log=True
                        )
                    else:
                        params[name] = trial.suggest_float(
                            name, spec['low'], spec['high']
                        )
                elif spec['type'] == 'categorical':
                    # v2.6.0 E5: categorical 采样 (orth_method/align_mode)
                    params[name] = trial.suggest_categorical(
                        name, spec['choices']
                    )

            # 约束: 确保静态阈值 > 动态阈值
            if (params['classification_threshold_static']
                    <= params['classification_threshold_dynamic']):
                return -1.0  # 惩罚无效配置

            try:
                # P2-2: 使用 CV 评估而非全量数据
                # _cv_evaluate 会在每个 fold 的 train 上 fit Pipeline, test 上 transform
                config = self._params_to_config(params)
                score = self._cv_evaluate(factor_data, forward_returns, config)
                return score

            except Exception as e:
                logger.warning(f"Trial {trial.number} failed: {e}")
                return -1.0  # 返回最低分

        # 创建 study
        sampler = optuna.samplers.TPESampler(seed=self.random_seed)
        self.study = optuna.create_study(
            direction='maximize',
            sampler=sampler,
        )

        # 执行优化
        optuna.logging.set_verbosity(
            optuna.logging.WARNING if not show_progress else optuna.logging.INFO
        )

        self.study.optimize(
            objective,
            n_trials=self.n_trials,
            n_jobs=n_jobs,
            show_progress_bar=show_progress,
        )

        # 存储结果
        self.best_params = self.study.best_params
        self.best_score = self.study.best_value

        logger.info(
            f"Optimization complete: best_score={self.best_score:.6f}, "
            f"best_params={self.best_params}"
        )

        # v2.6.0 P3-15 / E7: Layer 3 显著性最终验证 (可选)
        self.significance_report = None
        if validate_significance:
            logger.info("Running Layer 3 significance validation...")
            try:
                self.significance_report = self._validate_significance(
                    self.best_params, factor_data, forward_returns
                )
                if self.significance_report.get('warning'):
                    logger.warning(self.significance_report['warning'])
            except Exception as e:
                logger.warning(f"Layer 3 significance validation failed: {e}")
                self.significance_report = {
                    'n_significant': 0, 'n_total': 0,
                    'significance_ratio': 0.0, 'details': {},
                    'warning': f'显著性验证失败: {e}',
                }

        return self.best_params

    def _validate_significance(
        self,
        best_params: Dict[str, float],
        factor_data: Dict[str, pd.DataFrame],
        forward_returns: pd.DataFrame,
    ) -> Dict:
        """对最优配置运行 Layer 3 显著性检验 (v2.6.0 P3-15 / E7)

        使用 FactorSignificanceTest (Belloni et al. 2014 PDS Lasso + HC3 + BH 校正)
        评估 best_params 下各因子的增量显著性.

        注意: 计算成本高 (K 次 LassoCV + K 次 OLS), 仅用于最终验证,
        不用于每 trial 评估 (计算成本约束).

        Args:
            best_params: 最优参数字典
            factor_data: 因子数据
            forward_returns: 前向收益率

        Returns:
            {
                'n_significant': int,
                'n_total': int,
                'significance_ratio': float,
                'details': Dict[str, Dict],
                'warning': Optional[str],  # significance_ratio < 0.5 时警告
            }
        """
        from factor_pipeline.backtest.factor_significance import FactorSignificanceTest

        # 空 factor_data 防护
        if not factor_data:
            return {
                'n_significant': 0, 'n_total': 0,
                'significance_ratio': 0.0, 'details': {},
                'warning': '因子数据为空, 无法验证',
            }

        # 用 best_params 构造 config, 处理因子
        config = self._params_to_config(best_params)
        pipeline = FactorProcessingPipelineV2(config=config, strict_mode=False)
        try:
            pipeline.fit(factor_data)
            processed = pipeline.transform(factor_data)
        except Exception as e:
            return {
                'n_significant': 0, 'n_total': len(factor_data),
                'significance_ratio': 0.0, 'details': {},
                'warning': f'Pipeline 处理失败: {e}',
            }

        if not processed:
            return {
                'n_significant': 0, 'n_total': 0,
                'significance_ratio': 0.0, 'details': {},
                'warning': 'Pipeline 处理后无因子',
            }

        # 运行 Layer 3 显著性检验
        fst = FactorSignificanceTest(
            method='double_lasso', alpha=0.05,
            correction='benjamini_hochberg',
        )
        factor_names = list(processed.keys())

        # v2.6.0 E7: 对齐 + dropna (LassoCV 不接受 NaN)
        # 1. 对齐所有因子到共同的 (date, stock) 索引
        # 2. 与 forward_returns 对齐
        # 3. 删除含 NaN 的行 (保证 LassoCV 能跑)
        aligned_factors = {}
        common_dates = processed[factor_names[0]].columns.intersection(
            forward_returns.index
        )
        common_stocks = processed[factor_names[0]].index.intersection(
            forward_returns.columns
        )
        for name in factor_names:
            df = processed[name].loc[common_stocks, common_dates]
            aligned_factors[name] = df
        aligned_returns = forward_returns.loc[common_dates, common_stocks]

        # 构造堆叠矩阵后 dropna (FactorSignificanceTest._stack_factor_returns 不 dropna)
        try:
            fst.fit(aligned_factors, aligned_returns, factor_names)
            # 内部 F_/y_ 可能含 NaN, dropna
            valid_mask = ~(np.isnan(fst.F_).any(axis=1) | np.isnan(fst.y_))
            if valid_mask.sum() < len(factor_names) + 5:
                # 有效样本不足, 直接返回 0
                return {
                    'n_significant': 0, 'n_total': len(factor_names),
                    'significance_ratio': 0.0, 'details': {},
                    'warning': f'有效样本不足 ({valid_mask.sum()} < {len(factor_names)+5})',
                }
            fst.F_ = fst.F_[valid_mask]
            fst.y_ = fst.y_[valid_mask]
            if fst.y_normalized_ is not None:
                fst.y_normalized_ = fst.y_normalized_[valid_mask]
            results = fst.test_all_factors()
        except Exception as e:
            return {
                'n_significant': 0, 'n_total': len(factor_names),
                'significance_ratio': 0.0, 'details': {},
                'warning': f'显著性检验失败: {e}',
            }

        n_significant = sum(
            1 for r in results.values() if r.get('is_significant', False)
        )
        n_total = len(results)
        significance_ratio = n_significant / n_total if n_total > 0 else 0.0

        warning = None
        if significance_ratio < 0.5:
            warning = (
                f"显著性比例 {significance_ratio:.1%} < 50%, "
                f"建议检查因子冗余或调整 P3-14 redundancy_penalty"
            )

        return {
            'n_significant': n_significant,
            'n_total': n_total,
            'significance_ratio': significance_ratio,
            'details': results,
            'warning': warning,
        }

    def get_best_config(self) -> 'PipelineV2Config':
        """获取最优配置"""
        if self.best_params is None:
            raise ValueError("尚未执行优化，请先调用 optimize()")
        return self._params_to_config(self.best_params)

    def get_param_importance(self) -> Dict[str, float]:
        """
        获取参数重要性。

        使用 Optuna 内置的 fanova 重要性评估。
        """
        if self.study is None:
            raise ValueError("尚未执行优化")

        try:
            importance = optuna.importance.get_param_importances(self.study)
            return dict(importance)
        except Exception:
            return {name: 0.0 for name in self.search_space}

    # =========================================================================
    # 可视化
    # =========================================================================

    def plot_param_importance(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: str = "Parameter Importance (fANOVA)",
        save_path: Optional[str] = None,
    ) -> None:
        """
        绘制参数重要性条形图。

        Parameters
        ----------
        figsize : Tuple[int, int]
            图像尺寸
        title : str
            图表标题
        save_path : Optional[str]
            保存路径（可选），支持 .png/.pdf/.svg
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib 未安装，无法绘图。pip install matplotlib")
            return

        if self.study is None:
            raise ValueError("尚未执行优化")

        importance = self.get_param_importance()

        # 过滤零值并按重要性排序
        items = sorted(
            [(k, v) for k, v in importance.items() if v > 0],
            key=lambda x: x[1],
        )
        if not items:
            items = sorted(importance.items(), key=lambda x: x[0])

        names = [item[0] for item in items]
        values = [item[1] for item in items]

        # 参数名简化
        short_names = [
            n.replace('classification_threshold_', 'cls_')
             .replace('mixed_winsor_', 'winsor_')
             .replace('transform_', 'trans_')
            for n in names
        ]

        fig, ax = plt.subplots(figsize=figsize)

        colors = plt.cm.Blues([0.4 + 0.5 * (v / max(values, default=1))
                                for v in values])

        bars = ax.barh(short_names, values, color=colors, edgecolor='#2c3e50', linewidth=0.5)

        # 数值标注
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + 0.005,
                bar.get_y() + bar.get_height() / 2,
                f'{val:.3f}',
                va='center',
                fontsize=9,
                color='#2c3e50',
            )

        ax.set_xlabel('Importance', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlim(0, max(values, default=1) * 1.3)
        ax.grid(axis='x', alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"参数重要性图已保存至: {save_path}")

        plt.show()

    def plot_optimization_history(
        self,
        figsize: Tuple[int, int] = (10, 5),
        save_path: Optional[str] = None,
    ) -> None:
        """
        绘制优化历史（目标函数值随 trial 的变化）。

        Parameters
        ----------
        figsize : Tuple[int, int]
            图像尺寸
        save_path : Optional[str]
            保存路径（可选）
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib 未安装，无法绘图。pip install matplotlib")
            return

        if self.study is None:
            raise ValueError("尚未执行优化")

        trials = self.study.trials
        values = [t.value for t in trials]
        best_so_far = np.maximum.accumulate(values)

        fig, ax = plt.subplots(figsize=figsize)

        ax.plot(values, 'o-', alpha=0.4, markersize=3, color='#3498db',
                label='Trial Score')
        ax.plot(best_so_far, '-', linewidth=2, color='#e74c3c',
                label='Best So Far')

        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

        ax.set_xlabel('Trial', fontsize=12)
        ax.set_ylabel('Objective Value', fontsize=12)
        ax.set_title('Optimization History', fontsize=14, fontweight='bold')
        ax.legend(loc='lower right')
        ax.grid(alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"优化历史图已保存至: {save_path}")

        plt.show()

    def plot_slice_plot(
        self,
        param_name: str,
        figsize: Tuple[int, int] = (8, 5),
        save_path: Optional[str] = None,
    ) -> None:
        """
        绘制单参数切片图（参数值 vs 目标函数值）。

        Parameters
        ----------
        param_name : str
            参数名称
        figsize : Tuple[int, int]
            图像尺寸
        save_path : Optional[str]
            保存路径（可选）
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib 未安装，无法绘图。pip install matplotlib")
            return

        if self.study is None:
            raise ValueError("尚未执行优化")

        if param_name not in self.search_space:
            raise ValueError(f"未知参数: {param_name}")

        param_values = []
        scores = []
        for trial in self.study.trials:
            if param_name in trial.params:
                param_values.append(trial.params[param_name])
                scores.append(trial.value)

        if not param_values:
            logger.warning(f"参数 {param_name} 无数据")
            return

        fig, ax = plt.subplots(figsize=figsize)

        ax.scatter(param_values, scores, alpha=0.5, s=20, c='#3498db',
                   edgecolors='white', linewidth=0.3)

        # 趋势线
        z = np.polyfit(param_values, scores, 2)
        x_range = np.linspace(min(param_values), max(param_values), 100)
        y_trend = np.polyval(z, x_range)
        ax.plot(x_range, y_trend, '-', color='#e74c3c', linewidth=2,
                alpha=0.7, label='Quadratic Trend')

        ax.set_xlabel(param_name, fontsize=12)
        ax.set_ylabel('Objective Value', fontsize=12)
        ax.set_title(f'Slice Plot: {param_name}', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"切片图已保存至: {save_path}")

        plt.show()