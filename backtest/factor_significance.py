# -*- coding: utf-8 -*-
"""O3b: 因子增量显著性检验 (Layer 3, 有监督)

架构层: Layer 3 (回测子模块)
位置: 所有因子处理完后跑, 不参与 Pipeline.transform() 循环
输入: K 因子 + 收益 Y
输出: p 值 / 系数 / 置信区间 / 选中的控制变量

学术依据: Belloni-Chernozhukov-Hansen (2014) Post-Double-Selection Lasso

双重 Lasso (Belloni 2014 PDS):
- Stage 1: Lasso Y ~ X → 选出 S_Y (与 Y 相关的因子)
- Stage 2: Lasso D_k ~ X → 选出 S_D (与 D_k 相关的因子)
- Stage 3: OLS Y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha

O4.9 工程深化 (v1.1):
- O4.9.1: Stage 3 OLS 加截距列, 与 LassoCV 的 fit_intercept=True 对齐
- O4.9.2: HC3 稳健标准误 (MacKinnon-White 1985), 默认 std_error_type='hc3'
- O4.9.3: 多重检验校正 (BH/Bonferroni/Holm), 默认 'benjamini_hochberg'
- O4.9.4: treatment 并行化 (joblib threading, sklearn 释放 GIL)
- O4.9.5: LassoCV 收敛检测 (n_iter_ 接近 max_iter 时告警)
- O4.9.6: Y 标准化 (Lasso 用标准化 Y, OLS 报告用原始 Y)
- O4.9.7: S_D 空集诊断信息
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LassoCV, ElasticNetCV

try:
    from joblib import Parallel, delayed
    _HAS_JOBLIB = True
except ImportError:
    _HAS_JOBLIB = False

# T3.5 (v3.0.0): 共享多重检验校正模块
try:
    from backtest.multiple_testing import apply_bh_fdr, apply_bonferroni
    _HAS_MULTIPLE_TESTING = True
except ImportError:
    _HAS_MULTIPLE_TESTING = False


class FactorSignificanceTest:
    """因子增量显著性检验

    双重 Lasso (Belloni 2014 PDS):
    - Stage 1: Lasso y ~ X (X = 其他 K-1 因子) → 选出 S_Y
    - Stage 2: Lasso D_k ~ X → 选出 S_D
    - Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha

    与 Layer 2 正交化的关系:
    - 正交化是预处理 (变换因子)
    - 双重 Lasso 是后处理检验 (验证增量 alpha)
    - 可串联: 正交化 → 双重 Lasso, 或直接双重 Lasso

    运行模式: treatment 轮询
    - 每个因子独立当 treatment, 跑一次双重 Lasso
    - 轮次顺序不影响结果 (每轮独立 OLS)
    - 不需要事先排序 (vs GS 强顺序依赖)
    """

    def __init__(
        self,
        method: str = 'double_lasso',
        cv_folds: int = 5,
        max_iter: int = 10000,
        eps: float = 1e-4,
        alpha: float = 0.05,
        std_error_type: str = 'hc3',
        correction: str = 'benjamini_hochberg',
        n_jobs: int = 1,
        backend: str = 'threading',
        lasso_params: Optional[Dict] = None,
    ):
        """
        Args:
            method: 'double_lasso' 或 'elastic_net'
            cv_folds: LassoCV 交叉验证折数
            max_iter: Lasso 最大迭代次数
            eps: Lasso 坐标下降收敛阈值 (O4.9.5)
            alpha: 显著性水平 (默认 0.05)
            std_error_type: 'ols' / 'hc1' / 'hc3' (O4.9.2, 默认 'hc3')
            correction: 'none' / 'bonferroni' / 'benjamini_hochberg' / 'holm'
                        (O4.9.3, 默认 'benjamini_hochberg')
            n_jobs: treatment 并行数 (O4.9.4)
                    - n_jobs=1: 串行, LassoCV 内部 n_jobs=-1 (推荐 K<=10)
                    - n_jobs>1: 外层线程并行, LassoCV 内部 n_jobs=1 (推荐 K>10)
            backend: joblib 后端 ('threading' / 'loky', O4.9.4)
            lasso_params: 透传给 LassoCV 的额外参数 (O4.9.5)
        """
        self.method = method
        self.cv_folds = cv_folds
        self.max_iter = max_iter
        self.eps = eps
        self.alpha = alpha
        self.std_error_type = std_error_type
        self.correction = correction
        self.n_jobs = n_jobs
        self.backend = backend
        self.lasso_params = lasso_params or {}
        # 外层并行时 LassoCV 内部串行 (避免嵌套并行)
        self._lasso_n_jobs = -1 if n_jobs == 1 else 1
        # O4.9.6: Y 标准化字段 (fit() 中填充, 兼容直接注入 F_/y_ 的测试场景)
        self.y_mean_ = 0.0
        self.y_std_ = 1.0
        self.y_normalized_ = None  # 在 _double_lasso_test 中惰性初始化

    # ── 公开接口 ──────────────────────────────────

    def fit(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        factor_names: List[str],
    ) -> 'FactorSignificanceTest':
        """拟合因子矩阵和收益向量

        Args:
            factor_dict: {因子名: (N, T) DataFrame} (可正交化或原始)
            fwd_returns: (T, N) 前向收益 DataFrame (来自 BacktestEngine)
            factor_names: 待检验的所有因子列表
        """
        self.factor_names_ = factor_names
        self.F_, self.y_, self.dates_, self.stocks_ = self._stack_factor_returns(
            factor_dict, fwd_returns, factor_names
        )
        # O4.9.6: Y 标准化 (供 Lasso 使用, 不影响 OLS 报告)
        self.y_mean_ = float(self.y_.mean())
        self.y_std_ = float(self.y_.std())
        if self.y_std_ > 1e-12:
            self.y_normalized_ = (self.y_ - self.y_mean_) / self.y_std_
        else:
            self.y_normalized_ = self.y_.copy()
        return self

    def test_incremental_alpha(self, target_factor: str) -> Dict:
        """检验目标因子在控制其他因子后是否有增量 alpha

        Args:
            target_factor: 待检验的因子名 (作为 treatment D_k)

        Returns:
            {
                'factor': str,
                'coefficient': float,
                'std_error': float,
                't_statistic': float,
                'p_value': float,
                'ci_lower': float,
                'ci_upper': float,
                'selected_controls': List[str],
                'is_significant': bool,
            }
        """
        if self.method == 'double_lasso':
            return self._double_lasso_test(target_factor)
        elif self.method == 'elastic_net':
            return self._elastic_net_path(target_factor)
        else:
            raise ValueError(f"未知 method: {self.method}")

    def test_all_factors(
        self,
        correction: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """对所有因子轮询当 treatment, 返回 K 个因子的检验结果

        运行模式: treatment 轮询 + 多重检验校正 (O4.9.3)
        - 每个因子独立当 treatment
        - 轮次顺序不影响结果
        - 默认应用 BH 校正 (可通过 correction 参数覆盖)

        Args:
            correction: 多重检验校正方法, None 时用 self.correction
        """
        corr = correction if correction is not None else self.correction

        if self.n_jobs == 1 or not _HAS_JOBLIB:
            # 串行
            results = {
                name: self.test_incremental_alpha(name)
                for name in self.factor_names_
            }
        else:
            # O4.9.4: 并行 (joblib threading)
            original_n_jobs = self._lasso_n_jobs
            self._lasso_n_jobs = 1  # 外层并行时, 内部串行

            def _test_one(name):
                return name, self.test_incremental_alpha(name)

            try:
                raw = Parallel(
                    n_jobs=self.n_jobs, backend=self.backend
                )(delayed(_test_one)(name) for name in self.factor_names_)
                results = dict(raw)
            finally:
                self._lasso_n_jobs = original_n_jobs

        # 多重检验校正
        return self._apply_correction(results, corr)

    # ── 双重 Lasso 实现 ──────────────────────────────────

    def _double_lasso_test(self, target_factor: str) -> Dict:
        """Belloni-Chernozhukov-Hansen (2014) 双重 Lasso

        Stage 1: Lasso y ~ X (X = 其他 K-1 因子) → 选出 S_Y
        Stage 2: Lasso D_k ~ X → 选出 S_D
        Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D} → D_k 系数即净化后增量 alpha
        """
        k_idx = self.factor_names_.index(target_factor)
        D_k = self.F_[:, k_idx]
        X = np.delete(self.F_, k_idx, axis=1)
        other_names = [n for i, n in enumerate(self.factor_names_) if i != k_idx]

        # O4.9.6: Y 标准化 (惰性初始化, 兼容直接注入 F_/y_ 的测试场景)
        if self.y_normalized_ is None:
            y_mean = float(self.y_.mean())
            y_std = float(self.y_.std())
            if y_std > 1e-12:
                self.y_normalized_ = (self.y_ - y_mean) / y_std
            else:
                self.y_normalized_ = self.y_.copy()

        # Stage 1: Lasso y ~ X → S_Y (用标准化 Y, O4.9.6)
        lasso_y = self._make_lasso().fit(X, self.y_normalized_)
        # O4.9.5: 收敛检测
        self._check_convergence(lasso_y, stage=1)
        S_Y = set(np.where(lasso_y.coef_ != 0)[0])

        # Stage 2: Lasso D_k ~ X → S_D (D_k 不需标准化, 与 X 同尺度)
        lasso_d = self._make_lasso().fit(X, D_k)
        self._check_convergence(lasso_d, stage=2)
        S_D = set(np.where(lasso_d.coef_ != 0)[0])

        # Stage 3: OLS y ~ D_k + X_{S_Y ∪ S_D} + intercept (O4.9.1 加截距列)
        selected = sorted(S_Y | S_D)
        n = len(self.y_)
        if selected:
            X_selected = X[:, selected]
            # O4.9.1: 加截距列
            X_final = np.column_stack([D_k, X_selected, np.ones(n)])
        else:
            # S_D = ∅ 兜底
            X_final = np.column_stack([D_k, np.ones(n)])

        # OLS 求解 (用原始 Y, 保持系数可解释性, O4.9.6)
        beta = np.linalg.lstsq(X_final, self.y_, rcond=None)[0]
        # D_k 是第 0 个系数, 截距是最后一个
        coef = float(beta[0])

        # 标准误 (O4.9.2: HC3 默认)
        std_err = self._compute_standard_error(
            X_final, self.y_, beta, self.std_error_type
        )[0]
        std_err = float(std_err)

        # t 检验
        t_stat = coef / std_err if std_err > 0 else 0.0
        # 自由度 = n - p
        p = X_final.shape[1]
        df = max(n - p, 1)
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=df))

        # 置信区间 (1.96 近似, 大样本下与 t 分布接近)
        ci_lower = coef - 1.96 * std_err
        ci_upper = coef + 1.96 * std_err

        result = {
            'factor': target_factor,
            'coefficient': coef,
            'std_error': std_err,
            't_statistic': float(t_stat),
            'p_value': float(p_value),
            'ci_lower': float(ci_lower),
            'ci_upper': float(ci_upper),
            'selected_controls': [other_names[i] for i in selected],
            'is_significant': bool(p_value < self.alpha),
        }

        # O4.9.7: S_D 空集诊断
        if not selected:
            result['diagnostic'] = {
                'stage1_zero_coefs': len(S_Y) == 0,
                'stage2_zero_coefs': len(S_D) == 0,
                'interpretation': (
                    'Y 与控制变量无显著相关 (Stage 1 全零), '
                    'D_k 与控制变量无显著相关 (Stage 2 全零). '
                    'D_k 系数为单变量 OLS 估计, 缺乏混淆变量控制, 谨慎解读.'
                ),
                'recommendation': (
                    '若 D_k 是已知独立因子, 结果可信; '
                    '若 D_k 与其他因子应有相关, 检查数据对齐或增大样本.'
                ),
            }

        return result

    def _elastic_net_path(self, target_factor: str) -> Dict:
        """Elastic Net 路径分析 (系数稳定性)

        在不同 l1_ratio 下检查因子系数稳定性
        """
        k_idx = self.factor_names_.index(target_factor)
        D_k = self.F_[:, k_idx]
        X = np.delete(self.F_, k_idx, axis=1)
        X_full = np.column_stack([D_k, X])

        enet = ElasticNetCV(
            l1_ratio=[0.5, 0.7, 0.9],
            cv=self.cv_folds,
            max_iter=self.max_iter,
            n_jobs=self._lasso_n_jobs,
        )
        enet.fit(X_full, self.y_normalized_)

        coef = float(enet.coef_[0])
        stability = 'stable' if abs(coef) > 0.01 else 'weak'
        return {
            'factor': target_factor,
            'coefficient': coef,
            'optimal_alpha': float(enet.alpha_),
            'optimal_l1_ratio': float(enet.l1_ratio_),
            'stability': stability,
            'is_significant': bool(abs(coef) > 0.01),
        }

    # ── 辅助方法 ──────────────────────────────────

    def _make_lasso(self) -> LassoCV:
        """O4.9.5: 构造 LassoCV, 暴露 eps + lasso_params"""
        params = {
            'cv': self.cv_folds,
            'max_iter': self.max_iter,
            'eps': self.eps,
            'n_jobs': self._lasso_n_jobs,
            **self.lasso_params,
        }
        return LassoCV(**params)

    def _check_convergence(self, lasso: LassoCV, stage: int) -> None:
        """O4.9.5: 检测 n_iter_ 接近 max_iter 时告警"""
        if hasattr(lasso, 'n_iter_'):
            n_iter = lasso.n_iter_
            # n_iter_ 可能是数组 (per CV fold) 或标量
            if isinstance(n_iter, np.ndarray):
                n_iter_max = int(np.max(n_iter))
            else:
                n_iter_max = int(n_iter)
            if n_iter_max >= self.max_iter * 0.9:
                warnings.warn(
                    f"Stage {stage} LassoCV 接近 max_iter "
                    f"({n_iter_max}/{self.max_iter}), "
                    f"可能未收敛, 建议增大 max_iter 或检查共线性",
                    UserWarning,
                    stacklevel=3,
                )

    def _compute_standard_error(
        self,
        X: np.ndarray,
        y: np.ndarray,
        beta: np.ndarray,
        std_error_type: str = 'hc3',
    ) -> np.ndarray:
        """O4.9.2: 计算标准误

        Args:
            X: (n, p) 设计矩阵 (含截距列)
            y: (n,) 因变量
            beta: (p,) OLS 系数
            std_error_type: 'ols' / 'hc1' / 'hc3'

        Returns: (p,) 标准误数组
        """
        n, p = X.shape
        residuals = y - X @ beta
        XtX_inv = np.linalg.inv(X.T @ X)

        if std_error_type == 'ols':
            # 同方差假设
            sigma2 = np.sum(residuals ** 2) / (n - p)
            cov = sigma2 * XtX_inv
        elif std_error_type == 'hc1':
            # HC1: 自由度调整的 White 稳健
            meat = (X * residuals[:, None]).T @ (X * residuals[:, None])
            cov = XtX_inv @ meat @ XtX_inv * (n / (n - p))
        elif std_error_type == 'hc3':
            # HC3: MacKinnon-White 1985, 对杠杆点更稳健
            # 公式: cov = (XtX)^-1 @ X^T @ diag(e_i^2 / (1-h_i)^2) @ X @ (XtX)^-1
            # h_i = x_i^T (X^T X)^(-1) x_i (leverage)
            h = np.sum((X @ XtX_inv) * X, axis=1)
            # 避免除零 (h_i 接近 1)
            denom = np.maximum(1 - h, 1e-10)
            # 修正 (v1.2): w_i = e_i^2 / (1-h_i)^2 (非 e_i / (1-h_i)^2)
            w = residuals ** 2 / (denom ** 2)
            meat = (X * w[:, None]).T @ X
            cov = XtX_inv @ meat @ XtX_inv
        else:
            raise ValueError(
                f"未知 std_error_type: {std_error_type}, "
                f"支持 'ols'/'hc1'/'hc3'"
            )

        # 防御性 clip: 正确公式下 cov 应为 PSD (对角线 >= 0),
        # 极端数值误差可能产生微小负值, clip 到非负 (与 statsmodels 一致)
        diag = np.maximum(np.diag(cov), 0.0)
        return np.sqrt(diag)

    def _apply_correction(
        self,
        results: Dict[str, Dict],
        correction: str,
    ) -> Dict[str, Dict]:
        """O4.9.3: 多重检验校正

        Args:
            results: {name: result_dict}
            correction: 'none' / 'bonferroni' / 'benjamini_hochberg' / 'holm'
        """
        if correction == 'none':
            # 不校正, 但仍标记 correction_method
            for r in results.values():
                r['correction_method'] = 'none'
            return results

        p_values = np.array([r['p_value'] for r in results.values()])
        K = len(p_values)

        if correction == 'bonferroni':
            # T3.5: 调用共享模块 (向后兼容, fallback 到内联)
            if _HAS_MULTIPLE_TESTING:
                p_adj_list, _ = apply_bonferroni(p_values.tolist(), alpha=self.alpha)
                p_adj = np.array(p_adj_list)
            else:
                p_adj = np.minimum(p_values * K, 1.0)
        elif correction == 'benjamini_hochberg':
            # T3.5: 调用共享模块 (向后兼容, fallback 到内联)
            if _HAS_MULTIPLE_TESTING:
                p_adj_list, _ = apply_bh_fdr(p_values.tolist(), alpha=self.alpha)
                p_adj = np.array(p_adj_list)
            else:
                order = np.argsort(p_values)
                p_adj = np.empty_like(p_values)
                prev = 1.0
                for i in range(K - 1, -1, -1):
                    rank = i + 1
                    idx = order[i]
                    bh = p_values[idx] * K / rank
                    prev = min(prev, bh)
                    p_adj[idx] = min(prev, 1.0)
        elif correction == 'holm':
            # Holm: 逐步 Bonferroni (从小到大, p * (K - i))
            order = np.argsort(p_values)
            p_adj = np.empty_like(p_values)
            prev = 0.0
            for i in range(K):
                idx = order[i]
                holm = p_values[idx] * (K - i)
                prev = max(prev, holm)
                p_adj[idx] = min(prev, 1.0)
        else:
            raise ValueError(
                f"未知 correction: {correction}, "
                f"支持 'none'/'bonferroni'/'benjamini_hochberg'/'holm'"
            )

        # 回填
        for name, p_a in zip(results.keys(), p_adj):
            results[name]['p_value_adjusted'] = float(p_a)
            results[name]['is_significant_adjusted'] = bool(p_a < self.alpha)
            results[name]['correction_method'] = correction

        return results

    def _stack_factor_returns(
        self,
        factor_dict: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        factor_names: List[str],
    ) -> Tuple[np.ndarray, np.ndarray, pd.Index, pd.Index]:
        """堆叠因子和收益为 (N·T, K) 和 (N·T,)

        步骤:
        1. 对齐日期 (因子 columns ∩ fwd_returns index)
        2. 对齐股票 (因子 index ∩ fwd_returns columns)
        3. 堆叠为 (N·T, K) 因子矩阵 + (N·T,) 收益向量
        """
        # 1. 对齐日期
        # factor_dict[name]: (N, T), columns 是日期
        # fwd_returns: (T, N), index 是日期
        factor_dates = factor_dict[factor_names[0]].columns
        return_dates = fwd_returns.index
        common_dates = factor_dates.intersection(return_dates)
        if len(common_dates) == 0:
            raise ValueError(
                "因子日期与收益日期无交集, 无法对齐"
            )

        # 2. 对齐股票
        factor_stocks = factor_dict[factor_names[0]].index
        return_stocks = fwd_returns.columns
        common_stocks = factor_stocks.intersection(return_stocks)
        if len(common_stocks) == 0:
            raise ValueError(
                "因子股票与收益股票无交集, 无法对齐"
            )

        # 3. 堆叠
        T = len(common_dates)
        N = len(common_stocks)
        K = len(factor_names)
        F_stacked = np.zeros((N * T, K))

        for k, name in enumerate(factor_names):
            df = factor_dict[name].loc[common_stocks, common_dates]
            # df: (N, T), 按 (T, N) 顺序堆叠 → (N·T,)
            F_stacked[:, k] = df.values.T.flatten()

        # fwd_returns: (T, N) → (N·T,)
        y_stacked = fwd_returns.loc[common_dates, common_stocks].values.flatten()

        return F_stacked, y_stacked, common_dates, common_stocks

    # ── v3.1.0 E5 L2: 威胁分层显著性 (opt-in, 不替换 double_lasso) ──

    def threat_layered_alpha(
        self,
        threat_taus: Dict[str, float],
        alpha_base: float = 0.05,
        gamma: float = 0.5,
    ) -> Dict[str, float]:
        """分层显著性阈值 (v3.1.0 E5 L2).

        数学: α_i = α_base × (1 - γ × τ_i)

        与 BH-FDR 协同:
        1. 先按内生性威胁分层 (高/中/低)
        2. 每层内独立做 BH-FDR 校正
        3. 跨层合并, 高威胁层 q-value 乘以惩罚因子

        Args:
            threat_taus: 各因子的内生性威胁等级 {factor_name: τ ∈ [0,1]}
            alpha_base: 基础显著性水平 (默认 0.05)
            gamma: 正则化强度 (默认 0.5)

        Returns:
            {factor_name: adjusted_alpha}
        """
        result = {}
        for factor_name, tau in threat_taus.items():
            alpha_i = alpha_base * (1.0 - gamma * tau)
            result[factor_name] = float(max(alpha_i, 0.001))  # 下限保护
        return result

    def threat_layered_bh_fdr(
        self,
        p_values: Dict[str, float],
        threat_taus: Dict[str, float],
        alpha_base: float = 0.05,
        gamma: float = 0.5,
    ) -> Dict[str, Dict[str, Any]]:
        """分层 BH-FDR (L2 + L3 协同, v3.1.0 E5).

        1. 按 τ 分层 (低 < 0.3, 中 0.3-0.7, 高 ≥ 0.7)
        2. 每层内做 BH-FDR
        3. 高威胁层 q-value 乘以惩罚因子 (1 - γ × τ_mean)

        统计性质说明 (分层 BH-FDR):
        - 分层 BH-FDR 在每层内独立控制 FDR (层内 FDR ≤ alpha_base).
        - 全局 FDR 控制需要额外条件: 若层间检验独立, 全局 FDR ≤ alpha_base;
          若层间不独立, 全局 FDR 可能超过 alpha_base, 需加权补偿 (此处用
          penalty_factor = 1 - γ × τ_mean 对高威胁层额外收紧以补偿层间相关性).
        - 跨层惩罚 (L3) 同时起到缓解层间相关性导致的全局 FDR 膨胀的作用.
        """
        # 分层
        layers: Dict[str, Dict[str, float]] = {'low': {}, 'medium': {}, 'high': {}}
        for factor, tau in threat_taus.items():
            if tau < 0.3:
                layers['low'][factor] = p_values.get(factor, 1.0)
            elif tau < 0.7:
                layers['medium'][factor] = p_values.get(factor, 1.0)
            else:
                layers['high'][factor] = p_values.get(factor, 1.0)

        # 层内 BH-FDR + 跨层惩罚
        result: Dict[str, Dict[str, Any]] = {}
        for layer_name, layer_pvals in layers.items():
            if not layer_pvals:
                continue
            factors = list(layer_pvals.keys())
            p_list = [layer_pvals[f] for f in factors]

            # apply_bh_fdr 返回 Tuple[List[float], List[bool]] = (p_adj, is_significant)
            if _HAS_MULTIPLE_TESTING:
                p_adj, is_significant = apply_bh_fdr(p_list, alpha=alpha_base)
            else:
                # 内联 BH-FDR (fallback)
                p_adj, is_significant = self._inline_bh_fdr(p_list, alpha_base)

            # 跨层惩罚: 高威胁层 q-value 乘以 (1 - γ × τ_mean)
            taus_layer = [threat_taus[f] for f in factors]
            tau_mean = sum(taus_layer) / len(taus_layer) if taus_layer else 0.0
            penalty_factor = 1.0 - gamma * tau_mean

            for i, factor in enumerate(factors):
                adjusted_p_penalized = p_adj[i] * penalty_factor
                result[factor] = {
                    'adjusted_p': float(adjusted_p_penalized),
                    'rejected': bool(
                        is_significant[i]
                        and (adjusted_p_penalized < alpha_base)
                    ),
                    'layer': layer_name,
                    'tau': float(threat_taus[factor]),
                    'penalty_factor': float(penalty_factor),
                }
        return result

    @staticmethod
    def _inline_bh_fdr(
        p_values: List[float],
        alpha: float = 0.05,
    ) -> Tuple[List[float], List[bool]]:
        """内联 BH-FDR (fallback, 当 multiple_testing 模块不可用时)."""
        K = len(p_values)
        if K == 0:
            return [], []
        p_arr = np.asarray(p_values, dtype=float)
        order = np.argsort(p_arr)
        p_adj = np.empty_like(p_arr)
        prev = 1.0
        for i in range(K - 1, -1, -1):
            rank = i + 1
            idx = order[i]
            bh = p_arr[idx] * K / rank
            prev = min(prev, bh)
            p_adj[idx] = min(prev, 1.0)
        # 判定: 找到最大 k* 使 p_adj_(k*) <= alpha
        is_sig = [bool(pa <= alpha) for pa in p_adj]
        return p_adj.tolist(), is_sig
