# -*- coding: utf-8 -*-
"""v3.7.0 E5/E6 — G2 门禁与台账 stage 测试（T41-T46 + T41b/T45b，8 项）。

对应 ``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §4.5 与
``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §9 / §10。
"""
import numpy as np
import pytest

from factor_pipeline.backtest.multiple_testing_ledger import (
    CorrectionTrack,
    FamilyConflictError,
    FamilySpec,
    MultipleTestingLedger,
    TrialRecord,
    VariantSpec,
)


def _family(stage="factor", family_id="fam1"):
    variant = VariantSpec(
        variant_id="v1", factor_id="f_v1", description="d",
        spec_hash="h_v1", kind="confirmatory",
    )
    return FamilySpec(
        family_id=family_id,
        experiment_id="exp_1",
        batch_id="batch_1",
        description="test",
        registered_by="tester",
        correction_track=CorrectionTrack.FDR,
        variants=(variant,),
        stage=stage,
    )


def _trial(family_id, stage="S3"):
    return TrialRecord(
        family_id=family_id, variant_id="v1", attempt_id="a1",
        factor_id="f_v1", stage=stage, metric_name="lambda_mean",
        metric_value=0.01, p_value=0.01, spec_hash="h_v1",
    )


def test_t46_ledger_stage_consistency(tmp_path):
    ledger = MultipleTestingLedger(db_path=str(tmp_path / "mt.duckdb"))
    try:
        # portfolio family 只接受 S4 / portfolio trial
        ledger.register_family(_family(stage="portfolio", family_id="fam_port"))
        with pytest.raises(FamilyConflictError):
            ledger.record_trial(_trial("fam_port", stage="S3"))
        ledger.record_trial(_trial("fam_port", stage="S4"))
        ledger.record_trial(_trial("fam_port", stage="portfolio"))

        # factor family 拒绝 S4 / portfolio trial
        ledger.register_family(_family(stage="factor", family_id="fam_fac"))
        with pytest.raises(FamilyConflictError):
            ledger.record_trial(_trial("fam_fac", stage="S4"))
        with pytest.raises(FamilyConflictError):
            ledger.record_trial(_trial("fam_fac", stage="portfolio"))
        ledger.record_trial(_trial("fam_fac", stage="S3"))

        # 旧 family（未显式 stage）默认 factor，S3 正常
        ledger.register_family(_family(family_id="fam_legacy"))
        ledger.record_trial(_trial("fam_legacy", stage="S3"))
        assert ledger._load_family("fam_legacy").stage == "factor"
    finally:
        ledger.close()


# ============================================================
# E6: G2 门禁（T41-T45b）
# ============================================================

from factor_pipeline.backtest import governance as gov  # noqa: E402
from factor_pipeline.backtest.governance import (  # noqa: E402
    G2Policy,
    GovernanceRecord,
    Stage,
    evaluate_g2,
)
from factor_pipeline.backtest.multiple_testing_ledger import (  # noqa: E402
    CorrectionMethod,
)


def _gate_record(**overrides):
    base = dict(
        record_id="r1", batch_id="b1", experiment_id="e1", factor_id="f1",
        stage=Stage.S3, pipeline_version="3.7.0", config_hash="cfg",
        construction_code_hash="code", data_snapshot={},
        data_snapshot_hash="dsh",
        sample_window={"start": "2020-01-01", "end": "2025-01-01"},
        benchmark_id="hs300", return_convention="monthly_next",
        tradable_convention={
            "st_source": "name_proxy", "suspend_source": "event_rebuild"},
        cost_model={}, sign_convention="positive",
        test_family="fam", correction_method="benjamini_hochberg",
        effect_metric="lambda_mean", effect_size=0.05,
        ci=(0.01, 0.09), n_trials=10, q_value=0.01,
        dsr=0.99, pbo=0.05,
        oos_metric={
            "metric": "sharpe", "value": 0.8,
            "n_periods": 12, "same_sign": True,
        },
    )
    base.update(overrides)
    return GovernanceRecord.model_construct(**base)


def test_t41_fdr_track_pass():
    out = evaluate_g2(_gate_record())
    assert out.passed is True
    assert out.action == "allow"
    assert out.reasons == []
    assert out.evaluated_by == "script"
    assert out.evidence_refs == ["r1"]


def test_t41b_method_name_no_drift():
    assert gov._FDR_METHODS == frozenset({
        CorrectionMethod.BH.value, CorrectionMethod.BY.value})
    assert gov._FWER_METHODS == frozenset({
        CorrectionMethod.BONFERRONI.value, CorrectionMethod.HOLM.value,
        CorrectionMethod.ROMANO_WOLF.value, CorrectionMethod.WHITE_RC.value,
        CorrectionMethod.HANSEN_SPA.value})
    all_methods = {m.value for m in CorrectionMethod}
    assert gov._FDR_METHODS | gov._FWER_METHODS == all_methods
    assert not (gov._FDR_METHODS & gov._FWER_METHODS)


def test_t42_fwer_track_pass():
    record = _gate_record(
        correction_method="holm", q_value=None, adjusted_p=0.02)
    out = evaluate_g2(record)
    assert out.passed is True
    assert out.action == "allow"


def test_t43_ambiguous_track_rejected():
    record = _gate_record(
        correction_method="benjamini_hochberg",
        q_value=0.01, adjusted_p=0.01,
    )
    out = evaluate_g2(record)
    assert out.passed is False
    assert "ambiguous_track" in out.reasons
    assert out.action == "downgrade"


def test_t44_threshold_failures():
    out_dsr = evaluate_g2(_gate_record(dsr=0.9))
    assert "dsr_below_threshold" in out_dsr.reasons
    assert out_dsr.action == "downgrade"

    policy = G2Policy(require_pbo=True)
    out_pbo = evaluate_g2(_gate_record(pbo=0.2), policy=policy)
    assert "pbo_above_threshold" in out_pbo.reasons
    assert out_pbo.action == "downgrade"


def test_t45_oos_missing_or_sign_flip():
    out_missing = evaluate_g2(_gate_record(oos_metric=None))
    assert "missing_oos" in out_missing.reasons

    out_flip = evaluate_g2(_gate_record(oos_metric={
        "metric": "sharpe", "value": 0.8,
        "n_periods": 12, "same_sign": False,
    }))
    assert "oos_not_same_sign" in out_flip.reasons


def test_t45b_record_structure_validation():
    def _valid_payload(**overrides):
        payload = dict(
            record_id="r2", batch_id="b1", experiment_id="e1",
            factor_id="f1", stage=Stage.S3, pipeline_version="3.7.0",
            config_hash="cfg", construction_code_hash="code",
            data_snapshot={}, data_snapshot_hash="dsh",
            sample_window={"start": "2020-01-01", "end": "2025-01-01"},
            benchmark_id="hs300", return_convention="monthly_next",
            tradable_convention={
                "st_source": "name_proxy",
                "suspend_source": "event_rebuild"},
            cost_model={}, sign_convention="positive",
            test_family="fam", correction_method="benjamini_hochberg",
            effect_metric="lambda_mean", effect_size=0.05,
            ci=(0.01, 0.09), n_trials=10, q_value=0.01,
        )
        payload.update(overrides)
        return payload

    GovernanceRecord(**_valid_payload(dsr=0.9, pbo=0.1))
    for bad in (1.2, float("nan"), -0.1):
        with pytest.raises(ValueError):
            GovernanceRecord(**_valid_payload(dsr=bad))
    with pytest.raises(ValueError):
        GovernanceRecord(**_valid_payload(pbo=-0.1))
    with pytest.raises(ValueError):
        GovernanceRecord(**_valid_payload(pbo=1.5))

    oos = {"metric": "sharpe", "value": 0.8,
           "n_periods": 12, "same_sign": True}
    for key in ("metric", "value", "n_periods", "same_sign"):
        broken = dict(oos)
        broken.pop(key)
        with pytest.raises(ValueError):
            GovernanceRecord(**_valid_payload(oos_metric=broken))
    for key, bad in (
        ("metric", 123), ("value", "high"),
        ("n_periods", 0), ("same_sign", "yes"),
    ):
        broken = dict(oos)
        broken[key] = bad
        with pytest.raises(ValueError):
            GovernanceRecord(**_valid_payload(oos_metric=broken))
