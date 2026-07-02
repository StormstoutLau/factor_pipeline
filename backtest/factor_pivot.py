# -*- coding: utf-8 -*-
"""
DuckDB PIVOT 适配器 — 用 DuckDB 原生 PIVOT 替代 pandas pivot

将因子数据从 (trade_date, stock_code, factor_value) 长表
直接在 DuckDB 引擎内转为 (stock_code × trade_date) 宽表，
跳过 pandas pivot 的内存开销和 Python 循环。

性能: 7M 行 pivot 从 ~29s (pandas) → ~3s (DuckDB)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

import duckdb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorPivotAdapter:
    """用 DuckDB PIVOT 语法直接获取 (stock_code × trade_date) 格式的因子数据。

    Usage:
        adapter = FactorPivotAdapter('factor_db.duckdb')
        result = adapter.get_pivoted(
            ['PE', 'PB'],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        # result = {'PE': DataFrame(stock_code × trade_date), ...}
    """

    def __init__(self, db_path: str):
        """初始化适配器。

        Args:
            db_path: DuckDB 数据库路径
        """
        self.db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._wide_columns: Optional[List[str]] = None
        self._detect_schema()

    # ── 公开 API ──────────────────────────────────

    def get_pivoted(
        self,
        factor_names: List[str],
        stock_codes: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, pd.DataFrame]:
        """获取 pivoted 因子数据。

        Args:
            factor_names: 因子名称列表
            stock_codes: 股票代码列表 (None 表示全部)
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            {factor_name: DataFrame(index=stock_code, columns=trade_date)}
        """
        if not factor_names:
            return {}

        result: Dict[str, pd.DataFrame] = {}
        for fn in factor_names:
            result[fn] = self._pivot_single(fn, stock_codes, start_date, end_date)

        logger.info(f"FactorPivotAdapter: {len(result)} 个因子 pivoted")
        return result

    def close(self):
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── 内部方法 ──────────────────────────────────

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """懒加载 DuckDB 连接 (只读模式)。"""
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path, read_only=True)
        return self._conn

    def _detect_schema(self):
        """检测宽表结构。"""
        try:
            tables = self.conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchdf()['table_name'].tolist()

            if 'factor_wide' in tables:
                cols = self.conn.execute("DESCRIBE factor_wide").fetchdf()
                skip = {'trade_date', 'stock_code', 'loaded_at'}
                self._wide_columns = [c for c in cols['column_name'].tolist() if c not in skip]
            else:
                self._wide_columns = []
        except Exception as e:
            logger.warning(f"检测宽表失败: {e}")
            self._wide_columns = []

    def _pivot_single(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """对单个因子执行 DuckDB PIVOT。

        优先使用 factor_wide 宽表 (性能最优)，
        回退到 factor_data 长表 + PIT 过滤。
        """
        if factor_name not in (self._wide_columns or []):
            logger.debug(f"因子 {factor_name} 不在宽表中，尝试长表")
            return self._pivot_from_long(factor_name, stock_codes, start_date, end_date)

        return self._pivot_from_wide(factor_name, stock_codes, start_date, end_date)

    def _pivot_from_wide(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """从 factor_wide 宽表执行 PIVOT。

        宽表已经是 (trade_date, stock_code, factor_1, factor_2, ...) 格式，
        只需要 SELECT + PIVOT ON trade_date。
        """
        conditions = [f'"{factor_name}" IS NOT NULL']
        if start_date is not None:
            conditions.append(f"trade_date >= '{start_date}'")
        if end_date is not None:
            conditions.append(f"trade_date <= '{end_date}'")
        if stock_codes is not None:
            codes = "', '".join(str(s) for s in stock_codes)
            conditions.append(f"stock_code IN ('{codes}')")

        where_clause = ' AND '.join(conditions)

        sql = f'''
            PIVOT (
                SELECT stock_code, trade_date, "{factor_name}" AS val
                FROM factor_wide
                WHERE {where_clause}
            )
            ON trade_date
            USING FIRST(val)
            GROUP BY stock_code
        '''

        try:
            df = self.conn.execute(sql).fetchdf()
        except Exception as e:
            logger.warning(f"DuckDB PIVOT 失败 ({factor_name}): {e}，回退到 pandas")
            return self._fallback_pandas_wide(factor_name, stock_codes, start_date, end_date)

        if df.empty:
            return pd.DataFrame()

        df = df.set_index('stock_code')
        # 确保列是 datetime
        df.columns = pd.to_datetime(df.columns)
        # 确保值是 float
        df = df.astype('float64')
        return df

    def _pivot_from_long(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """从 factor_data 长表执行 PIVOT (带 PIT 过滤)。"""
        conditions = [f"factor_name = '{factor_name}'"]
        if start_date is not None:
            conditions.append(f"trade_date >= '{start_date}'")
        if end_date is not None:
            conditions.append(f"trade_date <= '{end_date}'")
        if stock_codes is not None:
            codes = "', '".join(str(s) for s in stock_codes)
            conditions.append(f"stock_code IN ('{codes}')")

        where_clause = ' AND '.join(conditions)

        sql = f'''
            PIVOT (
                SELECT stock_code, trade_date, factor_value AS val
                FROM factor_data
                WHERE {where_clause}
                  AND (trade_date, stock_code, factor_name, loaded_at) IN (
                      SELECT trade_date, stock_code, factor_name, MAX(loaded_at)
                      FROM factor_data
                      WHERE {where_clause}
                      GROUP BY trade_date, stock_code, factor_name
                  )
            )
            ON trade_date
            USING FIRST(val)
            GROUP BY stock_code
        '''

        try:
            df = self.conn.execute(sql).fetchdf()
        except Exception as e:
            logger.warning(f"DuckDB PIVOT 长表失败 ({factor_name}): {e}")
            return pd.DataFrame()

        if df.empty:
            return pd.DataFrame()

        df = df.set_index('stock_code')
        df.columns = pd.to_datetime(df.columns)
        return df.astype('float64')

    def _fallback_pandas_wide(
        self,
        factor_name: str,
        stock_codes: Optional[List[str]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> pd.DataFrame:
        """pandas pivot 回退方案。"""
        conditions = [f'"{factor_name}" IS NOT NULL']
        if start_date is not None:
            conditions.append(f"trade_date >= '{start_date}'")
        if end_date is not None:
            conditions.append(f"trade_date <= '{end_date}'")
        if stock_codes is not None:
            codes = "', '".join(str(s) for s in stock_codes)
            conditions.append(f"stock_code IN ('{codes}')")

        where_clause = ' AND '.join(conditions)

        sql = f'''
            SELECT stock_code, trade_date, "{factor_name}" AS val
            FROM factor_wide
            WHERE {where_clause}
        '''

        df = self.conn.execute(sql).fetchdf()
        if df.empty:
            return pd.DataFrame()

        pivoted = df.pivot(
            index='stock_code', columns='trade_date', values='val',
        )
        return pivoted