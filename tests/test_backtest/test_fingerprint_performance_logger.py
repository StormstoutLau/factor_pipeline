# -*- coding: utf-8 -*-
"""RESEARCH_NOTES E4 — FingerprintPerformanceLogger 测试 (TDD Red)

测试 21 维指纹 × 因子表现持久化日志 (DuckDB).

规格文档: docs/EXECUTION_RESEARCH_NOTES.md 行 998-1360

TDD 流程: Red (本文件) → Green (实现) → Review
"""
import pytest
import numpy as np
import pandas as pd

from modules.factor_fingerprint import FactorFingerprint
from backtest.fingerprint_performance_logger import (
    FingerprintPerformanceLogger,
    FINGERPRINT_FIELDS,
    PERFORMANCE_FIELDS,
    PIPELINE_WEIGHT_FIELDS,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_fingerprint(**overrides) -> FactorFingerprint:
    """构造一个 21 维 FactorFingerprint, 默认全 0.5, 可覆盖"""
    defaults = {f: 0.5 for f in FINGERPRINT_FIELDS}
    defaults.update(overrides)
    return FactorFingerprint(**defaults)


def _make_performance(**overrides) -> dict:
    """构造 6 维表现字典"""
    perf = {
        'ic_mean': 0.05,
        'ic_std': 0.1,
        'ic_ir': 0.5,
        'turnover': 0.3,
        'max_drawdown': -0.15,
        'sharpe_ratio': 1.2,
    }
    perf.update(overrides)
    return perf


def _make_pipeline_weights(**overrides) -> dict:
    """构造管道权重字典"""
    weights = {'static': 0.4, 'dynamic': 0.3, 'mixed': 0.3}
    weights.update(overrides)
    return weights


# ============================================================
# 测试类: TestFingerprintPerformanceLogger (14 测试)
# ============================================================

class TestFingerprintPerformanceLogger:
    """E4 FingerprintPerformanceLogger TDD 测试"""

    # ---------- 1. 初始化与开关 ----------

    def test_init_creates_table(self, tmp_path):
        """enable=True 时表被创建"""
        db_path = str(tmp_path / "test_fp.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        # 表应存在
        tables = logger._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "fp_log" in table_names
        logger._conn.close()

    def test_disabled_no_op(self, tmp_path):
        """enable=False 时所有操作无副作用, query 返回空 DataFrame"""
        db_path = str(tmp_path / "test_fp_disabled.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=False
        )
        # log 不报错, 无副作用
        logger.log(
            factor_name="f1",
            fingerprint=_make_fingerprint(),
            performance=_make_performance(),
        )
        # query 返回空 DataFrame
        df = logger.query()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        # get_diagnostics 返回 {'enabled': False}
        diag = logger.get_diagnostics()
        assert diag == {'enabled': False}

    def test_idempotent_init(self, tmp_path):
        """多次 __init__ 不报错 (CREATE IF NOT EXISTS)"""
        db_path = str(tmp_path / "test_fp_idem.duckdb")
        logger1 = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        conn1 = logger1._conn
        # 第二次实例化 (复用同一 DB 文件)
        logger2 = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        # 写入一条记录验证表仍可用
        logger2.log(
            factor_name="f1",
            fingerprint=_make_fingerprint(),
            performance=_make_performance(),
        )
        df = logger2.query()
        assert len(df) == 1
        conn1.close()
        logger2._conn.close()

    # ---------- 2. 单条记录写入 ----------

    def test_log_single_record(self, tmp_path):
        """log 一条记录后 query 返回 1 行"""
        db_path = str(tmp_path / "test_fp_single.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        logger.log(
            factor_name="factor_a",
            fingerprint=_make_fingerprint(ar1_median=0.7),
            performance=_make_performance(ic_mean=0.08),
            timestamp="2024-01-15",
            regime="bull",
            pipeline_weights=_make_pipeline_weights(),
        )
        df = logger.query()
        assert len(df) == 1
        assert df.iloc[0]['factor_name'] == "factor_a"
        assert df.iloc[0]['timestamp'] == "2024-01-15"
        assert df.iloc[0]['regime'] == "bull"
        logger._conn.close()

    def test_log_preserves_all_21_fingerprint_fields(self, tmp_path):
        """21 维指纹字段完整存储"""
        db_path = str(tmp_path / "test_fp_21.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        # 构造每个字段不同的值以便验证
        overrides = {f: float(i + 1) * 0.1 for i, f in enumerate(FINGERPRINT_FIELDS)}
        logger.log(
            factor_name="f_21",
            fingerprint=_make_fingerprint(**overrides),
            performance=_make_performance(),
            timestamp="2024-02-01",
            regime="neutral",
        )
        df = logger.query()
        assert len(df) == 1
        row = df.iloc[0]
        for f in FINGERPRINT_FIELDS:
            assert f in df.columns, f"字段 {f} 不在表中"
            expected = overrides[f]
            actual = row[f]
            assert abs(float(actual) - expected) < 1e-6, (
                f"字段 {f} 期望 {expected}, 实际 {actual}"
            )
        logger._conn.close()

    def test_log_preserves_performance_fields(self, tmp_path):
        """表现字段完整存储"""
        db_path = str(tmp_path / "test_fp_perf.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        perf = _make_performance(
            ic_mean=0.06, ic_std=0.12, ic_ir=0.55,
            turnover=0.25, max_drawdown=-0.18, sharpe_ratio=1.35,
        )
        logger.log(
            factor_name="f_perf",
            fingerprint=_make_fingerprint(),
            performance=perf,
            pipeline_weights=_make_pipeline_weights(),
        )
        df = logger.query()
        assert len(df) == 1
        row = df.iloc[0]
        for f in PERFORMANCE_FIELDS:
            assert f in df.columns, f"表现字段 {f} 不在表中"
            assert abs(float(row[f]) - perf[f]) < 1e-6, (
                f"表现字段 {f} 期望 {perf[f]}, 实际 {row[f]}"
            )
        # 管道权重也应存储
        assert abs(float(row['weight_static']) - 0.4) < 1e-6
        assert abs(float(row['weight_dynamic']) - 0.3) < 1e-6
        assert abs(float(row['weight_mixed']) - 0.3) < 1e-6
        logger._conn.close()

    # ---------- 3. 查询过滤 ----------

    def test_query_by_factor_name(self, tmp_path):
        """按 factor_name 过滤"""
        db_path = str(tmp_path / "test_fp_qfn.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        for fname in ["alpha", "beta", "alpha", "gamma"]:
            logger.log(
                factor_name=fname,
                fingerprint=_make_fingerprint(),
                performance=_make_performance(),
                timestamp="2024-03-01",
            )
        df = logger.query(factor_name="alpha")
        assert len(df) == 2
        assert df['factor_name'].nunique() == 1
        assert (df['factor_name'] == "alpha").all()
        logger._conn.close()

    def test_query_by_date_range(self, tmp_path):
        """按日期范围过滤"""
        db_path = str(tmp_path / "test_fp_qdr.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        timestamps = ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]
        for i, ts in enumerate(timestamps):
            logger.log(
                factor_name=f"f{i}",
                fingerprint=_make_fingerprint(),
                performance=_make_performance(),
                timestamp=ts,
            )
        df = logger.query(start_date="2024-02-01", end_date="2024-03-15")
        assert len(df) == 2
        assert (df['timestamp'] >= "2024-02-01").all()
        assert (df['timestamp'] <= "2024-03-15").all()
        logger._conn.close()

    def test_query_by_regime(self, tmp_path):
        """按 regime 过滤"""
        db_path = str(tmp_path / "test_fp_qr.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        regimes = ["bull", "bear", "bull", "neutral"]
        for i, r in enumerate(regimes):
            logger.log(
                factor_name=f"f{i}",
                fingerprint=_make_fingerprint(),
                performance=_make_performance(),
                timestamp="2024-05-01",
                regime=r,
            )
        df = logger.query(regime="bull")
        assert len(df) == 2
        assert df['regime'].nunique() == 1
        assert (df['regime'] == "bull").all()
        logger._conn.close()

    # ---------- 4. 归因分析 ----------

    def test_compute_attribution_returns_dataframe(self, tmp_path):
        """归因返回非空 DataFrame"""
        db_path = str(tmp_path / "test_fp_attr.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        # 写入足够多记录以支持 5 分位分桶
        np.random.seed(42)
        for i in range(30):
            fp = _make_fingerprint(gpd_shape=float(np.random.randn()))
            perf = _make_performance(ic_mean=float(np.random.randn() * 0.1))
            logger.log(
                factor_name=f"f{i}",
                fingerprint=fp,
                performance=perf,
                timestamp="2024-06-01",
                regime="bull" if i % 2 == 0 else "bear",
            )
        df = logger.compute_attribution(performance_metric='ic_mean', group_by='regime')
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        logger._conn.close()

    def test_compute_attribution_quantile_buckets(self, tmp_path):
        """归因含分位桶列 'quantile_bucket'"""
        db_path = str(tmp_path / "test_fp_qb.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        np.random.seed(42)
        for i in range(30):
            fp = _make_fingerprint(ar1_median=float(np.random.randn()))
            perf = _make_performance(ic_mean=float(np.random.randn() * 0.1))
            logger.log(
                factor_name=f"f{i}",
                fingerprint=fp,
                performance=perf,
                timestamp="2024-07-01",
                regime="bull",
            )
        df = logger.compute_attribution(performance_metric='ic_mean')
        assert 'quantile_bucket' in df.columns
        assert len(df) > 0
        logger._conn.close()

    # ---------- 5. 诊断 ----------

    def test_get_diagnostics_enabled(self, tmp_path):
        """enable=True 时 diagnostics 含 'n_records'"""
        db_path = str(tmp_path / "test_fp_diag.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        logger.log(
            factor_name="f1",
            fingerprint=_make_fingerprint(),
            performance=_make_performance(),
            timestamp="2024-08-01",
            regime="bull",
        )
        logger.log(
            factor_name="f2",
            fingerprint=_make_fingerprint(),
            performance=_make_performance(),
            timestamp="2024-08-02",
            regime="bear",
        )
        diag = logger.get_diagnostics()
        assert isinstance(diag, dict)
        assert diag.get('enabled') is True
        assert 'n_records' in diag
        assert diag['n_records'] == 2
        logger._conn.close()

    def test_get_diagnostics_disabled(self, tmp_path):
        """enable=False 时 diagnostics 返回 {'enabled': False}"""
        db_path = str(tmp_path / "test_fp_diagd.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=False
        )
        diag = logger.get_diagnostics()
        assert diag == {'enabled': False}

    # ---------- 6. 边界情况 ----------

    def test_nan_fingerprint_field_handled(self, tmp_path):
        """指纹字段为 NaN 时不报错"""
        db_path = str(tmp_path / "test_fp_nan.duckdb")
        logger = FingerprintPerformanceLogger(
            db_path=db_path, table_name="fp_log", enable=True
        )
        # 构造含 NaN 的指纹 (gpd_shape 默认 NaN, 模拟正态分布)
        fp = FactorFingerprint(
            ar1_median=0.6,
            rank_autocorr=0.4,
            vol_clustering_pvalue=0.3,
            half_life=5.0,
            level_diff_ic_ratio=2.0,
            skewness_std=0.5,
            kurtosis_std=1.2,
            js_divergence_mean=0.1,
            missing_cv=0.05,
            coverage_ratio=0.95,
            sd_score=0.7,
            complexity_need=0.3,
            snr_estimate=1.5,
            tail_dependence_lower=np.nan,  # NaN
            tail_dependence_upper=np.nan,  # NaN
            gpd_shape=np.nan,              # NaN (正态分布)
            hill_estimator=np.nan,         # NaN
            regime_transition_prob=np.nan, # NaN
            regime_persistence=np.nan,     # NaN
            regime_ic_diff=np.nan,         # NaN
            tail_regime_score=np.nan,      # NaN
        )
        # log 不报错
        logger.log(
            factor_name="f_nan",
            fingerprint=fp,
            performance=_make_performance(),
            timestamp="2024-09-01",
            regime="bull",
        )
        df = logger.query()
        assert len(df) == 1
        # NaN 字段应存储为 NaN
        assert np.isnan(float(df.iloc[0]['gpd_shape']))
        # 非 NaN 字段应正常
        assert abs(float(df.iloc[0]['ar1_median']) - 0.6) < 1e-6
        logger._conn.close()
