# -*- coding: utf-8 -*-
"""GR-4 多重检验台账 — T21-T30 (v3.6.0 E4).

先于 backtest/multiple_testing_ledger.py 落地；首次运行应为红
（ModuleNotFoundError: No module named 'factor_pipeline.backtest.multiple_testing_ledger'）。

覆盖 EXECUTION_V3.6.0_GOVERNANCE_BASE.md §5.1：
  T21 未预注册拒绝 / T22 时序 / T23-T24 BH/BY 参考
  T25 `<= α` 边界 / T26 RW 参考 / T27 RW 快速核
  T28 White/SPA 联合（注入同一索引矩阵）/ T29 三分母 / T30 轨不匹配
"""
import numpy as np
import pytest

from dataclasses import replace

from factor_pipeline.backtest.multiple_testing import (
    HansenSPA,
    WhiteRealityCheck,
    _romano_wolf_stepdown,
    apply_bh_fdr,
    apply_by_fdr,
    apply_romano_wolf,
)
from factor_pipeline.backtest.multiple_testing_ledger import (
    CorrectionMethod,
    CorrectionTrack,
    FamilyConflictError,
    FamilySpec,
    MultipleTestingLedger,
    PreregistrationError,
    TrackMismatchError,
    TrialRecord,
    VariantSpec,
    _romano_wolf_fast,
)


# ============================================================
# helpers
# ============================================================

def _family(family_id="fam1", track=CorrectionTrack.FDR, alpha=0.05,
            variants=None) -> FamilySpec:
    variants = variants or [("v1", "confirmatory")]
    specs = tuple(
        VariantSpec(
            variant_id=vid, factor_id="f_%s" % vid, description="d",
            spec_hash="h_%s" % vid, kind=kind,
        )
        for vid, kind in variants
    )
    return FamilySpec(
        family_id=family_id,
        experiment_id="exp_20261117_00000001",
        batch_id="batch_20261117_00000001",
        description="test family",
        registered_by="tester",
        correction_track=track,
        alpha=alpha,
        variants=specs,
    )


def _trial(family_id, variant_id, p, attempt_id="a1", *,
           created_at=None, primary=False, stage="S3") -> TrialRecord:
    return TrialRecord(
        family_id=family_id, variant_id=variant_id,
        attempt_id=attempt_id, factor_id="f_%s" % variant_id,
        stage=stage, metric_name="lambda_mean", metric_value=0.01,
        p_value=p, spec_hash="h_%s" % variant_id,
        primary=primary, created_at=created_at,
    )


def _ledger(tmp_path) -> MultipleTestingLedger:
    return MultipleTestingLedger(db_path=str(tmp_path / "mt.duckdb"))


# ============================================================
# T21 未预注册拒绝 / exploratory 允许
# ============================================================

def test_t21_preregistration_required(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(variants=[("v1", "confirmatory")]))

        with pytest.raises(PreregistrationError):
            ledger.record_trial(_trial("fam1", "v2", 0.01))

        assert ledger.record_trial(_trial("fam1", "v2", 0.01), exploratory=True)
        with pytest.raises(PreregistrationError):
            ledger.record_trial(_trial("fam1", "v1", 0.01), exploratory=True)
    finally:
        ledger.close()


# ============================================================
# T22 预注册时序
# ============================================================

def test_t22_trial_before_registration_rejected(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family())
        with pytest.raises(PreregistrationError):
            ledger.record_trial(
                _trial("fam1", "v1", 0.01,
                       created_at="2000-01-01T00:00:00+00:00")
            )
    finally:
        ledger.close()


# ============================================================
# T23-T24 BH / BY 参考实现
# ============================================================

@pytest.mark.parametrize("method,func", [
    (CorrectionMethod.BH, apply_bh_fdr),
    (CorrectionMethod.BY, apply_by_fdr),
])
def test_t23_t24_bh_by_reference(tmp_path, method, func):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(variants=[
            ("v1", "confirmatory"), ("v2", "confirmatory"),
            ("v3", "confirmatory"),
        ]))
        p_values = [0.01, 0.04, 0.03]
        for i, p in enumerate(p_values, 1):
            ledger.record_trial(_trial("fam1", "v%d" % i, p))

        result = ledger.apply("fam1", method=method)
        ref_q, _ = func(p_values, 0.05)
        for variant_id, expected in zip(("v1", "v2", "v3"), ref_q):
            assert abs(result.adjusted[variant_id] - expected) <= 1e-12
            assert result.rejected[variant_id] == (expected <= 0.05)
        assert result.n_hypotheses == 3
    finally:
        ledger.close()


# ============================================================
# T25 q == α 边界
# ============================================================

def test_t25_q_equal_alpha_is_rejected(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family())
        ledger.record_trial(_trial("fam1", "v1", 0.05))
        result = ledger.apply("fam1", method=CorrectionMethod.BH)
        assert abs(result.adjusted["v1"] - 0.05) <= 1e-15
        assert result.rejected["v1"] is True
    finally:
        ledger.close()


# ============================================================
# T26 Romano-Wolf 参考实现
# ============================================================

def test_t26_romano_wolf_reference(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(
            family_id="fam_rw", track=CorrectionTrack.FWER,
            variants=[("v1", "confirmatory"), ("v2", "confirmatory"),
                      ("v3", "confirmatory")],
        ))
        p_values = [0.01, 0.20, 0.50]
        for i, p in enumerate(p_values, 1):
            ledger.record_trial(_trial("fam_rw", "v%d" % i, p))

        rng = np.random.default_rng(20261117)
        boot = rng.random((200, 3)) * 0.10
        result = ledger.apply(
            "fam_rw", method=CorrectionMethod.ROMANO_WOLF,
            bootstrap_p_values=boot,
        )
        ref, _ = apply_romano_wolf(p_values, boot, 0.05)
        got = np.array([result.adjusted["v%d" % i] for i in (1, 2, 3)])
        assert np.max(np.abs(got - np.asarray(ref))) <= 1e-10
    finally:
        ledger.close()


# ============================================================
# T27 RW 快速核等价性
# ============================================================

def test_t27_romano_wolf_fast_equivalence():
    rng = np.random.default_rng(7)
    p_values = rng.random(20)
    boot = rng.random((500, 20))
    fast, fast_rej = _romano_wolf_fast(p_values, boot, alpha=0.05)
    ref, ref_rej = _romano_wolf_stepdown(p_values, boot, alpha=0.05, k=1)
    assert np.max(np.abs(np.asarray(fast) - np.asarray(ref))) <= 1e-15
    assert fast_rej == ref_rej


# ============================================================
# T28 White RC / Hansen SPA 联合检验（同一索引矩阵）
# ============================================================

def test_t28_white_and_hansen_joint(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(
            family_id="fam_white", track=CorrectionTrack.FWER,
            variants=[("v1", "confirmatory"), ("v2", "confirmatory")],
        ))
        ledger.record_trial(_trial("fam_white", "v1", 0.01))
        ledger.record_trial(_trial("fam_white", "v2", 0.20))

        rng = np.random.default_rng(11)
        T = 60
        returns = rng.normal(0.0, 0.1, size=(T, 3))
        returns[:, 0] = 0.0
        returns[:, 1] += 0.01
        indices = rng.integers(0, T, size=(100, T))

        white = ledger.apply(
            "fam_white", method=CorrectionMethod.WHITE_RC,
            returns_matrix=returns, benchmark_index=0,
            bootstrap_indices=indices,
        )
        ref_white = WhiteRealityCheck(n_bootstrap=100).test(
            returns, benchmark_index=0, alpha=0.05,
            bootstrap_indices=indices,
        )
        assert white.joint_p is not None
        assert abs(white.joint_p - ref_white["rc_p_value"]) <= 1e-10

        hansen = ledger.apply(
            "fam_white", method=CorrectionMethod.HANSEN_SPA,
            returns_matrix=returns, benchmark_index=0,
            bootstrap_indices=indices,
        )
        ref_spa = HansenSPA(n_bootstrap=100).test(
            returns, benchmark_index=0, alpha=0.05,
            bootstrap_indices=indices,
        )
        assert hansen.joint_p is not None
        assert abs(hansen.joint_p - ref_spa["spa_p_value"]) <= 1e-10
        assert (ref_spa["spa_lc_p_value"] >= ref_spa["spa_p_value"]
                >= ref_spa["spa_uc_p_value"])
    finally:
        ledger.close()


# ============================================================
# T29 三个分母
# ============================================================

def test_t29_three_denominators(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(variants=[
            ("v1", "confirmatory"), ("v2", "exploratory"),
        ]))
        ledger.record_trial(_trial("fam1", "v1", 0.01, attempt_id="a1",
                                   primary=True))
        ledger.record_trial(_trial("fam1", "v1", 0.02, attempt_id="a2"))
        ledger.record_trial(_trial("fam1", "v1", None, attempt_id="a3"))
        ledger.record_trial(_trial("fam1", "v2", 0.03, attempt_id="a4"),
                            exploratory=True)

        result = ledger.apply("fam1", method=CorrectionMethod.BH)
        assert result.n_trials == 4
        assert result.n_testable == 3
        assert result.n_hypotheses == 1
        assert set(result.adjusted) == {"v1"}
    finally:
        ledger.close()


# ============================================================
# T30 轨与方法不匹配
# ============================================================

def test_t30_track_method_mismatch(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(
            family_id="fam_fdr", track=CorrectionTrack.FDR,
        ))
        ledger.record_trial(_trial("fam_fdr", "v1", 0.01))
        with pytest.raises(TrackMismatchError):
            ledger.apply("fam_fdr", method=CorrectionMethod.BONFERRONI)

        ledger.register_family(_family(
            family_id="fam_fwer", track=CorrectionTrack.FWER,
        ))
        ledger.record_trial(_trial("fam_fwer", "v1", 0.01))
        with pytest.raises(TrackMismatchError):
            ledger.apply("fam_fwer", method=CorrectionMethod.BH)
    finally:
        ledger.close()


# ============================================================
# T39 backfill 隔离 / T40 result_id 稳定
# ============================================================

def _result_rows(ledger):
    return ledger._conn.execute(
        "SELECT result_id, payload FROM %s ORDER BY result_id"
        % ledger._table("result")
    ).fetchall()


def test_t39_backfill_excluded_from_confirmatory(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(variants=[
            ("v1", "confirmatory"), ("v2", "exploratory"),
        ]))
        ledger.record_trial(_trial("fam1", "v1", 0.01, primary=True))
        ledger.record_trial(_trial("fam1", "v2", 0.0001, attempt_id="a2"))
        base = ledger.apply("fam1", method=CorrectionMethod.BH)
        assert base.n_hypotheses == 1
        assert set(base.adjusted) == {"v1"}

        ledger.record_trial(
            _trial("fam1", "v1", 0.50, attempt_id="a0",
                   created_at="2020-01-01T00:00:00+00:00"),
            backfill=True,
        )
        after = ledger.apply("fam1", method=CorrectionMethod.BH)
        assert after.n_trials == base.n_trials + 1
        assert after.n_testable == base.n_testable + 1
        assert after.n_hypotheses == base.n_hypotheses == 1
        assert after.adjusted["v1"] == base.adjusted["v1"]
    finally:
        ledger.close()


def test_t40_result_id_stable_with_exploratory(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(_family(variants=[
            ("v1", "confirmatory"), ("v2", "exploratory"),
        ]))
        ledger.record_trial(_trial("fam1", "v1", 0.01, primary=True))
        ledger.apply("fam1", method=CorrectionMethod.BH)
        first = _result_rows(ledger)
        assert len(first) == 1

        ledger.record_trial(_trial("fam1", "v2", 0.0001, attempt_id="a2"))
        ledger.apply("fam1", method=CorrectionMethod.BH)
        second = _result_rows(ledger)
        assert len(second) == 1
        assert second[0][0] == first[0][0]
    finally:
        ledger.close()


# ============================================================
# v3.7.0 E5: family stage / holdout 回调
# ============================================================

def test_family_stage_default(tmp_path):
    default = _family()
    assert default.stage == "factor"
    # stage 不进入指纹
    assert (replace(default, stage="portfolio").fingerprint()
            == default.fingerprint())

    ledger = _ledger(tmp_path)
    try:
        ledger.register_family(default)
        loaded = ledger._load_family("fam1")
        assert loaded.stage == "factor"
        # 注册时 lead_variant_id 被补全为首个 variant，指纹其余部分不变
        expected = replace(default, lead_variant_id="v1")
        assert loaded.fingerprint() == expected.fingerprint()
    finally:
        ledger.close()


def test_family_stage_portfolio(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        portfolio = replace(_family(), stage="portfolio")
        assert ledger.register_family(portfolio) == "fam1"
        ledger.record_trial(_trial("fam1", "v1", 0.01, stage="S4"))
        ledger.record_trial(
            _trial("fam1", "v1", 0.02, attempt_id="a2", stage="portfolio"))

        with pytest.raises(FamilyConflictError):
            ledger.register_family(
                replace(_family(family_id="fam2"), stage="unknown"))
    finally:
        ledger.close()


def test_holdout_checker_called(tmp_path):
    calls = []

    def checker(holdout_id, batch_id):
        calls.append((holdout_id, batch_id))

    ledger = MultipleTestingLedger(
        db_path=str(tmp_path / "mt.duckdb"), holdout_checker=checker)
    try:
        spec = replace(_family(), holdout_id="h" * 64)
        ledger.register_family(spec)
        assert calls == [("h" * 64, spec.batch_id)]
    finally:
        ledger.close()


def test_holdout_checker_error(tmp_path):
    def checker(holdout_id, batch_id):
        raise RuntimeError("holdout not locked")

    ledger = MultipleTestingLedger(
        db_path=str(tmp_path / "mt.duckdb"), holdout_checker=checker)
    try:
        spec = replace(_family(), holdout_id="h" * 64)
        with pytest.raises(RuntimeError):
            ledger.register_family(spec)
        with pytest.raises(PreregistrationError):
            ledger.record_trial(_trial("fam1", "v1", 0.01))
    finally:
        ledger.close()


def test_family_stage_idempotent(tmp_path):
    ledger = _ledger(tmp_path)
    try:
        factor = _family()
        ledger.register_family(factor)
        portfolio = replace(factor, stage="portfolio")
        assert ledger.register_family(portfolio) == "fam1"
        # 首次注册为准
        assert ledger._load_family("fam1").stage == "factor"
    finally:
        ledger.close()
