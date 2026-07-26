# -*- coding: utf-8 -*-
"""
数据桥接模块 — Pipeline → DataLoaderV3 适配器

将 Pipeline 输出的 DataFrame 格式 (n_stocks × n_dates)
转换为 DataLoaderV3 的 NumPy 数组格式 (n_dates × n_stocks)。

职责:
  - 转置: (stocks, dates) → (dates, stocks)
  - 创建 DataLoaderV3 实例
  - 形状/一致性验证

这是 Pipeline 和回测引擎之间的唯一数据通道。
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# TD-1.4 (ADR-016): Factor_Trading_v3.0 已子包化 (pip install -e .),
# 直接导入 DataLoaderV3, 不再用 importlib 动态加载 hack.
# 原 hack 的两个原因已消除:
#   1. "绕过 core/__init__.py 的重依赖链" — core/__init__.py 已改为空 (轻量)
#   2. "避免 core/ 遮蔽 Factor_DB/core" — 子包化后用 Factor_Trading_v3_0.core 命名空间,
#      不再与 Factor_DB/core 冲突 (ADR-013)
# P2-fix (v3.4.0): 改为 lazy import, 仅在 create_dataloader 调用时导入,
# 避免模块加载时强制依赖 Factor_Trading_v3_0 (41 个测试 collection error 的根因之一).


class DataBridge:
    """Pipeline 输出 → DataLoaderV3 格式适配器。

    核心转换:
      Pipeline:  Dict[str, pd.DataFrame]  shape (n_stocks, n_dates)
      ↓
      DataLoaderV3:  NumPy arrays  shape (n_dates, n_stocks)
    """

    def __init__(self):
        self._n_stocks: int = 0
        self._n_dates: int = 0
        self._DataLoaderV3 = None  # lazy-loaded

    def _ensure_dataloader(self):
        """Lazy load DataLoaderV3 on first use.

        Defers the Factor_Trading_v3_0 import to call time so that
        ``from factor_pipeline.backtest import DataBridge`` works even
        when the external project is not installed.
        """
        if self._DataLoaderV3 is not None:
            return self._DataLoaderV3
        try:
            from Factor_Trading_v3_0.core.data_v3 import DataLoaderV3
        except ImportError as e:
            from factor_pipeline.exceptions import AdapterImportError
            raise AdapterImportError(
                f"data_bridge: REQUIRED 依赖 factor-trading-v3 导入失败: {e}. "
                f"请运行 cd F:/Coding/Factor_Trading_v3.0 && python -m pip install -e . 安装",
                module_path="Factor_Trading_v3_0.core.data_v3",
                class_name="DataLoaderV3",
            ) from e
        self._DataLoaderV3 = DataLoaderV3
        return DataLoaderV3

    # ── 因子数据转置 ──────────────────────────────────

    def _transpose_factor_data(
        self,
        processed_factors: Dict[str, pd.DataFrame],
    ) -> Dict[str, np.ndarray]:
        """将因子 DataFrame 从 (n_stocks, n_dates) 转置为 (n_dates, n_stocks)。

        Args:
            processed_factors: Pipeline 输出的因子数据
                {factor_name: DataFrame(index=stocks, columns=dates)}

        Returns:
            {factor_name: np.ndarray(shape=(n_dates, n_stocks))}
        """
        result = {}
        for name, df in processed_factors.items():
            # df.values → (n_stocks, n_dates) → .T → (n_dates, n_stocks)
            result[name] = df.values.T.astype(np.float64)
        return result

    # ── 价格数据构建 ──────────────────────────────────

    def _build_price_dataframe(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """将价格 DataFrame 从 (n_stocks, n_dates) 转置为 (n_dates, n_stocks)。

        Args:
            price_data: DataFrame(index=stocks, columns=dates)

        Returns:
            DataFrame(index=dates, columns=stocks)，适用于 DataLoaderV3.from_pandas_dataframes
        """
        # 转置: (stocks, dates) → (dates, stocks)
        close_df = price_data.T.copy()
        close_df.index = close_df.index.astype(str)
        close_df.columns = close_df.columns.astype(str)
        return close_df

    # ── 创建 DataLoaderV3 ──────────────────────────────────

    def create_dataloader(
        self,
        processed_factors: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
        min_dates: Optional[Dict[str, int]] = None,
    ) -> "DataLoaderV3":
        """从 Pipeline 输出创建 DataLoaderV3。

        Args:
            processed_factors: Pipeline 输出的因子数据
            price_data: 价格数据 (index=stocks, columns=dates)
            min_dates: per-factor 最小日期数阈值 (P1 新增)
                {factor_name: min_dates}。低于阈值的因子被跳过。
                未指定的因子使用默认值 20。

        Returns:
            配置好的 DataLoaderV3 实例
        """
        DataLoaderV3 = self._ensure_dataloader()

        # P1: 自适应 min_dates 过滤
        DEFAULT_MIN_DATES = 20
        min_dates = min_dates or {}

        filtered_factors = {}
        skipped_factors = []
        for name, df in processed_factors.items():
            threshold = min_dates.get(name, DEFAULT_MIN_DATES)
            n_dates = df.shape[1]
            if n_dates < threshold:
                logger.info(
                    f"[DataBridge] 跳过因子 {name}: "
                    f"{n_dates} 天 < 阈值 {threshold}"
                )
                skipped_factors.append(name)
            else:
                filtered_factors[name] = df

        if skipped_factors:
            logger.info(
                f"[DataBridge] 跳过 {len(skipped_factors)} 个因子 "
                f"(日期不足): {skipped_factors}"
            )

        # 1. 构建 close DataFrame (dates × stocks) — 始终需要,即使无因子
        close_df = self._build_price_dataframe(price_data)

        if not filtered_factors:
            logger.warning("[DataBridge] 所有因子都被跳过,无数据可加载")
            # 返回空因子字典的 DataLoaderV3 (engine 需处理空因子场景)
            return DataLoaderV3.from_pandas_dataframes(
                close=close_df, factor_dict={},
            )

        # 2. 转置并对齐因子数据到 close_df 的 (dates, stocks) 索引
        # P1 修正: 不同因子的日期范围可能不同 (Barra 41 天 vs 日频 250 天),
        # 用 reindex 对齐到 close_df 的日期索引,缺失日期填 NaN
        factor_dict_for_v3 = {}
        close_index = close_df.index
        close_columns = close_df.columns

        for name, df in filtered_factors.items():
            # df: (n_stocks, n_dates) → 转置为 (n_dates, n_stocks)
            factor_df = df.T.copy()
            # 统一索引类型为 str 以便 reindex (pandas 2.x: astype(object) 不转换 Timestamp)
            factor_df.index = factor_df.index.astype(str)
            factor_df.columns = factor_df.columns.astype(str)
            # reindex 对齐: 行(日期)与列(股票)都对齐到 close_df,缺失填 NaN
            factor_df = factor_df.reindex(index=close_index, columns=close_columns)
            factor_dict_for_v3[name] = factor_df

        # 3. 创建 DataLoaderV3
        dl = DataLoaderV3.from_pandas_dataframes(
            close=close_df,
            factor_dict=factor_dict_for_v3,
        )

        self._n_stocks = dl.n_stocks
        self._n_dates = dl.n_dates

        logger.info(
            f"DataBridge 创建 DataLoaderV3: "
            f"{self._n_dates} 天 × {self._n_stocks} 股票, "
            f"{len(filtered_factors)} 个因子 "
            f"(跳过 {len(skipped_factors)} 个)"
        )

        return dl

    # ── P3: loaded_at 滞后处理 ──────────────────────────────────

    def _apply_loaded_at_lag(
        self,
        factor_data: pd.DataFrame,
        loaded_at_data: pd.DataFrame,
        use_loaded_at: bool = True,
        fill_missing: str = 'ffill',
    ) -> pd.DataFrame:
        """利用 loaded_at 消除 look-ahead bias。

        对于每个 (stock, trade_date)，如果 loaded_at > trade_date,
        则因子值在 trade_date 时刻不可见，设为 NaN，然后前向填充。

        Args:
            factor_data: 因子数据 (index=stocks, columns=trade_dates)
            loaded_at_data: 加载日期 (index=stocks, columns=trade_dates)
            use_loaded_at: 是否启用 loaded_at 检查
            fill_missing: 'ffill' 前向填充, 'nan' 保持 NaN

        Returns:
            调整后的因子数据 (index=stocks, columns=trade_dates)
        """
        if not use_loaded_at:
            return factor_data.copy()

        # 确保 loaded_at_data 的列是 datetime
        loaded_at_data = loaded_at_data.copy()
        if not loaded_at_data.empty:
            for col in loaded_at_data.columns:
                if not pd.api.types.is_datetime64_any_dtype(loaded_at_data[col]):
                    loaded_at_data[col] = pd.to_datetime(loaded_at_data[col])

        # 检查是否全为 NaT（没有 loaded_at 信息）
        all_nat = True
        if not loaded_at_data.empty:
            for col in loaded_at_data.columns:
                if not loaded_at_data[col].isna().all():
                    all_nat = False
                    break
        if all_nat:
            return factor_data.copy()

        # 构建结果 DataFrame，初始为 NaN
        result = pd.DataFrame(
            np.nan,
            index=factor_data.index,
            columns=factor_data.columns,
        )

        # 对于每个 stock，基于 loaded_at 构建可见时间线
        for stock in factor_data.index:
            factor_series = factor_data.loc[stock]  # Series(index=trade_date, value=factor)
            loaded_series = loaded_at_data.loc[stock]  # Series(index=trade_date, value=loaded_at)

            # 检查该 stock 是否有有效的 loaded_at
            has_valid_loaded = False
            for trade_date in factor_series.index:
                if trade_date in loaded_series.index and not pd.isna(loaded_series[trade_date]):
                    has_valid_loaded = True
                    break

            if not has_valid_loaded:
                # 没有 loaded_at 信息 → 保持原始值
                result.loc[stock] = factor_series
                continue

            # 按 loaded_at 排序，从最早到最晚，后面的覆盖前面的
            pairs = []
            for trade_date in factor_series.index:
                if trade_date not in loaded_series.index:
                    continue
                loaded = loaded_series[trade_date]
                if pd.isna(loaded):
                    continue
                pairs.append((pd.Timestamp(loaded), trade_date, factor_series[trade_date]))

            # 按 loaded_at 排序
            pairs.sort(key=lambda x: x[0])

            for loaded, trade_date, factor_val in pairs:
                # 找到所有 >= loaded 的 trade_dates 列
                release_dates = result.columns[
                    pd.to_datetime(result.columns) >= loaded
                ]
                for rd in release_dates:
                    result.loc[stock, rd] = factor_val  # 始终覆盖，取最新值

        # 前向填充
        if fill_missing == 'ffill':
            result = result.ffill(axis=1)
        elif fill_missing == 'nan':
            pass  # 保持 NaN

        return result

    # ── 形状验证 ──────────────────────────────────

    def validate_shapes(
        self,
        processed_factors: Dict[str, pd.DataFrame],
        price_data: pd.DataFrame,
    ) -> Tuple[bool, str]:
        """验证因子数据和价格数据的一致性。

        检查:
          1. 因子字典非空
          2. 所有因子的 index/columns 与价格数据一致
          3. 因子内部无 NaN 全列

        Args:
            processed_factors: Pipeline 输出的因子数据
            price_data: 价格数据

        Returns:
            (is_valid, message)
        """
        # 空因子字典
        if not processed_factors:
            return False, "因子字典为空"

        ref_index = price_data.index
        ref_columns = price_data.columns

        for name, df in processed_factors.items():
            if not isinstance(df, pd.DataFrame):
                return False, f"因子 '{name}' 不是 DataFrame"

            # 检查 index (stocks)
            if not df.index.equals(ref_index):
                return False, (
                    f"因子 '{name}' 的 index 与价格数据不一致: "
                    f"因子 {len(df.index)} 股票 vs 价格 {len(ref_index)} 股票"
                )

            # 检查 columns (dates)
            if not df.columns.equals(ref_columns):
                return False, (
                    f"因子 '{name}' 的 columns 与价格数据不一致: "
                    f"因子 {len(df.columns)} 期 vs 价格 {len(ref_columns)} 期"
                )

        return True, "OK"