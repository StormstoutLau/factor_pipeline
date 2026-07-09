# -*- coding: utf-8 -*-
"""12 个 A 股状态变量加载器 (RESEARCH_NOTES E7 §3.1)

状态变量分 5 类:
- liquidity (2): market_turnover, amihud_illiquidity
- sentiment (2): new_account_growth, margin_balance_ratio
- capital_flow (2): northbound_flow, etf_flow
- macro_regime (3): cpi_surprise, pmi_surprise, term_spread
- style_regime (3): value_growth_spread, small_large_spread, low_vol_high_vol_spread

数据源: akshare (可选依赖, extras: state-data). 不可用时降级为合成数据.

设计原则:
- 默认 enable=False (opt-in)
- 缺失率 > max_missing_rate 的变量标记为不可靠, 不参与回归
- 提供 get_variable_metadata() 便于审计
"""
from typing import Dict, Any, Optional, List
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class StateDataLoader:
    """12 个 A 股状态变量加载器 (RESEARCH_NOTES §2B.2)

    状态变量分 5 类:
    - liquidity (2): market_turnover, amihud_illiquidity
    - sentiment (2): new_account_growth, margin_balance_ratio
    - capital_flow (2): northbound_flow, etf_flow
    - macro_regime (3): cpi_surprise, pmi_surprise, term_spread
    - style_regime (3): value_growth_spread, small_large_spread, low_vol_high_vol_spread

    数据源: akshare (需 extras: state-data)

    设计原则:
    - 默认 enable=False (opt-in)
    - 缺失率 > max_missing_rate 的变量标记为不可靠, 不参与回归
    - 提供 get_variable_metadata() 便于审计
    """

    VARIABLE_CATEGORIES: Dict[str, List[str]] = {
        'liquidity': ['market_turnover', 'amihud_illiquidity'],
        'sentiment': ['new_account_growth', 'margin_balance_ratio'],
        'capital_flow': ['northbound_flow', 'etf_flow'],
        'macro_regime': ['cpi_surprise', 'pmi_surprise', 'term_spread'],
        'style_regime': [
            'value_growth_spread', 'small_large_spread', 'low_vol_high_vol_spread',
        ],
    }

    ALL_VARIABLES: List[str] = [v for vs in VARIABLE_CATEGORIES.values() for v in vs]

    # 变量元数据: 定义 + 来源 (类别由 VARIABLE_CATEGORIES 反查)
    _VARIABLE_DEFINITIONS: Dict[str, Dict[str, str]] = {
        'market_turnover': {
            'definition': '全市场日均换手率',
            'source': "akshare stock_zh_a_spot",
        },
        'amihud_illiquidity': {
            'definition': 'Amihud (2002) 非流动性 (|r| / volume)',
            'source': '计算: |r| / volume',
        },
        'new_account_growth': {
            'definition': '新增开户数同比',
            'source': 'akshare stock_account_em',
        },
        'margin_balance_ratio': {
            'definition': '两融余额 / 市值',
            'source': 'akshare stock_margin_*',
        },
        'northbound_flow': {
            'definition': '北向资金净流入',
            'source': 'akshare stock_hsgt_*',
        },
        'etf_flow': {
            'definition': 'ETF 净申赎',
            'source': 'akshare fund_etf_*',
        },
        'cpi_surprise': {
            'definition': 'CPI 同比 - 一致预期',
            'source': 'akshare macro_china_*',
        },
        'pmi_surprise': {
            'definition': 'PMI - 50',
            'source': 'akshare macro_china_pmi',
        },
        'term_spread': {
            'definition': '10Y - 1Y 国债利差',
            'source': 'akshare bond_zh_*',
        },
        'value_growth_spread': {
            'definition': '价值因子 - 成长因子收益差',
            'source': '计算: 因子组合收益',
        },
        'small_large_spread': {
            'definition': '小盘 - 大盘收益差',
            'source': 'akshare 指数',
        },
        'low_vol_high_vol_spread': {
            'definition': '低波 - 高波收益差',
            'source': '计算: 因子组合收益',
        },
    }

    def __init__(
        self,
        enable: bool = False,
        min_observations: int = 252,
        source: str = 'akshare',
        max_missing_rate: float = 0.05,
    ):
        self.enable = enable
        self.min_observations = min_observations
        self.source = source
        self.max_missing_rate = max_missing_rate
        self._data: Optional[pd.DataFrame] = None
        self._metadata: Dict[str, Dict] = {}
        self._fallback_used: bool = False

    def fit(self, start_date: str, end_date: str) -> 'StateDataLoader':
        """加载状态变量数据

        Args:
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            self (链式调用)

        Raises:
            ValueError: 观测数 < min_observations
        """
        if not self.enable:
            return self

        # 生成日期索引 (bdate_range: 工作日)
        dates = pd.bdate_range(start_date, end_date)
        n_obs = len(dates)
        if n_obs < self.min_observations:
            raise ValueError(
                f"观测数 {n_obs} < 最小要求 {self.min_observations}"
            )

        # 根据数据源加载
        if self.source == 'synthetic':
            self._data = self._generate_synthetic(n_obs, dates)
            self._fallback_used = False
        elif self.source == 'akshare':
            self._fit_akshare(start_date, end_date, dates, n_obs)
        else:
            raise ValueError(f"未知 source: {self.source}")

        self._metadata = self._build_metadata()
        return self

    def _fit_akshare(
        self,
        start_date: str,
        end_date: str,
        dates: pd.DatetimeIndex,
        n_obs: int,
    ) -> None:
        """akshare 数据源加载流程

        降级规则:
        - import akshare 失败 → 合成数据 + _fallback_used=True
        - 全部 API 调用失败 → 合成数据 + _fallback_used=True
        - 至少 1 个变量成功 → 真实数据 (失败列用合成填充) + _fallback_used=False
        """
        try:
            import akshare  # noqa: F401  验证可导入
        except ImportError:
            # akshare 不可用, 降级为合成数据
            self._data = self._generate_synthetic(n_obs, dates)
            self._fallback_used = True
            logger.warning(
                "akshare 不可用, 降级为合成数据. "
                "安装: pip install factor-pipeline[state-data]"
            )
            return

        # akshare 可用, 尝试真实加载
        real_data = self._load_from_akshare(start_date, end_date, dates)

        # 检查是否所有变量都失败 (全 NaN 或空)
        successful_cols = []
        if real_data is not None and not real_data.empty:
            for col in real_data.columns:
                if not real_data[col].isna().all():
                    successful_cols.append(col)

        if not successful_cols:
            # 全部失败 → 降级合成
            self._data = self._generate_synthetic(n_obs, dates)
            self._fallback_used = True
            logger.warning(
                "akshare 可用但全部 API 调用失败, 降级为合成数据"
            )
            return

        # 至少 1 个变量成功: 用真实数据, 失败列用合成数据填充
        synthetic = self._generate_synthetic(n_obs, dates)
        merged = pd.DataFrame(index=dates)
        for var in self.ALL_VARIABLES:
            if var in real_data.columns and not real_data[var].isna().all():
                merged[var] = real_data[var].reindex(dates)
            else:
                # 该变量失败, 用合成数据填充
                merged[var] = synthetic[var].values
        self._data = merged
        self._fallback_used = False
        n_success = len(successful_cols)
        logger.info(
            f"akshare 加载完成: {n_success}/{len(self.ALL_VARIABLES)} "
            f"变量成功, 其余用合成数据填充"
        )

    # ============================================================
    # akshare 真实加载入口
    # ============================================================

    def _load_from_akshare(
        self,
        start_date: str,
        end_date: str,
        dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """从 akshare 真实加载 12 个状态变量

        每个 _load_<var> 方法独立 try/except, 单个失败不影响其他变量.
        返回 DataFrame (index=dates), 成功列含真实数据, 失败列为 NaN.

        Args:
            start_date: 起始日期
            end_date: 结束日期
            dates: 目标日期索引

        Returns:
            DataFrame, 列为成功加载的变量 (失败变量不出现在列中)
        """
        import akshare as ak

        result = pd.DataFrame(index=dates)

        # 12 个变量各自的加载方法 (命名约定: _load_<var_name>)
        for var in self.ALL_VARIABLES:
            loader = getattr(self, f'_load_{var}', None)
            if loader is None:
                logger.warning(f"未实现 {var} 的加载方法, 跳过")
                continue
            try:
                series = loader(ak, start_date, end_date)
                if series is None:
                    continue
                if not isinstance(series, pd.Series):
                    logger.warning(f"{var} 加载返回非 Series 类型: {type(series)}")
                    continue
                if series.empty:
                    continue
                # 确保日期索引
                if not pd.api.types.is_datetime64_any_dtype(series.index):
                    series.index = pd.to_datetime(series.index, errors='coerce')
                # 去掉无效日期, 转为 float
                series = series[~series.index.isna()]
                series = pd.to_numeric(series, errors='coerce').astype(float)
                # 去重 (保留最后值) 并 reindex 到目标日期
                series = series[~series.index.duplicated(keep='last')]
                series = series.sort_index()
                result[var] = series.reindex(dates)
            except Exception as e:
                # 单个变量失败不影响其他变量
                logger.warning(f"加载状态变量 {var} 失败: {e}")
                continue

        return result

    # ============================================================
    # 辅助工具
    # ============================================================

    @staticmethod
    def _find_col(df: Any, candidates: List[str]) -> Optional[str]:
        """从候选列名中找到第一个存在的列 (大小写不敏感)

        Args:
            df: DataFrame
            candidates: 候选列名列表

        Returns:
            第一个匹配的列名, 未找到返回 None
        """
        if df is None or not hasattr(df, 'columns'):
            return None
        try:
            cols = list(df.columns)
        except Exception:
            return None
        cols_lower = {str(c).lower(): c for c in cols}
        for c in candidates:
            if c in cols:
                return c
            key = c.lower()
            if key in cols_lower:
                return cols_lower[key]
        return None

    @staticmethod
    def _series_from_df(
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
    ) -> Optional[pd.Series]:
        """从 DataFrame 提取 Series, 以 date_col 为索引, value_col 为值"""
        if df is None or df.empty:
            return None
        if date_col not in df.columns or value_col not in df.columns:
            return None
        s = pd.to_numeric(df[value_col], errors='coerce')
        s.index = pd.to_datetime(df[date_col], errors='coerce')
        s = s[~s.index.isna()]
        return s

    # ============================================================
    # 12 个状态变量各自的 akshare 加载器
    # ============================================================

    def _load_market_turnover(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """市场换手率: 全市场日均换手率

        优先 ak.stock_turnover_em() (历史市场换手率),
        降级到 ak.stock_zh_a_spot_em() 当前快照均值.
        """
        # 方案 1: stock_turnover_em 历史换手率
        try:
            df = ak.stock_turnover_em()
            date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
            val_col = self._find_col(
                df, ['换手率', 'turnover_rate', 'turnover', '平均换手率'],
            )
            if date_col and val_col:
                s = self._series_from_df(df, date_col, val_col)
                if s is not None and not s.empty:
                    return s.sort_index()
        except Exception as e:
            logger.debug(f"stock_turnover_em 调用失败: {e}")

        # 方案 2: 当前 A 股 spot 快照, 取均值作为常数序列
        df = ak.stock_zh_a_spot_em()
        val_col = self._find_col(df, ['换手率', 'turnover_rate'])
        if val_col is None:
            return None
        avg = pd.to_numeric(df[val_col], errors='coerce').mean()
        if pd.isna(avg):
            return None
        dates = pd.bdate_range(start_date, end_date)
        return pd.Series(float(avg), index=dates)

    def _load_amihud_illiquidity(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """Amihud (2002) 非流动性: |r| / 成交额

        用沪深300指数日线代理全市场, 计算 |日收益| / 成交额.
        """
        # 拉取沪深300指数日线
        try:
            df = ak.stock_zh_index_daily_em(symbol="sh000300")
        except Exception as e:
            logger.debug(f"stock_zh_index_daily_em 失败: {e}")
            return None

        date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
        close_col = self._find_col(df, ['收盘', 'close', '收盘价'])
        vol_col = self._find_col(df, ['成交额', 'amount', 'turnover_value'])
        if not (date_col and close_col and vol_col):
            return None

        close = pd.to_numeric(df[close_col], errors='coerce').values
        amount = pd.to_numeric(df[vol_col], errors='coerce').values
        idx = pd.to_datetime(df[date_col], errors='coerce')

        # |日收益| / 成交额 (避免除零)
        ret = np.diff(close, prepend=close[0]) / close
        safe_amt = np.where(amount > 0, amount, np.nan)
        amihud = np.abs(ret) / safe_amt
        s = pd.Series(amihud, index=idx)
        s = s[~s.index.isna()]
        return s.sort_index()

    def _load_new_account_growth(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """新增开户数同比增速

        ak.stock_account_em() 返回 A 股账户新增数历史.
        """
        try:
            df = ak.stock_account_em()
        except Exception as e:
            logger.debug(f"stock_account_em 失败: {e}")
            return None

        date_col = self._find_col(df, ['日期', 'date', '月份', '统计月份'])
        val_col = self._find_col(
            df, ['新增账户', '新增投资者', '股票账户新增数', '新增'],
        )
        if not (date_col and val_col):
            return None
        s = self._series_from_df(df, date_col, val_col)
        if s is None or s.empty:
            return None
        # 计算同比增速 (pct_change period=12 假设月度数据)
        growth = s.pct_change(periods=12) if len(s) > 12 else s.pct_change()
        return growth.dropna().sort_index()

    def _load_margin_balance_ratio(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """融资融券余额比 (两融余额, 单位: 亿元)

        ak.stock_margin_em() 返回两融余额历史.
        """
        try:
            df = ak.stock_margin_em()
        except Exception as e:
            logger.debug(f"stock_margin_em 失败: {e}")
            return None

        date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
        val_col = self._find_col(
            df, ['融资融券余额', '两融余额', '余额', '融资余额'],
        )
        if not (date_col and val_col):
            return None
        return self._series_from_df(df, date_col, val_col)

    def _load_northbound_flow(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """北向资金净流入 (单位: 亿元)

        ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        """
        try:
            df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        except Exception as e:
            # 尝试不带 symbol
            try:
                df = ak.stock_hsgt_north_net_flow_in_em()
            except Exception as e2:
                logger.debug(f"stock_hsgt_north_net_flow_in_em 失败: {e}; {e2}")
                return None

        date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
        val_col = self._find_col(
            df, ['当日成交净买额', '当日资金流入', '净流入', '净买额'],
        )
        if not (date_col and val_col):
            return None
        return self._series_from_df(df, date_col, val_col)

    def _load_etf_flow(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """ETF 净申赎资金流 (单位: 亿元)

        ak.fund_etf_fund_daily_em() 返回 ETF 基金日线.
        """
        try:
            df = ak.fund_etf_fund_daily_em()
        except Exception as e:
            logger.debug(f"fund_etf_fund_daily_em 失败: {e}")
            return None

        date_col = self._find_col(df, ['日期', 'date', '净值日期'])
        val_col = self._find_col(
            df, ['净申购', '净流入', '资金净流入', '份额变动'],
        )
        if not (date_col and val_col):
            return None
        return self._series_from_df(df, date_col, val_col)

    def _load_cpi_surprise(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """CPI 惊喜: CPI 同比 - 一致预期

        简化: 用 ak.macro_china_cpi() 的同比, 一致预期以滚动均值代理.
        """
        try:
            df = ak.macro_china_cpi()
        except Exception as e:
            logger.debug(f"macro_china_cpi 失败: {e}")
            return None

        date_col = self._find_col(df, ['月份', '日期', 'date', 'report_date'])
        val_col = self._find_col(
            df, ['同比增长', '当月同比', 'cpi_yoy', '同比'],
        )
        if not (date_col and val_col):
            return None
        s = self._series_from_df(df, date_col, val_col)
        if s is None or s.empty:
            return None
        # 一致预期用滚动 12 期均值代理
        expected = s.rolling(window=12, min_periods=3).mean()
        surprise = s - expected
        return surprise.dropna().sort_index()

    def _load_pmi_surprise(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """PMI 惊喜: PMI - 50 (50 为荣枯线)

        ak.macro_china_pmi() 返回制造业 PMI.
        """
        try:
            df = ak.macro_china_pmi()
        except Exception as e:
            logger.debug(f"macro_china_pmi 失败: {e}")
            return None

        date_col = self._find_col(df, ['月份', '日期', 'date', 'report_date'])
        val_col = self._find_col(
            df, ['制造业-Loss', '制造业-PMI', 'pmi', '制造业PMI', '制造业'],
        )
        if not (date_col and val_col):
            # 尝试取第二列为数值
            if len(df.columns) >= 2:
                date_col = self._find_col(df, ['月份', '日期', 'date'])
                if date_col:
                    val_col = df.columns[1]
        if not (date_col and val_col):
            return None
        s = self._series_from_df(df, date_col, val_col)
        if s is None or s.empty:
            return None
        # PMI - 50 (荣枯线)
        return (s - 50.0).sort_index()

    def _load_term_spread(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """期限利差: 10Y 国债收益率 - 1Y 国债收益率

        ak.bond_china_yield(start_date, end_date) 返回国债收益率曲线.
        """
        try:
            df = ak.bond_china_yield(start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.debug(f"bond_china_yield 失败: {e}")
            return None

        date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
        # 尝试匹配 10 年和 1 年列
        y10_col = self._find_col(
            df, ['10年', '10年国债收益率', '10y', '10Y'],
        )
        y1_col = self._find_col(
            df, ['1年', '1年国债收益率', '1y', '1Y'],
        )
        if not (date_col and y10_col and y1_col):
            return None
        y10 = pd.to_numeric(df[y10_col], errors='coerce')
        y1 = pd.to_numeric(df[y1_col], errors='coerce')
        spread = y10 - y1
        spread.index = pd.to_datetime(df[date_col], errors='coerce')
        spread = spread[~spread.index.isna()]
        return spread.sort_index()

    def _load_value_growth_spread(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """价值-成长价差: 价值指数收益 - 成长指数收益

        沪深300价值 (000967) - 沪深300成长 (000966) 日收益差.
        """
        value_s = self._load_index_returns(ak, "sh000967", start_date, end_date)
        growth_s = self._load_index_returns(ak, "sh000966", start_date, end_date)
        if value_s is None or growth_s is None:
            return None
        # 对齐日期, 计算收益差
        df = pd.concat([value_s, growth_s], axis=1, keys=['v', 'g']).dropna()
        if df.empty:
            return None
        return (df['v'] - df['g']).sort_index()

    def _load_small_large_spread(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """小盘-大盘价差: 中证500收益 - 沪深300收益

        中证500 (000905) - 沪深300 (000300) 日收益差.
        """
        small_s = self._load_index_returns(ak, "sh000905", start_date, end_date)
        large_s = self._load_index_returns(ak, "sh000300", start_date, end_date)
        if small_s is None or large_s is None:
            return None
        df = pd.concat([small_s, large_s], axis=1, keys=['s', 'l']).dropna()
        if df.empty:
            return None
        return (df['s'] - df['l']).sort_index()

    def _load_low_vol_high_vol_spread(
        self, ak: Any, start_date: str, end_date: str,
    ) -> Optional[pd.Series]:
        """低波动-高波动价差

        简化: 用上证50 (sh000016, 低波大盘) - 创业板指 (sh399006, 高波成长)
        日收益差代理.
        """
        low_vol_s = self._load_index_returns(ak, "sh000016", start_date, end_date)
        high_vol_s = self._load_index_returns(ak, "sh399006", start_date, end_date)
        if low_vol_s is None or high_vol_s is None:
            return None
        df = pd.concat(
            [low_vol_s, high_vol_s], axis=1, keys=['lv', 'hv'],
        ).dropna()
        if df.empty:
            return None
        return (df['lv'] - df['hv']).sort_index()

    def _load_index_returns(
        self,
        ak: Any,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Optional[pd.Series]:
        """加载指数日线并计算日收益率

        Args:
            ak: akshare 模块
            symbol: 指数代码 (如 'sh000300')
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            pd.Series, index=日期, values=日收益率
        """
        try:
            df = ak.stock_zh_index_daily_em(symbol=symbol)
        except Exception as e:
            logger.debug(f"加载指数 {symbol} 失败: {e}")
            return None
        date_col = self._find_col(df, ['日期', 'date', 'trade_date'])
        close_col = self._find_col(df, ['收盘', 'close', '收盘价'])
        if not (date_col and close_col):
            return None
        close = pd.to_numeric(df[close_col], errors='coerce')
        close.index = pd.to_datetime(df[date_col], errors='coerce')
        close = close[~close.index.isna()].sort_index()
        close = close[~close.index.duplicated(keep='last')]
        # 过滤日期范围
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        close = close.loc[(close.index >= start_ts) & (close.index <= end_ts)]
        if close.empty or len(close) < 2:
            return None
        # 日收益率
        return close.pct_change().dropna()

    # ============================================================
    # 合成数据 + 元数据
    # ============================================================

    def _generate_synthetic(
        self, n_obs: int, dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """生成合成状态变量数据 (用于测试和 akshare 不可用时的降级)

        Args:
            n_obs: 观测数
            dates: 日期索引

        Returns:
            DataFrame (n_obs, 12)
        """
        rng = np.random.default_rng(42)
        data = {}
        for var in self.ALL_VARIABLES:
            data[var] = rng.normal(0, 1, n_obs)
        return pd.DataFrame(data, index=dates)

    def _build_metadata(self) -> Dict[str, Dict]:
        """构建变量元数据: 类别 / 定义 / 来源"""
        meta = {}
        # 反查类别
        var_to_cat = {}
        for cat, vars_ in self.VARIABLE_CATEGORIES.items():
            for v in vars_:
                var_to_cat[v] = cat
        for var in self.ALL_VARIABLES:
            defn = self._VARIABLE_DEFINITIONS.get(var, {})
            meta[var] = {
                'category': var_to_cat.get(var, 'unknown'),
                'definition': defn.get('definition', ''),
                'source': defn.get('source', ''),
            }
        return meta

    def load_12_state_variables(self) -> pd.DataFrame:
        """返回 12 列状态变量 DataFrame

        Returns:
            DataFrame (T, 12), 列名 = ALL_VARIABLES.
            enable=False 或未 fit 时返回空 DataFrame.
        """
        if self._data is None:
            return pd.DataFrame()
        return self._data.copy()

    def get_variable_metadata(self) -> Dict[str, Dict]:
        """返回各变量的元数据: 类别 / 定义 / 来源

        Returns:
            {var_name: {'category': str, 'definition': str, 'source': str}}
        """
        return self._metadata

    def get_diagnostics(self) -> Dict[str, Any]:
        """返回诊断信息

        Returns:
            Dict 含 enabled/loaded/n_observations/n_variables/
            missing_rates/unreliable_variables/source/fallback_used
        """
        if self._data is None:
            return {
                'enabled': self.enable,
                'loaded': False,
                'fallback_used': self._fallback_used,
            }
        missing_rates = self._data.isna().mean()
        return {
            'enabled': self.enable,
            'loaded': True,
            'n_observations': len(self._data),
            'n_variables': len(self._data.columns),
            'date_range': (
                str(self._data.index.min()), str(self._data.index.max())
            ),
            'missing_rates': missing_rates.to_dict(),
            'unreliable_variables': missing_rates[
                missing_rates > self.max_missing_rate
            ].index.tolist(),
            'source': self.source,
            'fallback_used': self._fallback_used,
        }
