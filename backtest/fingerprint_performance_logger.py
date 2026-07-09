# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E4 — FingerprintPerformanceLogger (21 维指纹 × 因子表现持久化日志)

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 998-1360

DuckDB 持久化 (factor_db.duckdb, 不新建数据库), append-only 写入, 默认 enable=False.

设计原则:
- 默认 enable=False (opt-in)
- DuckDB 持久化 (复用 factor_db.duckdb, 不新建数据库)
- append-only 写入, 不修改历史记录
- sklearn-style: log() / query() / get_diagnostics()
"""
from typing import Dict, Any, Optional, List
import logging

import duckdb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# 21 维指纹字段 (与 modules/factor_fingerprint/core/fingerprint.py 对齐)
# ============================================================
FINGERPRINT_FIELDS: List[str] = [
    'ar1_median', 'rank_autocorr', 'vol_clustering_pvalue', 'half_life',
    'level_diff_ic_ratio', 'skewness_std', 'kurtosis_std',
    'js_divergence_mean', 'missing_cv', 'coverage_ratio',
    'sd_score', 'complexity_need', 'snr_estimate',
    'tail_dependence_lower', 'tail_dependence_upper',
    'gpd_shape', 'hill_estimator',
    'regime_transition_prob', 'regime_persistence',
    'regime_ic_diff', 'tail_regime_score',
]

# 6 维表现字段
PERFORMANCE_FIELDS: List[str] = [
    'ic_mean', 'ic_std', 'ic_ir', 'turnover', 'max_drawdown', 'sharpe_ratio',
]

# 3 维管道权重字段
PIPELINE_WEIGHT_FIELDS: List[str] = ['weight_static', 'weight_dynamic', 'weight_mixed']


class FingerprintPerformanceLogger:
    """21 维指纹 × 因子表现持久化日志 (RESEARCH_NOTES §2.5 Layer 1 + §2.7 方案 A)

    记录每次 Pipeline.fit() 时的 (指纹, 表现, 体制) 三元组,
    为后续 E5 AttributionAnalyzer 提供数据基础.

    设计原则:
    - 默认 enable=False (opt-in)
    - DuckDB 持久化 (复用 factor_db.duckdb, 不新建数据库)
    - append-only 写入, 不修改历史记录
    - sklearn-style: log() / query() / get_diagnostics()
    """

    def __init__(
        self,
        db_path: str = 'factor_db.duckdb',
        table_name: str = 'fingerprint_performance_log',
        enable: bool = False,
    ):
        self.db_path = db_path
        self.table_name = table_name
        self.enable = enable
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        if enable:
            self._init_db()

    def _init_db(self) -> None:
        """初始化 DuckDB 表 (幂等, CREATE IF NOT EXISTS)"""
        self._conn = duckdb.connect(self.db_path)
        cols = []
        cols.extend([f"{f} DOUBLE" for f in FINGERPRINT_FIELDS])
        cols.extend([f"{f} DOUBLE" for f in PERFORMANCE_FIELDS])
        cols.extend([f"{f} DOUBLE" for f in PIPELINE_WEIGHT_FIELDS])
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                timestamp VARCHAR,
                factor_name VARCHAR,
                regime VARCHAR,
                {', '.join(cols)},
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        self._conn.execute(create_sql)

    # ============================================================
    # log: 记录一条 (指纹, 表现, 体制) 三元组
    # ============================================================

    def log(
        self,
        factor_name: str,
        fingerprint,
        performance: Dict[str, float],
        timestamp: Optional[str] = None,
        regime: Optional[str] = None,
        pipeline_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """记录一条 (指纹, 表现, 体制) 三元组

        Args:
            factor_name: 因子名
            fingerprint: FactorFingerprint (NamedTuple, 21 维)
            performance: 表现字典, 含 ic_mean/ic_std/ic_ir/turnover/max_drawdown/sharpe_ratio
            timestamp: YYYY-MM-DD 字符串; None 时用今天
            regime: 'bull' / 'bear' / 'neutral' / None
            pipeline_weights: {'static': float, 'dynamic': float, 'mixed': float}
        """
        if not self.enable:
            return
        if timestamp is None:
            timestamp = pd.Timestamp.now().strftime('%Y-%m-%d')

        # 从 FactorFingerprint 提取 21 维 (NamedTuple._asdict 或 to_dict 或 dict)
        if hasattr(fingerprint, '_asdict'):
            fp_dict = fingerprint._asdict()
        elif hasattr(fingerprint, 'to_dict'):
            fp_dict = fingerprint.to_dict()
        else:
            fp_dict = dict(fingerprint)

        row: Dict[str, Any] = {
            'timestamp': timestamp,
            'factor_name': factor_name,
            'regime': regime,
        }
        # 21 维指纹 (NaN 安全)
        for f in FINGERPRINT_FIELDS:
            val = fp_dict.get(f, np.nan)
            try:
                row[f] = float(val) if not (val is None or (isinstance(val, float) and np.isnan(val))) else np.nan
            except (TypeError, ValueError):
                row[f] = np.nan
        # 6 维表现
        for f in PERFORMANCE_FIELDS:
            val = performance.get(f, np.nan)
            try:
                row[f] = float(val) if not (val is None or (isinstance(val, float) and np.isnan(val))) else np.nan
            except (TypeError, ValueError):
                row[f] = np.nan
        # 3 维管道权重
        if pipeline_weights:
            # 支持 {'static':...} 和 {'weight_static':...} 两种 key 风格
            row['weight_static'] = float(pipeline_weights.get('static', pipeline_weights.get('weight_static', np.nan)))
            row['weight_dynamic'] = float(pipeline_weights.get('dynamic', pipeline_weights.get('weight_dynamic', np.nan)))
            row['weight_mixed'] = float(pipeline_weights.get('mixed', pipeline_weights.get('weight_mixed', np.nan)))
        else:
            for w in PIPELINE_WEIGHT_FIELDS:
                row[w] = np.nan

        df = pd.DataFrame([row])
        # 显式列名 INSERT (跳过 created_at, 它有 DEFAULT CURRENT_TIMESTAMP)
        all_cols = (['timestamp', 'factor_name', 'regime']
                    + FINGERPRINT_FIELDS
                    + PERFORMANCE_FIELDS
                    + PIPELINE_WEIGHT_FIELDS)
        col_list = ", ".join(all_cols)
        placeholders = ", ".join(["?"] * len(all_cols))
        # NaN → None 以便 DuckDB 存为 NULL (避免类型推断问题)
        # numpy scalar → Python native (DuckDB 不接受 numpy int64/float64)
        values = []
        for c in all_cols:
            v = df.iloc[0][c]
            if isinstance(v, float) and np.isnan(v):
                values.append(None)
            elif isinstance(v, (np.integer,)):
                values.append(int(v))
            elif isinstance(v, (np.floating,)):
                values.append(float(v))
            elif isinstance(v, (np.bool_,)):
                values.append(bool(v))
            else:
                values.append(v)
        self._conn.execute(
            f"INSERT INTO {self.table_name} ({col_list}) VALUES ({placeholders})",
            values,
        )

    # ============================================================
    # query: 查询历史记录
    # ============================================================

    def query(
        self,
        factor_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> pd.DataFrame:
        """查询历史记录

        Args:
            factor_name: 因子名过滤 (None = 不过滤)
            start_date: 起始日期 (YYYY-MM-DD, 含, None = 不过滤)
            end_date: 结束日期 (YYYY-MM-DD, 含, None = 不过滤)
            regime: 体制过滤 (None = 不过滤)

        Returns:
            DataFrame, 按 timestamp 升序; enable=False 时返回空 DataFrame
        """
        if not self.enable:
            return pd.DataFrame()
        conditions = []
        params: list = []
        if factor_name is not None:
            conditions.append("factor_name = ?")
            params.append(factor_name)
        if start_date is not None:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date is not None:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        if regime is not None:
            conditions.append("regime = ?")
            params.append(regime)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM {self.table_name}{where} ORDER BY timestamp"
        return self._conn.execute(sql, params).fetchdf()

    # ============================================================
    # compute_attribution: 指纹维度 → 表现的初步归因 (Layer 1)
    # ============================================================

    def compute_attribution(
        self,
        performance_metric: str = 'ic_mean',
        group_by: str = 'regime',
        n_quantiles: int = 5,
    ) -> pd.DataFrame:
        """计算指纹维度 → 表现的初步归因 (Layer 1)

        对每个指纹维度按分位数分桶, 计算各桶的平均表现.

        Args:
            performance_metric: 表现指标列名 (如 'ic_mean')
            group_by: 分组列名 (如 'regime')
            n_quantiles: 分位数桶数 (默认 5)

        Returns:
            DataFrame: columns = [fingerprint_dim, quantile_bucket, group_by, n_factors, performance_metric]
            enable=False 或无数据时返回空 DataFrame
        """
        if not self.enable:
            return pd.DataFrame()
        df = self.query()
        if df.empty:
            return pd.DataFrame()
        if performance_metric not in df.columns:
            return pd.DataFrame()
        if group_by not in df.columns:
            group_by = 'regime' if 'regime' in df.columns else None
            if group_by is None:
                return pd.DataFrame()

        results = []
        for fp_field in FINGERPRINT_FIELDS:
            if fp_field not in df.columns:
                continue
            valid = df[df[fp_field].notna() & df[performance_metric].notna()].copy()
            if len(valid) < n_quantiles:
                continue
            try:
                valid['quantile_bucket'] = pd.qcut(
                    valid[fp_field], q=n_quantiles, labels=False, duplicates='drop'
                )
            except (ValueError, IndexError):
                continue
            if valid['quantile_bucket'].isna().all():
                continue
            for bucket in valid['quantile_bucket'].dropna().unique():
                bucket_df = valid[valid['quantile_bucket'] == bucket]
                for group_val in bucket_df[group_by].dropna().unique():
                    sub = bucket_df[bucket_df[group_by] == group_val]
                    if len(sub) == 0:
                        continue
                    results.append({
                        'fingerprint_dim': fp_field,
                        'quantile_bucket': int(bucket),
                        group_by: group_val,
                        'n_factors': len(sub),
                        performance_metric: float(sub[performance_metric].mean()),
                    })
        return pd.DataFrame(results)

    # ============================================================
    # get_diagnostics: 诊断信息
    # ============================================================

    def get_diagnostics(self) -> Dict[str, Any]:
        """诊断信息: 记录数 / 时间范围 / 因子数 / 缺失率

        Returns:
            enable=False: {'enabled': False}
            enable=True 无数据: {'enabled': True, 'n_records': 0}
            enable=True 有数据: {'enabled': True, 'n_records': int, 'n_factors': int, ...}
        """
        if not self.enable:
            return {'enabled': False}
        df = self.query()
        if df.empty:
            return {'enabled': True, 'n_records': 0}
        diag: Dict[str, Any] = {
            'enabled': True,
            'n_records': int(len(df)),
            'n_factors': int(df['factor_name'].nunique()) if 'factor_name' in df.columns else 0,
            'date_range': (
                str(df['timestamp'].min()) if 'timestamp' in df.columns else None,
                str(df['timestamp'].max()) if 'timestamp' in df.columns else None,
            ),
            'regime_distribution': df['regime'].value_counts().to_dict() if 'regime' in df.columns else {},
            'fingerprint_missing_rate': {
                f: float(df[f].isna().mean()) if f in df.columns else 1.0
                for f in FINGERPRINT_FIELDS
            },
        }
        return diag

    # ============================================================
    # 资源管理
    # ============================================================

    def close(self) -> None:
        """关闭 DuckDB 连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
