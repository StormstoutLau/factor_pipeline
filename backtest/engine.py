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
from .tradability import (apply_tradability_with_diagnostics,
                          TradabilityApplyState)

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
        tradability_plan=None,
    ):
        """初始化因子回测引擎。

        Args:
            data_loader: DataLoaderV3 实例 (经 data_bridge 适配)
            config: 配置字典，覆盖默认值
            fwd_returns: 预计算的前向收益率，shape (n_dates - 1, n_stocks)。
                         若为 None，引擎内部自动计算。
                         用于多引擎共享前向收益，避免重复计算。
            tradability_inputs: 可选 TradabilityInputs；None 时旧路径逐位不变。
            tradability_plan: 可选 TradabilityPlan（P-023 流式路径）；与
                tradability_inputs 互斥。

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

        # P-023 流式 plan（互斥；None → 旧路径逐位不变）
        if tradability_plan is not None and tradability_inputs is not None:
            raise ValueError(
                "tradability_inputs 与 tradability_plan 不能同时提供")
        self._tradability_plan = tradability_plan
        if tradability_plan is not None:
            self._validate_tradability_plan(tradability_plan)

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
        if inputs.adj is None and getattr(inputs, "ref", None) is None:
            raise ValueError(
                "tradability 需要 adj 或 ref（判定需除权参考价基准）")
        if inputs.adj is not None and np.shape(inputs.adj) != expected:
            raise ValueError(
                f"tradability_inputs.adj 形状应为 {expected} "
                f"(实际 {np.shape(inputs.adj)})")
        ref = getattr(inputs, "ref", None)
        if ref is not None and np.shape(ref) != expected:
            raise ValueError(
                f"tradability_inputs.ref 形状应为 {expected} "
                f"(实际 {np.shape(ref)})")
        limit_up = getattr(inputs, "limit_up", None)
        limit_down = getattr(inputs, "limit_down", None)
        if (limit_up is None) != (limit_down is None):
            raise ValueError("tradability_inputs.limit_up/limit_down 必须成对")
        for field in ("limit_up", "limit_down"):
            value = getattr(inputs, field, None)
            if value is not None and np.shape(value) != expected:
                raise ValueError(
                    f"tradability_inputs.{field} 形状应为 {expected} "
                    f"(实际 {np.shape(value)})")
        codes = getattr(inputs, "codes", None)
        if codes is not None:
            if np.shape(codes) != (self.n_stocks,):
                raise ValueError(
                    f"tradability_inputs.codes 形状应为 {(self.n_stocks,)} "
                    f"(实际 {np.shape(codes)})")
            if len(set(map(str, np.asarray(codes).tolist()))) != self.n_stocks:
                raise ValueError("tradability_inputs.codes 含重复代码")
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

    def _validate_tradability_plan(self, plan) -> None:
        """P-023 流式 plan 形状/mode 校验。"""
        n_dates = len(getattr(plan, "index", ()))
        n_codes = len(getattr(plan, "codes", ()))
        if n_dates != self.n_dates or n_codes != self.n_stocks:
            raise ValueError(
                f"tradability_plan 形状应为 ({self.n_dates}, {self.n_stocks})"
                f" (实际 ({n_dates}, {n_codes}))")
        if getattr(plan, "mode", None) not in (
                "full", "execution_only_open", "off"):
            raise ValueError(
                f"tradability_plan.mode 非法: {getattr(plan, 'mode', None)!r}")

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
        if self._tradability_plan is not None:
            return self._evaluate_factor_streaming(factor_name)
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
        inputs = self._tradability_inputs
        policy_mode = getattr(getattr(inputs, "policy", None), "mode", None)
        if inputs is None or policy_mode == "off":
            # mode=off 视同未启用：不挂块、走旧 turnover 路径（INV-13）
            turnover = compute_turnover(positions)
        else:
            prev_close = np.full((self.n_dates, self.n_stocks), np.nan)
            if self.n_dates > 1:
                prev_close[1:] = inputs.close[:-1]
            effective_long, report, apply_diag = \
                apply_tradability_with_diagnostics(
                    np.clip(positions, 0.0, None),
                    prev_close, inputs.high, inputs.low, inputs.close,
                    inputs.open_, inputs.volume, inputs.suspended, inputs.board,
                    inputs.is_st, inputs.dates, policy=inputs.policy,
                    adj=inputs.adj, is_delisting=inputs.is_delisting,
                    no_limit=inputs.no_limit, ref=getattr(inputs, "ref", None),
                    limit_up=getattr(inputs, "limit_up", None),
                    limit_down=getattr(inputs, "limit_down", None))
            # 空头腿透传；原地累加，避免再分配一份 (T,N)
            effective = effective_long
            for _t in range(self.n_dates):
                effective[_t] += np.minimum(positions[_t], 0.0)
            turnover = compute_turnover(effective)
            diag = dict(getattr(inputs, "diagnostics", None) or {})
            diag.update(apply_diag)
            # 审计 P1-①（INV-10）：partial 限价表标记不得被 apply 的全量标记覆盖
            if (diag.get("limit_table_missing_cells") or 0) > 0:
                diag["limit_table_source"] = "stk_limit_partial"
            diag["close_mismatch_cells"] = int(np.count_nonzero(
                ~np.isclose(inputs.close, self._close, equal_nan=True)))
            meta = inputs.meta or {}
            tradability_block = {
                'report': report,
                'meta': meta,
                'diagnostics': diag,
                'price_basis': meta.get('price_basis', 'raw_adj_ref'),
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

    def _evaluate_factor_streaming(self, factor_name: str) -> Dict[str, Any]:
        """P-023：分块 positions/apply/turnover；IC/LS 保持整幅。"""
        factor = self.dl.factor_data[factor_name]
        fwd_ret = self._compute_fwd_returns()

        factor_t = factor.T
        fwd_ret_t = fwd_ret.T
        padding = np.full((fwd_ret_t.shape[0], 1), np.nan)
        fwd_ret_t = np.hstack([padding, fwd_ret_t])

        rank_ic_series = compute_ic_series(factor_t, fwd_ret_t, method='rank')
        rank_icir = compute_icir(rank_ic_series)
        pearson_ic_series = compute_ic_series(factor_t, fwd_ret_t,
                                              method='pearson')
        pearson_icir = compute_icir(pearson_ic_series)
        max_lag = self.config.get('max_lag', 12)
        ic_decay = compute_ic_decay(factor_t, fwd_ret_t, max_lag=max_lag)
        hit_rate = compute_hit_rate(rank_ic_series)
        top_n = self.config.get('top_n', 0.2)
        ls_returns = compute_long_short_returns(factor_t, fwd_ret_t,
                                                top_n=top_n)
        spread = compute_spread(ls_returns)

        plan = self._tradability_plan
        turnover_parts = []
        tradability_block = None
        if plan.mode == "off":
            prev_row = None
            for chunk in plan.iter_chunks():
                pos_chunk = self._build_positions(
                    factor[chunk.start:chunk.stop])
                if prev_row is not None and pos_chunk.shape[0]:
                    turnover_parts.append(np.array(
                        [0.5 * np.sum(np.abs(pos_chunk[0] - prev_row))]))
                row = compute_turnover(pos_chunk)
                if row.size:
                    turnover_parts.append(row)
                if pos_chunk.shape[0]:
                    prev_row = pos_chunk[-1].copy()
                del pos_chunk
            plan.finalize()
        else:
            state = TradabilityApplyState(
                np.zeros(self.n_stocks),
                np.full(self.n_stocks, -1, dtype=int),
                np.zeros(self.n_stocks))
            report_total = None
            diag_total = {}
            mismatch = 0
            pos_prev_row = None
            for chunk in plan.iter_chunks():
                s, e = chunk.start, chunk.stop
                pos_chunk = self._build_positions(factor[s:e])
                target_prev = (None if pos_prev_row is None
                               else np.clip(pos_prev_row, 0.0, None))
                res = plan.build_chunk(chunk)
                inputs_chunk = res.inputs
                T_c = e - s
                prev_close = np.full((T_c, self.n_stocks), np.nan)
                if T_c > 1:
                    prev_close[1:] = inputs_chunk.close[:-1]
                if res.prev_close0 is not None and T_c:
                    prev_close[0] = res.prev_close0
                eff_long, report, apply_diag, state = \
                    apply_tradability_with_diagnostics(
                        np.clip(pos_chunk, 0.0, None),
                        prev_close, inputs_chunk.high, inputs_chunk.low,
                        inputs_chunk.close, inputs_chunk.open_,
                        inputs_chunk.volume, inputs_chunk.suspended,
                        inputs_chunk.board, inputs_chunk.is_st,
                        inputs_chunk.dates, policy=inputs_chunk.policy,
                        adj=inputs_chunk.adj,
                        is_delisting=inputs_chunk.is_delisting,
                        no_limit=inputs_chunk.no_limit,
                        ref=getattr(inputs_chunk, "ref", None),
                        limit_up=getattr(inputs_chunk, "limit_up", None),
                        limit_down=getattr(inputs_chunk, "limit_down", None),
                        state=state, target_prev=target_prev,
                        t_offset=s, is_last_chunk=(e == self.n_dates),
                        return_state=True)
                effective = eff_long
                effective += np.minimum(pos_chunk, 0.0)
                if s > 0 and state.turnover_prev is not None:
                    turnover_parts.append(np.array(
                        [0.5 * np.sum(np.abs(effective[0]
                                             - state.turnover_prev))]))
                row = compute_turnover(effective)
                if row.size:
                    turnover_parts.append(row)
                state.turnover_prev = effective[-1].copy()
                mismatch += int(np.count_nonzero(~np.isclose(
                    inputs_chunk.close, self._close[s:e], equal_nan=True)))
                if report_total is None:
                    report_total = dict(report)
                else:
                    for key in report_total:
                        report_total[key] += report[key]
                for key, value in apply_diag.items():
                    if (key.endswith("_cells")
                            and isinstance(value, (int, np.integer))
                            and not isinstance(value, bool)):
                        diag_total[key] = diag_total.get(key, 0) + int(value)
                    else:
                        diag_total[key] = value
                pos_prev_row = pos_chunk[-1].copy()
                del res, inputs_chunk, pos_chunk, effective, eff_long
            plan.finalize()
            diag = dict(plan.diagnostics or {})
            diag.update(diag_total)
            if (diag.get("limit_table_missing_cells") or 0) > 0:
                diag["limit_table_source"] = "stk_limit_partial"
            diag["close_mismatch_cells"] = mismatch
            meta = plan.meta or {}
            tradability_block = {
                'report': report_total,
                'meta': meta,
                'diagnostics': diag,
                'price_basis': meta.get('price_basis', 'raw_adj_ref'),
                'leg_scope': 'long_only',
                'short_leg_unmodeled': True,
                'turnover_basis': 'effective_long_only',
            }

        turnover = (np.concatenate(turnover_parts) if turnover_parts
                    else np.array([]))
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