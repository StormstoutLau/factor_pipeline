# -*- coding: utf-8 -*-
"""v3.7.0 E2 — DSR / PBO 测试（T15-T26，12 项）。

对应 ``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §4.2 与
``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §5 / §6。
"""
import itertools
import math

import numpy as np
import pytest
from scipy import stats

from backtest.overfitting import (
    _dsr_from_stats,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_ratio,
    trim_to_divisible,
)

GAMMA = 0.5772156649


# ------------------------------------------------------------
# T15-T20  DSR
# ------------------------------------------------------------

def _reference_dsr(returns, n_trials, sr_variance=None):
    r = np.asarray(returns, dtype=float)
    t = len(r)
    sr = r.mean() / r.std(ddof=1)
    skew = stats.skew(r, bias=False)
    kurt = stats.kurtosis(r, fisher=False, bias=False)
    variance = 1.0 / (t - 1) if sr_variance is None else sr_variance
    sr0 = math.sqrt(variance) * (
        (1 - GAMMA) * stats.norm.ppf(1 - 1.0 / n_trials)
        + GAMMA * stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    )
    denom = math.sqrt(
        1 - skew * sr + ((kurt - 1) / 4.0) * sr ** 2)
    return stats.norm.cdf((sr - sr0) * math.sqrt(t - 1) / denom), sr0


def test_t15_dsr_formula_reference():
    rng = np.random.default_rng(7)
    returns = rng.normal(0.02, 0.05, 58)
    for n_trials in (2, 5, 10, 20):
        out = deflated_sharpe_ratio(returns, n_trials)
        expected, sr0 = _reference_dsr(returns, n_trials)
        assert out["dsr"] == pytest.approx(expected, abs=1e-12)
        assert out["sr0"] == pytest.approx(sr0, abs=1e-14)
        assert out["reason"] == "ok"
        assert out["n_trials"] == n_trials
        assert out["T"] == 58


def test_t16_dsr_monotonic_in_n_trials():
    rng = np.random.default_rng(11)
    returns = rng.normal(0.03, 0.05, 58)
    values = [deflated_sharpe_ratio(returns, n)["dsr"]
              for n in (2, 5, 10, 20, 50)]
    for prev, cur in zip(values, values[1:]):
        assert cur <= prev + 1e-15


def test_t17_dsr_per_period_convention():
    rng = np.random.default_rng(13)
    returns = rng.normal(0.03, 0.04, 24)
    out = deflated_sharpe_ratio(returns, 3)
    expected = float(np.mean(returns) / np.std(returns, ddof=1))
    assert out["sr_per_period"] == pytest.approx(expected, abs=1e-15)
    assert out["sr_annualized"] == pytest.approx(
        expected * math.sqrt(12), abs=1e-14)
    assert out["skew"] == pytest.approx(
        stats.skew(returns, bias=False), abs=1e-14)
    assert out["kurtosis"] == pytest.approx(
        stats.kurtosis(returns, fisher=False, bias=False), abs=1e-14)


def test_t18_dsr_degenerate_inputs():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.1, 0.2, 0.3], 1)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.1, 0.2], 3)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.01, 0.01, 0.01, 0.01], 3)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.1, np.nan, 0.2], 3)


def test_t19_dsr_non_positive_denominator_branch():
    # 合法收益序列满足 Pearson 不等式（kurt >= skew^2 + 1），
    # 分母恒正；该分支只能通过内部统计量入口构造。
    out = _dsr_from_stats(
        sr=1.0, sr_variance=1.0 / 57.0, n_trials=10, t=58,
        skew=10.0, kurtosis=3.0,
    )
    assert math.isnan(out["dsr"])
    assert out["reason"] == "denominator_non_positive"


def test_t20_dsr_variance_sources():
    rng = np.random.default_rng(17)
    returns = rng.normal(0.02, 0.05, 58)
    out_null = deflated_sharpe_ratio(returns, 5)
    assert out_null["variance_source"] == "null"
    assert out_null["sr_variance"] == pytest.approx(1.0 / 57.0)

    out_explicit = deflated_sharpe_ratio(returns, 5, sr_variance=0.004)
    assert out_explicit["variance_source"] == "sr_variance"
    assert out_explicit["sr_variance"] == pytest.approx(0.004)

    trial_sharpes = [0.05, 0.10, 0.15, 0.20, 0.25]
    out_emp = deflated_sharpe_ratio(
        returns, 5, trial_sharpes=trial_sharpes)
    assert out_emp["variance_source"] == "trial_sharpes"
    assert out_emp["sr_variance"] == pytest.approx(
        float(np.var(trial_sharpes, ddof=1)))

    with pytest.raises(ValueError):
        deflated_sharpe_ratio(
            returns, 5, sr_variance=0.004, trial_sharpes=trial_sharpes)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(returns, 5, trial_sharpes=[0.1, 0.2])
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(returns, 5, sr_variance=0.0)


# ------------------------------------------------------------
# T21-T26  PBO / CSCV
# ------------------------------------------------------------

def _metric_block(data, metric):
    if metric == "mean":
        return data.mean(axis=0)
    return data.mean(axis=0) / data.std(axis=0, ddof=1)


def _pbo_bruteforce(matrix, n_blocks, metric="sharpe"):
    data = np.asarray(matrix, dtype=float)
    t, n = data.shape
    block = t // n_blocks
    blocks = [np.arange(i * block, (i + 1) * block)
              for i in range(n_blocks)]
    logs = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.setdiff1d(np.arange(t), is_idx)
        is_score = _metric_block(data[is_idx], metric)
        star = int(np.argmax(is_score))
        oos_score = _metric_block(data[oos_idx], metric)
        selected = oos_score[star]
        rank = (1
                + int(np.sum(oos_score < selected))
                + 0.5 * (int(np.sum(oos_score == selected)) - 1))
        omega = rank / (n + 1)
        logs.append(math.log(omega / (1 - omega)))
    return float(np.mean(np.asarray(logs) <= 0)), logs


def test_t21_pbo_bruteforce():
    rng = np.random.default_rng(3)
    matrix = rng.normal(size=(8, 3))
    out = probability_of_backtest_overfitting(
        matrix, n_blocks=4, return_logits=True)
    expected, logs = _pbo_bruteforce(matrix, 4)
    assert out["pbo"] == pytest.approx(expected, abs=1e-12)
    assert out["logits"] == pytest.approx(logs, abs=1e-12)
    assert out["n_splits"] == 6
    assert out["n_strategies"] == 3
    assert out["n_periods"] == 8


def test_t22_pbo_pure_noise():
    rng = np.random.default_rng(20261118)
    matrix = rng.normal(size=(56, 10))
    out = probability_of_backtest_overfitting(matrix, n_blocks=8)
    assert 0.3 <= out["pbo"] <= 0.7


def test_t23_pbo_with_skill():
    rng = np.random.default_rng(20261118)
    noise = rng.normal(size=(56, 10))
    skilled = noise.copy()
    skilled[:, 0] += 0.8
    pbo_noise = probability_of_backtest_overfitting(noise, n_blocks=8)["pbo"]
    pbo_skill = probability_of_backtest_overfitting(
        skilled, n_blocks=8)["pbo"]
    assert pbo_skill < pbo_noise


def test_t24_pbo_divisibility_and_trim():
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(rng.normal(size=(57, 4)), 8)
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(rng.normal(size=(56, 4)), 7)

    idx = np.arange(58)
    recent = idx[trim_to_divisible(58, 8, keep="recent")]
    earliest = idx[trim_to_divisible(58, 8, keep="earliest")]
    assert len(recent) == 56 and recent[0] == 2 and recent[-1] == 57
    assert len(earliest) == 56 and earliest[0] == 0 and earliest[-1] == 55
    with pytest.raises(ValueError):
        trim_to_divisible(58, 8, keep="middle")


def test_t25_pbo_tie_average_rank():
    rng = np.random.default_rng(9)
    base = rng.normal(size=(16, 2))
    matrix = np.column_stack([base[:, 0], base[:, 0], base[:, 1]])
    out = probability_of_backtest_overfitting(matrix, n_blocks=4)
    expected, _ = _pbo_bruteforce(matrix, 4)
    assert out["tie_policy"] == "average_rank"
    assert out["pbo"] == pytest.approx(expected, abs=1e-12)
    # 并列列不会改变确定性结果
    again = probability_of_backtest_overfitting(matrix, n_blocks=4)
    assert again["pbo"] == out["pbo"]


def test_t26_pbo_reproducible():
    rng = np.random.default_rng(21)
    matrix = rng.normal(size=(56, 6))
    first = probability_of_backtest_overfitting(
        matrix, n_blocks=8, return_logits=True)
    second = probability_of_backtest_overfitting(
        matrix, n_blocks=8, return_logits=True)
    assert first["pbo"] == second["pbo"]
    assert first["logits"] == second["logits"]


def test_t26b_constant_fp_slip_raises():
    """v3.7.0 复审 H1：常数序列因均值舍入 std≈1e-19>0，须显式拒绝。"""
    constant = np.full(58, 0.01)
    assert constant.std(ddof=1) > 0.0  # 复现浮点假阳性前提
    with pytest.raises(ValueError):
        sharpe_ratio(constant)
    # PBO：block 内含常数列（整列常数在每个 block 均为常数）
    rng = np.random.default_rng(23)
    matrix = np.column_stack([
        np.full(56, 0.01), rng.normal(size=56), rng.normal(size=56)])
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(matrix, n_blocks=8)
