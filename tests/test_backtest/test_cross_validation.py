# -*- coding: utf-8 -*-
"""v3.7.0 E1 — 样本外协议测试（T01-T14b，16 项）。

对应 ``docs/EXECUTION_V3.7.0_STAT_EVIDENCE_CHAIN.md`` §4.1 与
``docs/private/DESIGN_STAT_EVIDENCE_CHAIN.md`` §4。
"""
import numpy as np
import pandas as pd
import pytest

from backtest.cross_validation import (
    CombinatorialPurgedKFold,
    HoldoutRegistry,
    HoldoutRegistryError,
    HoldoutReuseError,
    PurgedKFold,
    require_locked,
)


# ------------------------------------------------------------
# T01-T04  PurgedKFold
# ------------------------------------------------------------

def test_t01_purged_kfold_basic():
    cv = PurgedKFold(n_splits=5, purge=1, embargo=1, label_horizon=1)
    splits = list(cv.split(20))
    assert len(splits) == 5
    covered = np.zeros(20, dtype=int)
    for train, test in splits:
        assert train.dtype == np.int64
        assert test.dtype == np.int64
        assert len(np.intersect1d(train, test)) == 0
        # 测试折连续
        assert np.array_equal(test, np.arange(test[0], test[-1] + 1))
        covered[test] += 1
    assert np.array_equal(np.where(covered == 1)[0], np.arange(20))


def test_t02_purge_conservative():
    # n_splits=4 -> 每折 5 期；第 2 折 test=[5,9]，a=5
    cv = PurgedKFold(n_splits=4, purge=0, embargo=0, label_horizon=1)
    train, test = list(cv.split(20))[1]
    assert test[0] == 5 and test[-1] == 9
    assert (5 - 1) not in train
    assert (5 - 2) in train


def test_t03_embargo():
    cv = PurgedKFold(n_splits=4, purge=0, embargo=2, label_horizon=1)
    train, test = list(cv.split(20))[0]
    b = int(test[-1])
    assert b == 4
    assert (b + 1) not in train
    assert (b + 2) not in train
    assert (b + 3) in train


def test_t04_parameter_validation():
    with pytest.raises(ValueError):
        PurgedKFold(n_splits=1)
    with pytest.raises(ValueError):
        PurgedKFold(n_splits=5, purge=-1)
    with pytest.raises(ValueError):
        PurgedKFold(n_splits=5, embargo=-1)
    with pytest.raises(ValueError):
        PurgedKFold(n_splits=5, label_horizon=0)
    # T 太小：T < n_splits + purge + embargo + label_horizon
    cv = PurgedKFold(n_splits=5, purge=1, embargo=1, label_horizon=1)
    with pytest.raises(ValueError):
        list(cv.split(3))


# ------------------------------------------------------------
# T05-T08  CombinatorialPurgedKFold
# ------------------------------------------------------------

def test_t05_cpcv_path_count():
    cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2,
                                  purge=1, embargo=1, label_horizon=1)
    assert cv.n_paths == 15
    assert cv.split_id == "cpcv_n6_k2_p1_e1_h1"
    assert len(list(cv.split(60))) == 15


def test_t06_cpcv_non_contiguous_test_blocks():
    cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2,
                                  purge=0, embargo=0, label_horizon=1)
    groups = cv.split_groups(24)          # 每组 4 期
    target = np.union1d(groups[0], groups[2])
    train = None
    for tr, te, _ in cv.split(24):
        if np.array_equal(te, target):
            train = tr
            break
    assert train is not None
    # 第 0 组 [0..3]，第 2 组 [8..11]
    # 段间训练样本保留：第 1 组的 5、6 在训练集中
    assert 5 in train and 6 in train
    # 第 2 组起点前 purge 1 期：7 被剔除
    assert 7 not in train
    # 两个测试段均不在训练集
    assert len(np.intersect1d(train, target)) == 0


def test_t07_cpcv_deterministic():
    cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2)
    first = [(tr.copy(), te.copy(), pid) for tr, te, pid in cv.split(54)]
    second = [(tr.copy(), te.copy(), pid) for tr, te, pid in cv.split(54)]
    assert len(first) == len(second) == 15
    for (a_tr, a_te, a_id), (b_tr, b_te, b_id) in zip(first, second):
        assert a_id == b_id
        assert np.array_equal(a_tr, b_tr)
        assert np.array_equal(a_te, b_te)


def test_t08_cpcv_validation():
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_groups=6, n_test_groups=6)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_groups=1, n_test_groups=1)
    with pytest.raises(ValueError):
        CombinatorialPurgedKFold(n_groups=6, n_test_groups=0)
    cv = CombinatorialPurgedKFold(n_groups=6, n_test_groups=2)
    with pytest.raises(ValueError):
        list(cv.split(5))


# ------------------------------------------------------------
# T09-T14b  HoldoutRegistry
# ------------------------------------------------------------

def _registry(tmp_path, enable=True):
    return HoldoutRegistry(db_path=str(tmp_path / "holdout.duckdb"),
                           enable=enable)


def test_t09_holdout_lock(tmp_path):
    reg = _registry(tmp_path)
    hid = reg.lock(
        start="2025-01-31", end="2025-12-31",
        universe_version="all_a_share_v1", batch_id="batch_a",
    )
    assert isinstance(hid, str) and len(hid) == 64
    rec = reg.check(hid)
    assert set(rec) == {
        "holdout_id", "start", "end", "universe_version", "batch_id",
        "locked_at", "price_convention", "return_convention", "note",
    }
    assert rec["locked_at"]
    assert rec["price_convention"] == "hfq"
    assert rec["return_convention"] == "monthly_next"
    # require_locked 回调
    checker = require_locked(reg)
    checker(hid, "batch_a")
    with pytest.raises(HoldoutReuseError):
        checker(hid, "batch_b")


def test_t10_holdout_idempotent(tmp_path):
    reg = _registry(tmp_path)
    kwargs = dict(start="2025-01-31", end="2025-12-31",
                  universe_version="all_a_share_v1", batch_id="batch_a")
    first = reg.lock(**kwargs)
    second = reg.lock(**kwargs)
    assert first == second
    assert len(reg.list_locks()) == 1


def test_t11_holdout_cross_batch_rejected(tmp_path):
    reg = _registry(tmp_path)
    reg.lock(start="2025-01-31", end="2025-12-31",
             universe_version="all_a_share_v1", batch_id="batch_a")
    with pytest.raises(HoldoutReuseError):
        reg.lock(start="2025-01-31", end="2025-12-31",
                 universe_version="all_a_share_v1", batch_id="batch_b")


def test_t12_holdout_overlap_rejected(tmp_path):
    reg = _registry(tmp_path)
    reg.lock(start="2025-01-31", end="2025-12-31",
             universe_version="all_a_share_v1", batch_id="batch_a")
    with pytest.raises(HoldoutReuseError):
        reg.lock(start="2025-06-30", end="2026-06-30",
                 universe_version="all_a_share_v1", batch_id="batch_b")


def test_t12b_holdout_multi_universe(tmp_path):
    reg = _registry(tmp_path)
    first = reg.lock(start="2025-01-31", end="2025-12-31",
                     universe_version="universe_a", batch_id="batch_a")
    second = reg.lock(start="2025-01-31", end="2025-12-31",
                      universe_version="universe_b", batch_id="batch_a")
    assert first != second
    assert len(reg.list_locks()) == 2
    # 同 batch 不同 start/end 且重叠 → 拒绝
    with pytest.raises(HoldoutReuseError):
        reg.lock(start="2025-02-28", end="2025-12-31",
                 universe_version="universe_c", batch_id="batch_a")


def test_t13_holdout_dev_mask(tmp_path):
    reg = _registry(tmp_path)
    hid = reg.lock(start="2025-01-31", end="2025-12-31",
                   universe_version="all_a_share_v1", batch_id="batch_a")
    dates = [d.strftime("%Y-%m-%d") for d in
             pd.date_range("2020-02-29", "2026-01-31", freq="M")]
    mask = reg.dev_mask(dates, hid)
    assert mask.dtype == bool
    by_date = dict(zip(dates, mask.tolist()))
    assert by_date["2024-11-30"] is True
    assert by_date["2024-12-31"] is False
    assert by_date["2025-01-31"] is False
    assert by_date["2025-12-31"] is False
    assert by_date["2026-01-31"] is False
    assert int(mask.sum()) == 58
    # holdout_id=None → 全 True（回顾性研究）
    assert reg.dev_mask(dates, None).all()


def test_t14_holdout_disabled(tmp_path):
    reg = _registry(tmp_path, enable=False)
    with pytest.raises(HoldoutRegistryError):
        reg.lock(start="2025-01-31", end="2025-12-31",
                 universe_version="u", batch_id="b")
    with pytest.raises(HoldoutRegistryError):
        reg.check("x" * 64)
    with pytest.raises(HoldoutRegistryError):
        reg.dev_mask(["2025-01-31"], None)


def test_t14b_assert_locked_before(tmp_path):
    reg = _registry(tmp_path)
    hid = reg.lock(start="2025-01-31", end="2025-12-31",
                   universe_version="u", batch_id="b",
                   locked_at="2026-01-01T00:00:00+00:00")
    with pytest.raises(HoldoutRegistryError):
        reg.assert_locked_before(hid, "2025-12-31T00:00:00+00:00")
    reg.assert_locked_before(hid, "2026-01-01T00:00:00+00:00")
    reg.assert_locked_before(hid, "2026-06-01T00:00:00+00:00")
