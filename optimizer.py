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
    'classification_threshold_static': {'type': 'float', 'low': 0.5,  'high': 1.0},
    'classification_threshold_dynamic': {'type': 'float', 'low': 0.0, 'high': 0.5},
    'migration_threshold':            {'type': 'float', 'low': 0.0,  'high': 1.0},
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
        random_seed: int = 42,
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
        self.random_seed = random_seed

        self.search_space = dict(DEFAULT_SEARCH_SPACE)

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

        # P0-2: migration_threshold — 影响 monitor 的迁移判定
        if 'migration_threshold' in params:
            config.monitor.enable_smooth_transition = True
            # migration_threshold 用作 monitor 的相似度阈值
            # 如果 MonitorConfig 有相关字段则设置
            if hasattr(config.monitor, 'migration_threshold'):
                config.monitor.migration_threshold = params['migration_threshold']
            elif hasattr(config.monitor, 'similarity_threshold'):
                config.monitor.similarity_threshold = params['migration_threshold']

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
    ) -> float:
        """
        计算 cross-sectional IC。

        输入 shape: (n_entities, n_periods) — 每行是一个实体 (stock),
        每列是一个时期。对每个时期 t 计算截面 corr,取均值。

        手工计算: IC = mean(corr(factor[:, t], return[:, t]) for each period t)
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
        KS 分布保真度约束。

        手工计算: 对变换前后的因子分别做 KS 检验。
        fidelity = min(1.0, -log10(min_p) / 10)
        当 min_p 很小时（分布显著不同），fidelity 接近 0。
        当 min_p 很大时（分布相似），fidelity 接近 1。
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
        # -log10 变换: p=0.01 → 2, p=0.001 → 3, p=1e-10 → 10
        # 除以 10 归一化到 [0, 1]
        fidelity = min(1.0, -np.log10(max(min_p, 1e-10)) / 10.0)
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

    def _composite_objective(
        self,
        ic_array: np.ndarray,
        n_processed: int,
        n_total: int,
        before: Optional[np.ndarray] = None,
        after: Optional[np.ndarray] = None,
    ) -> float:
        """
        复合目标函数。

        手工计算:
          objective = IC_mean
                    - lambda_volatility * vol_penalty
                    - lambda_coverage * coverage_penalty
                    + lambda_fidelity * fidelity

        最大化 IC 的同时惩罚高波动、低覆盖率和分布失真。
        """
        ic_mean = float(np.nanmean(ic_array))
        vol_penalty = self._ic_volatility_penalty(ic_array)
        cov_penalty = self._coverage_penalty(n_processed, n_total)

        fidelity = 0.0
        if before is not None and after is not None:
            fidelity = self._ks_distribution_fidelity(before, after)

        objective = (
            ic_mean
            - self.lambda_volatility * vol_penalty
            - self.lambda_coverage * cov_penalty
            + self.lambda_fidelity * fidelity
        )
        return float(objective)

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
                    params[name] = trial.suggest_float(
                        name, spec['low'], spec['high']
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

        return self.best_params

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