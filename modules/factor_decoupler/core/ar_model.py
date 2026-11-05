# -*- coding: utf-8 -*-
"""
AR模型与阶数选择器

基于信息准则（AIC/BIC/HQIC）自动选择最优AR阶数。
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
from dataclasses import dataclass
import logging

# v3.1.0 E1 (§2): 隐藏效应诊断 Mixin (不侵入 fit/transform).
# 局部导入避免循环依赖 — diagnostics 包仅依赖 numpy/pandas/scipy.
from factor_pipeline.modules.factor_decoupler.diagnostics.hidden_effect import (
    HiddenEffectDiagnosticMixin as _HiddenEffectDiagnosticMixin,
)

logger = logging.getLogger(__name__)


# ARModelResult.coefficients 布局约定 (由 _fit_ar 保证 — 该函数在列首插入 np.ones):
#     coefficients = [intercept, phi_1, phi_2, ..., phi_p]
# 所有提取 φ 的代码必须经 ARDecoupler._get_ar_phi_for_diagnosis(), 不得硬编码索引.
# ADR-030: 该布局的 dataclass 注释曾写成"截距末位", 与实现相反 ——
#          照注释改代码会静默取到错误的 φ, 因此用具名常量 + 布局钉子测试锁死真值.
AR_COEF_INTERCEPT_INDEX = 0
AR_COEF_PHI1_INDEX = 1


@dataclass
class ARModelResult:
    """AR模型拟合结果"""
    order: int              # 选定的AR阶数
    coefficients: np.ndarray  # OLS 系数 [intercept, phi_1, ..., phi_p] — 常数项在前, 见 _fit_ar
    residuals: pd.Series    # 残差
    fitted_values: pd.Series # 拟合值
    aic: float              # AIC
    bic: float              # BIC
    hqic: float            # HQIC
    r_squared: float        # R²
    sigma2: float           # 残差方差
    log_likelihood: float   # 对数似然


class AROrderSelector:
    """
    AR阶数选择器

    基于信息准则（AIC/BIC/HQIC）自动选择最优AR阶数。
    支持多只股票并行选择。

    Usage:
        selector = AROrderSelector(max_order=5, criterion='aic')
        results = selector.fit(series)
        print(f"最优阶数: {results.order}")
        print(f"AIC: {results.aic:.4f}")
    """

    def __init__(self,
                 max_order: int = 5,
                 min_order: int = 1,
                 criterion: str = 'aic',
                 min_obs: int = 20):
        self.max_order = max_order
        self.min_order = min_order
        self.criterion = criterion.lower()
        self.min_obs = min_obs

        self._criterion_funcs = {
            'aic': self._aic,
            'bic': self._bic,
            'hqic': self._hqic,
        }

        if self.criterion not in self._criterion_funcs:
            raise ValueError(f"不支持的信息准则: {criterion}，支持: {list(self._criterion_funcs.keys())}")

    def fit(self, series: pd.Series) -> ARModelResult:
        """
        拟合并选择最优阶数 (保留 INFO 日志)

        Parameters
        ----------
        series : pd.Series
            时间序列

        Returns
        -------
        ARModelResult
            包含最优阶数和详细结果
        """
        result = self._fit_best(series)
        logger.info(
            f"AR阶数选择完成: order={result.order}, "
            f"{self.criterion.upper()}={self._get_criterion_value(result):.4f}"
        )
        return result

    def _fit_best(self, series: pd.Series) -> ARModelResult:
        """内部选阶实现 (不产生 INFO 日志), 供 warm-up 批量复用."""
        series = series.dropna()
        if len(series) < self.min_obs:
            raise ValueError(f"数据长度 {len(series)} 少于最小要求 {self.min_obs}")

        # 尝试不同阶数
        best_order = self.min_order
        best_result = None
        best_value = np.inf

        for order in range(self.min_order, self.max_order + 1):
            if len(series) <= order + 5:  # 至少需要 order + 5 个观测
                continue

            try:
                result = self._fit_ar(series, order)
                criterion_value = self._get_criterion_value(result)

                if criterion_value < best_value:
                    best_value = criterion_value
                    best_order = order
                    best_result = result

            except Exception as e:
                logger.debug(f"AR({order}) 拟合失败: {e}")
                continue

        if best_result is None:
            # 回退：使用AR(1)
            best_order = 1
            best_result = self._fit_ar(series, 1)
            logger.warning("所有AR模型拟合失败，使用AR(1)作为备选")

        best_result.order = best_order

        return best_result

    def _fit_ar(self, series: pd.Series, order: int) -> ARModelResult:
        """拟合指定阶数的 AR 模型 (v3.3.7 / ADR-041: 所有阶数统一 hold_back 样本).

        ``hold_back = max_order`` 使 AR(1)..AR(max_order) 的响应向量与估计样本
        完全一致, 满足 statsmodels ``AutoReg(hold_back=maxlag)`` 的可比性语义;
        AIC/BIC/HQIC 因此可在同一 ``n_obs`` 上比较。

        前置条件: ``series`` 已 dropna; ``order <= self.max_order``。
        """
        y = series.values
        n = len(y)
        hold_back = self.max_order              # 所有阶数共享的估计样本起点

        y_trimmed = y[hold_back:]
        n_obs = len(y_trimmed)                   # 所有阶数相同; 也 == len(residuals)
        if n_obs <= order + 5:                  # 有效样本守卫 (ADR-041)
            raise ValueError(
                f"AR({order}) 有效样本不足: n_obs={n_obs} <= order+5={order + 5} "
                f"(n={n}, hold_back={hold_back})"
            )

        # 滞后矩阵: 所有列长度均为 n_obs
        X = np.column_stack([
            y[hold_back - i:n - i] for i in range(1, order + 1)
        ])
        X = np.column_stack([np.ones(n_obs), X])

        # OLS估计
        try:
            beta = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
        except np.linalg.LinAlgError:
            raise ValueError("OLS估计失败")

        coefficients = beta
        fitted = X @ beta
        residuals = y_trimmed - fitted

        # 统计量计算
        k = len(coefficients)                    # = order + 1
        sigma2 = np.var(residuals, ddof=0)
        log_likelihood = -n_obs / 2 * (np.log(2 * np.pi * sigma2) + 1)
        r_squared = 1 - np.var(residuals) / np.var(y_trimmed) if np.var(y_trimmed) > 0 else 0

        # 信息准则 (公式不变; 仅 n_obs 口径统一)
        aic = -2 * log_likelihood + 2 * k
        bic = -2 * log_likelihood + k * np.log(n_obs)
        hqic = -2 * log_likelihood + 2 * k * np.log(np.log(n_obs))

        return ARModelResult(
            order=order,
            coefficients=coefficients,
            residuals=pd.Series(residuals, index=series.index[hold_back:]),
            fitted_values=pd.Series(fitted, index=series.index[hold_back:]),
            aic=aic,
            bic=bic,
            hqic=hqic,
            r_squared=r_squared,
            sigma2=sigma2,
            log_likelihood=log_likelihood
        )

    def _aic(self, result: ARModelResult) -> float:
        return result.aic

    def _bic(self, result: ARModelResult) -> float:
        return result.bic

    def _hqic(self, result: ARModelResult) -> float:
        return result.hqic

    def _get_criterion_value(self, result: ARModelResult) -> float:
        func = self._criterion_funcs[self.criterion]
        return func(result)

    def batch_fit(self,
                  data: pd.DataFrame) -> Dict[str, ARModelResult]:
        """
        批量拟合多个股票

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            面板数据

        Returns
        -------
        Dict[str, ARModelResult]
            股票代码到拟合结果的映射
        """
        results = {}
        for col in data.columns:
            try:
                series = data[col].dropna()
                if len(series) >= self.min_obs:
                    results[col] = self.fit(series)
            except Exception as e:
                logger.debug(f"股票 {col} 拟合失败: {e}")
                continue

        logger.info(f"批量拟合完成: {len(results)}/{len(data.columns)} 只股票成功")
        return results


# v3.3.6 (ADR-040): warm-up 内每 10 行重估一次系数.
# 对应 tsibble `.step` / sktime `step_length` / skforecast `refit=n` 的同类实践:
# 逐点重估成本约 49× 而精度改善仅约 1.6%, 间歇重估是成本-精度折中.
_WARMUP_REFIT_STRIDE = 10


class ARDecoupler(_HiddenEffectDiagnosticMixin):
    """
    AR解耦器 (v3.3.6: 三段式因果一步预测)

    对时间序列进行AR建模, 提取残差作为去相关后的新息.
    支持:
    1. 自动阶数选择 (AIC/BIC)
    2. 固定阶数
    3. 软解耦 (保留部分原始信号)

    因果性 (ADR-040):
    - ``fit`` 只用前 ``warmup_obs`` 行估计阶数与系数 (冻结模型);
    - ``transform`` 按行递推, 每个 t 只使用 ``vals[0..t]``:
      * ``t < min_order+6``: identity (冷启动, 不做解耦);
      * ``min_order+6 <= t < min_obs``: 固定 ``min_order``, 每 stride 行重估;
      * ``min_obs <= t < warmup_obs``: 全阶 AIC, 每 stride 行重估;
      * ``t >= warmup_obs``: 冻结模型一步预测 (向量化).
    - 不构造 ``fitted_values`` / 不引入 ``ffill``; NaN 经滞后自然传播.

    Usage:
        decoupler = ARDecoupler(max_order=5, criterion='aic', warmup_obs=120)
        residuals = decoupler.fit_transform(series)
    """

    def __init__(self,
                 max_order: int = 5,
                 min_order: int = 1,
                 criterion: str = 'aic',
                 strength: float = 1.0,
                 min_obs: int = 20,
                 warmup_obs: int = 120):
        self.max_order = max_order
        self.min_order = min_order
        self.criterion = criterion
        self.strength = strength  # 解耦强度 [0, 1]
        self.min_obs = min_obs
        if warmup_obs <= min_obs:
            raise ValueError(
                f"warmup_obs ({warmup_obs}) 必须大于 min_obs ({min_obs}); "
                f"建议 warmup_obs >= min_obs + 10"
            )
        self.warmup_obs = int(warmup_obs)

        self._selector = AROrderSelector(
            max_order=max_order,
            min_order=min_order,
            criterion=criterion,
            min_obs=min_obs
        )
        self._results: Dict[str, ARModelResult] = {}
        self.is_fitted = False

    def fit(self, data: pd.DataFrame) -> 'ARDecoupler':
        """
        拟合AR模型 (只用前 ``warmup_obs`` 行)

        ``warmup_obs`` 之后的数据不参与阶数选择与系数估计; 由此得到
        "冻结模型", ``transform`` 在 ``t >= warmup_obs`` 后复用它做一步预测.

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            面板数据

        Returns
        -------
        self
        """
        warm = min(self.warmup_obs, len(data))
        self._results = self._selector.batch_fit(data.iloc[:warm])
        self.is_fitted = True
        logger.info(f"AR模型拟合完成: {len(self._results)} 只股票 (窗口={warm} 行)")
        return self

    def _get_ar_phi_for_diagnosis(self) -> Optional[float]:
        """诊断契约钩子 (ADR-030): 返回拟合窗口 (前 ``warmup_obs`` 行) 的平均 AR(1) 系数 φ.

        由 ``HiddenEffectDiagnosticMixin`` 调用, 使 Mixin 无需探测本类的私有
        ``_results``。**φ 的索引假设只在此处出现一处** —— 若内部存储布局变更,
        只需改这里, 契约测试 (`TestDiagnosticContract`) 会捕获漏改。

        Returns:
            平均 φ, 或 None (无任何可用拟合结果)
        """
        if not self._results:
            return None

        phis: List[float] = []
        for res in self._results.values():
            coeffs = getattr(res, 'coefficients', None)
            if coeffs is None:
                continue
            arr = np.asarray(coeffs).flatten()
            if arr.size > AR_COEF_PHI1_INDEX:
                phis.append(float(arr[AR_COEF_PHI1_INDEX]))

        return float(np.mean(phis)) if phis else None

    @staticmethod
    def _predict_one_step(vals: np.ndarray, t: int,
                          coef: np.ndarray, p: int) -> float:
        """一步预测 c0 + Σ c_i·y_{t-i}; 滞后值含 NaN 时返回 NaN."""
        yhat = coef[0]
        for i in range(p):
            yhat += coef[i + 1] * vals[t - 1 - i]
        return float(yhat)

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        应用AR解耦 (三段式因果一步预测)

        冷启动: ``t < min_order+6`` 输出 identity;
        预热: ``[min_order+6, warmup_obs)`` 每 ``_WARMUP_REFIT_STRIDE`` 行用
        ``vals[:t]`` 重估阶数与系数 (``t < min_obs`` 时固定 ``min_order``);
        冻结: ``t >= warmup_obs`` 用 ``fit`` 的前缀模型做向量化一步预测.
        每个 t 只使用 ``vals[0..t]``; NaN 经滞后自然传播, 不引入 ``ffill``.

        Parameters
        ----------
        data : pd.DataFrame, shape (T, N)
            原始数据

        Returns
        -------
        pd.DataFrame
            解耦后的数据
        """
        if not self.is_fitted:
            raise ValueError("模型未拟合，请先调用 fit()")

        result = data.copy()
        early = max(self.min_order + 6, 2)      # AR(min_order) 最少观测数

        for col in data.columns:                 # 不以 _results 过滤 (N4)
            vals = data[col].to_numpy(dtype=float)
            n = vals.shape[0]
            res = vals.copy()                    # 冷启动 identity

            warm_end = min(self.warmup_obs, n)
            coef, p, last = None, 0, None
            for t in range(min(early, warm_end), warm_end):
                if coef is None or (t - last) >= _WARMUP_REFIT_STRIDE:
                    ser = pd.Series(vals[:t]).dropna()   # 只用前缀
                    try:
                        if len(ser) < self.min_obs:
                            r = self._selector._fit_ar(ser, self.min_order)
                        else:
                            r = self._selector._fit_best(ser)
                    except Exception as e:
                        logger.debug(f"股票 {col} warm-up t={t} 拟合失败: {e}")
                        continue
                    coef = np.asarray(r.coefficients).flatten()
                    p = r.order
                    last = t
                res[t] = vals[t] - self._predict_one_step(vals, t, coef, p)

            frozen = self._results.get(col)      # 冻结模型 (前 K 行)
            if frozen is not None and n > self.warmup_obs:
                c = np.asarray(frozen.coefficients).flatten()
                q = frozen.order
                pred = np.full(n, c[0])
                for i in range(1, q + 1):
                    pred[i:] += c[i] * vals[: n - i]   # 只在已实现的值上累加
                res[self.warmup_obs:] = (
                    vals[self.warmup_obs:] - pred[self.warmup_obs:]
                )

            result[col] = (1 - self.strength) * vals + self.strength * res

        return result

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """拟合并变换"""
        return self.fit(data).transform(data)

    def get_residual_stats(self) -> Dict[str, Dict[str, float]]:
        """
        获取残差统计量

        Returns
        -------
        Dict[str, Dict[str, float]]
            每只股票的残差统计量
        """
        if not self._results:
            return {}

        stats = {}
        for stock, result in self._results.items():
            residuals = result.residuals.dropna()
            if len(residuals) > 0:
                stats[stock] = {
                    'mean': float(residuals.mean()),
                    'std': float(residuals.std()),
                    'skewness': float(residuals.skew()),
                    'kurtosis': float(residuals.kurtosis()),
                }
        return stats

    def get_summary(self) -> pd.DataFrame:
        """
        获取模型摘要

        Returns
        -------
        pd.DataFrame
            包含阶数、系数、AIC/BIC等
        """
        if not self._results:
            return pd.DataFrame()

        rows = []
        for stock, result in self._results.items():
            row = {
                'stock': stock,
                'ar_order': result.order,
                'r_squared': result.r_squared,
                'aic': result.aic,
                'bic': result.bic,
                'sigma2': result.sigma2,
            }
            for i, coef in enumerate(result.coefficients[1:], 1):  # 跳过截距
                row[f'phi_{i}'] = coef
            rows.append(row)

        return pd.DataFrame(rows).set_index('stock')
