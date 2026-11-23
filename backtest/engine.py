# -*- coding: utf-8 -*-
"""
因子回测引擎 — FactorBacktestEngine

基于 DataLoaderV3 的因子级回测评估。
使用 factor_metrics.py 作为所有指标计算的单一真相源。

核心职责:
  - 接收 DataLoaderV3 (经 data_bridge 适配后的 Pipeline 输出)
  - 计算前向收益率
  - 对每个因子计算: IC 序列、ICIR、IC Decay、Hit Rate、换手率、多空收益、Spread
  - 返回结构化结果

设计原则:
  - 本模块不重复实现任何指标计算逻辑，所有计算委托给 factor_metrics.py
  - 纯 numpy 操作，避免 pandas 开销
  - 无副作用，结果可复现
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from .factor_metrics import (
    compute_rank_ic,
    compute_pearson_ic,
    compute_ic_series,
    compute_icir,
    compute_ic_decay,
    compute_hit_rate,
    compute_turnover,
    compute_long_short_returns,
    compute_spread,
)
from .tradability import apply_tradability

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG = {
    'top_n': 0.2,           # 多空选股比例 (float) 或固定数量 (int)
    'ls_method': 'top_n',   # 'top_n' | 'equal_weight'
    'ic_method': 'rank',    # 'rank' | 'pearson'
    'max_lag': 12,          # IC Decay 最大滞后
}


class FactorBacktestEngine:
    """因子回测引擎。

    使用 factor_metrics.py 作为指标计算的单一真相源。

    Usage:
        dl = data_bridge.create_dataloader(processed_factors, price_data)
        engine = FactorBacktestEngine(dl, config={'top_n': 0.2})
        results = engine.run()
        ranking = engine.rank_by_icir()
    """

    def __init__(
        self,
        data_loader,
        config: Optional[Dict[str, Any]] = None,
        fwd_returns: Optional[np.ndarray] = None,
        tradability_inputs=None,
    ):
        """初始化因子回测引擎。

        Args:
            data_loader: DataLoaderV3 实例 (经 data_bridge 适配)
            config: 配置字典，覆盖默认值
            fwd_returns: 预计算的前向收益率，shape (n_dates - 1, n_stocks)。
                         若为 None，引擎内部自动计算。
                         用于多引擎共享前向收益，避免重复计算。
            tradability_inputs: 可选 TradabilityInputs；None 时旧路径逐位不变。

        Raises:
            ValueError: 因子数据为空时，或 fwd_returns 形状不匹配时
        """
        self.dl = data_loader
        self.n_dates = data_loader.n_dates
        self.n_stocks = data_loader.n_stocks

        # 因子名称列表
        self.factor_names = list(data_loader.factor_data.keys())
        if not self.factor_names:
            # P1: 空因子场景 (所有因子被 min_dates 过滤跳过)
            # 不抛异常,run() 将返回空 dict,让上层决定如何处理
            logger.warning(
                "FactorBacktestEngine: DataLoaderV3 中无因子数据 "
                "(可能全部被 min_dates 过滤),run() 将返回空结果"
            )

        # 配置合并
        self.config = {**DEFAULT_CONFIG, **(config or {})}

        # 提取 numpy 数组 (shape: n_dates × n_stocks)
        self._close = data_loader.price_data['close']

        # 可选可交易性输入（P-006）；None → 旧路径逐位不变
        self._tradability_inputs = tradability_inputs
        if tradability_inputs is not None:
            self._validate_tradability_inputs(tradability_inputs)

        # 缓存
        self._fwd_returns: Optional[np.ndarray] = None
        self._results: Optional[Dict[str, Dict[str, Any]]] = None

        # 验证并存储预计算的前向收益
        if fwd_returns is not None:
            if fwd_returns.shape != (self.n_dates - 1, self.n_stocks):
                raise ValueError(
                    f"fwd_returns 形状不匹配: 期望 ({self.n_dates - 1}, {self.n_stocks}), "
                    f"实际 {fwd_returns.shape}"
                )
            self._fwd_returns = fwd_returns

        logger.info(
            f"FactorBacktestEngine 初始化: "
            f"{self.n_dates} 天 × {self.n_stocks} 股票, "
            f"{len(self.factor_names)} 个因子"
            f"{', 使用预计算 fwd_returns' if fwd_returns is not None else ''}"
        )

    # ── 前向收益 ──────────────────────────────────

    def _validate_tradability_inputs(self, inputs) -> None:
        """OPT-IN 输入形状校验（P-006 DESIGN §4.5 / §7）。"""
        expected = (self.n_dates, self.n_stocks)
        for field in ("close", "high", "low", "open_", "volume",
                      "suspended", "is_st"):
            shape = np.shape(getattr(inputs, field, None))
            if shape != expected:
                raise ValueError(
                    f"tradability_inputs.{field} 形状应为 {expected} "
                    f"(实际 {shape})")
        if inputs.adj is None:
            raise ValueError(
                "tradability 需要 adj（判定需除权参考价基准）")
        if np.shape(inputs.adj) != expected:
            raise ValueError(
                f"tradability_inputs.adj 形状应为 {expected} "
                f"(实际 {np.shape(inputs.adj)})")
        if np.shape(inputs.dates) != (self.n_dates,):
            raise ValueError(
                f"tradability_inputs.dates 形状应为 {(self.n_dates,)} "
                f"(实际 {np.shape(inputs.dates)})")
        if np.shape(inputs.board) != (self.n_stocks,):
            raise ValueError(
                f"tradability_inputs.board 形状应为 {(self.n_stocks,)} "
                f"(实际 {np.shape(inputs.board)})")
        for field in ("is_delisting", "no_limit"):
            value = getattr(inputs, field)
            if value is not None and np.shape(value) != expected:
                raise ValueError(
                    f"tradability_inputs.{field} 形状应为 {expected} "
                    f"(实际 {np.shape(value)})")

    def compute_fwd_returns(self) -> np.ndarray:
        """公开方法: 计算前向收益率 (供外部预计算和共享)。

        Returns:
            np.ndarray, shape (n_dates - 1, n_stocks)
        """
        return self._compute_fwd_returns()

    def _compute_fwd_returns(self) -> np.ndarray:
        """计算前向收益率。

        fwd_ret[t] = (close[t+1] - close[t]) / close[t]

        Returns:
            np.ndarray, shape (n_dates - 1, n_stocks)
        """
        if self._fwd_returns is not None:
            return self._fwd_returns

        # close shape: (n_dates, n_stocks)
        close = self._close
        fwd = np.full((self.n_dates - 1, self.n_stocks), np.nan)

        for t in range(self.n_dates - 1):
            prev = close[t]
            curr = close[t + 1]
            valid = (prev > 1e-10) & (~np.isnan(prev)) & (~np.isnan(curr))
            fwd[t, valid] = (curr[valid] - prev[valid]) / prev[valid]

        self._fwd_returns = fwd
        return fwd

    # ── 仓位构建 ──────────────────────────────────

    def _build_positions(self, factor: np.ndarray) -> np.ndarray:
        """根据因子值构建仓位矩阵。

        Args:
            factor: np.ndarray, shape (n_dates, n_stocks)

        Returns:
            np.ndarray, shape (n_dates, n_stocks)
        """
        n_dates, n_stocks = factor.shape
        positions = np.zeros((n_dates, n_stocks))
        ls_method = self.config.get('ls_method', 'top_n')
        top_n = self.config.get('top_n', 0.2)

        for t in range(n_dates):
            f = factor[t]
            valid = ~np.isnan(f)
            valid_idx = np.flatnonzero(valid)
            n_valid = valid.sum()

            if n_valid < 3:
                continue

            if ls_method == 'equal_weight':
                signs = np.sign(f)
                signs[~valid] = 0.0
                total_abs = np.sum(np.abs(signs))
                if total_abs > 0:
                    positions[t] = signs / total_abs

            elif ls_method == 'top_n':
                # 确定选股数量
                if isinstance(top_n, float) and 0 < top_n <= 0.5:
                    n_select = max(1, int(n_valid * top_n))
                elif isinstance(top_n, int) and top_n > 0:
                    n_select = min(top_n, n_valid // 2)
                else:
                    n_select = max(1, int(n_valid * 0.2))

                if n_select < 1 or n_valid < n_select * 2:
                    continue

                sorted_local = valid_idx[np.argsort(f[valid_idx])]
                # bottom N → short
                positions[t, sorted_local[:n_select]] = -1.0 / n_select
                # top N → long
                positions[t, sorted_local[-n_select:]] = 1.0 / n_select

        return positions

    # ── 单因子评估 ──────────────────────────────────

    def _evaluate_factor(self, factor_name: str) -> Dict[str, Any]:
        """评估单个因子。

        Args:
            factor_name: 因子名称

        Returns:
            指标字典
        """
        factor = self.dl.factor_data[factor_name]  # (n_dates, n_stocks)
        fwd_ret = self._compute_fwd_returns()       # (n_dates - 1, n_stocks)

        # 转置为 factor_metrics 期望的格式: (n_stocks, n_periods)
        factor_t = factor.T   # (n_stocks, n_dates)
        fwd_ret_t = fwd_ret.T  # (n_stocks, n_dates - 1)

        # compute_ic_series 约定: factor[:, t] 对应 returns[:, t+1]
        # returns[:, 0] 是填充位（未使用），returns[:, 1] = fwd_ret[:, 0]
        # 因此需要在 fwd_ret_t 前插入一列 NaN
        padding = np.full((fwd_ret_t.shape[0], 1), np.nan)
        fwd_ret_t = np.hstack([padding, fwd_ret_t])  # (n_stocks, n_dates)

        # Rank IC 系列
        rank_ic_series = compute_ic_series(factor_t, fwd_ret_t, method='rank')
        rank_icir = compute_icir(rank_ic_series)

        # Pearson IC 系列
        pearson_ic_series = compute_ic_series(factor_t, fwd_ret_t, method='pearson')
        pearson_icir = compute_icir(pearson_ic_series)

        # IC Decay
        max_lag = self.config.get('max_lag', 12)
        ic_decay = compute_ic_decay(factor_t, fwd_ret_t, max_lag=max_lag)

        # Hit Rate
        hit_rate = compute_hit_rate(rank_ic_series)

        # 换手率（启用 tradability 时对多头腿推进，空头腿原样透传）
        positions = self._build_positions(factor)
        tradability_block = None
        if self._tradability_inputs is None:
            turnover = compute_turnover(positions)
        else:
            inputs = self._tradability_inputs
            prev_close = np.full((self.n_dates, self.n_stocks), np.nan)
            if self.n_dates > 1:
                prev_close[1:] = inputs.close[:-1]
            effective_long, report = apply_tradability(
                np.clip(positions, 0.0, None),
                prev_close, inputs.high, inputs.low, inputs.close,
                inputs.open_, inputs.volume, inputs.suspended, inputs.board,
                inputs.is_st, inputs.dates, policy=inputs.policy,
                adj=inputs.adj, is_delisting=inputs.is_delisting,
                no_limit=inputs.no_limit)
            effective = effective_long + np.minimum(positions, 0.0)
            turnover = compute_turnover(effective)
            tradability_block = {
                'report': report,
                'meta': inputs.meta,
                'price_basis': 'raw_adj_ref',
                'leg_scope': 'long_only',
                'short_leg_unmodeled': True,
                'turnover_basis': 'effective_long_only',
            }

        # 多空收益
        top_n = self.config.get('top_n', 0.2)
        ls_returns = compute_long_short_returns(factor_t, fwd_ret_t, top_n=top_n)

        # Spread
        spread = compute_spread(ls_returns)

        result = {
            'rank_ic_series': rank_ic_series,
            'rank_icir': rank_icir,
            'pearson_ic_series': pearson_ic_series,
            'pearson_icir': pearson_icir,
            'ic_decay': ic_decay,
            'hit_rate': hit_rate,
            'turnover': turnover,
            'long_short_returns': ls_returns,
            'spread': spread,
        }
        if tradability_block is not None:
            result['tradability'] = tradability_block
        return result

    # ── 运行 ──────────────────────────────────

    def run(self) -> Dict[str, Dict[str, Any]]:
        """运行因子回测，评估所有因子。

        Returns:
            {factor_name: {metric_name: value, ...}, ...}
        """
        if self._results is not None:
            return self._results

        # P1: 空因子场景直接返回空 dict
        if not self.factor_names:
            logger.info("无因子可评估,返回空结果")
            self._results = {}
            return self._results

        logger.info(f"开始评估 {len(self.factor_names)} 个因子...")

        results = {}
        for name in self.factor_names:
            logger.debug(f"  评估因子: {name}")
            results[name] = self._evaluate_factor(name)

        self._results = results
        logger.info(
            f"因子评估完成: {len(results)} 个因子, "
            f"每个因子 {len(results[self.factor_names[0]])} 个指标"
        )

        return results

    # ── 因子排序 ──────────────────────────────────

    def rank_by_icir(self) -> List[str]:
        """按 Rank ICIR 降序排列因子。

        Returns:
            因子名称列表，按 ICIR 从高到低
        """
        results = self.run()
        icirs = {}
        for name, metrics in results.items():
            icir = metrics['rank_icir']
            icirs[name] = icir if not np.isnan(icir) else -np.inf

        return sorted(icirs, key=icirs.get, reverse=True)

    # ── 摘要 ──────────────────────────────────

    def summary(self) -> Dict[str, Dict[str, float]]:
        """返回因子评估摘要 (仅标量指标)。

        Returns:
            {factor_name: {metric: value, ...}, ...}
        """
        results = self.run()
        summary = {}
        scalar_keys = ['rank_icir', 'pearson_icir', 'hit_rate', 'spread']

        for name, metrics in results.items():
            summary[name] = {k: metrics[k] for k in scalar_keys if k in metrics}
            # 添加 mean IC
            ic = metrics['rank_ic_series']
            summary[name]['mean_rank_ic'] = float(np.nanmean(ic))

        return summary