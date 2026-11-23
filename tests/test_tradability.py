# -*- coding: utf-8 -*-
"""v3.9.0 E4（S5）：交易现实性验收（T390-27 ~ T390-35）。"""
import numpy as np
import pytest

from backtest.tradability import (
    CostModel,
    LimitRule,
    TradabilityInputs,
    TradabilityPolicy,
    _pct_matrix,
    _validate_rules,
    apply_tradability,
    board_of,
    can_trade,
    compute_limits,
    limit_price,
    rule_pct,
)


def _case(T=3, N=1, dates=None):
    dates = dates or np.array(
        ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"][:T])
    return {
        "target_w": np.zeros((T, N)),
        "prev_close": np.full((T, N), 10.0),
        "high": np.full((T, N), 10.2),
        "low": np.full((T, N), 9.8),
        "close": np.full((T, N), 10.0),
        "open_": np.full((T, N), 10.0),
        "volume": np.full((T, N), 1e6),
        "suspended": np.zeros((T, N), dtype=bool),
        "board": np.array(["main"] * N),
        "is_st": np.zeros(N, dtype=bool),
        "dates": dates,
    }


def _run(case, policy=None):
    return apply_tradability(
        case["target_w"], case["prev_close"], case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["board"], case["is_st"], case["dates"], policy)


def test_t390_27_limit_up_blocks_buy():
    case = _case()
    case["target_w"][1, 0] = 0.5
    case["high"][1, 0] = 11.0  # main 非 ST 涨停价
    eff, report = _run(case)
    assert eff[1, 0] == eff[0, 0] == 0.0
    assert report["blocked_buy"] >= 1


def test_t390_28_limit_down_blocks_sell():
    case = _case()
    case["target_w"][0, 0] = 0.5
    case["target_w"][1, 0] = 0.0
    case["low"][1, 0] = 9.0
    eff, report = _run(case)
    assert eff[0, 0] == 0.5
    assert eff[1, 0] == 0.5
    assert report["blocked_sell"] >= 1


def test_t390_29_suspend_freezes_position():
    case = _case()
    case["target_w"][0, 0] = 0.5
    case["target_w"][1, 0] = 0.0
    case["suspended"][1, 0] = True
    eff, report = _run(case)
    assert eff[1, 0] == 0.5
    assert report["blocked_suspend"] >= 1


def test_t390_30_t_plus_1_lock():
    case = _case(T=3)
    case["target_w"][0, 0] = 0.5
    case["high"][0, 0] = 11.0          # 首日涨停 → 挂起
    case["target_w"][1, 0] = 0.0       # 次日开板：补成交后同日报卖 → T+1 拒绝
    eff, report = _run(case)
    assert report["deferred"] >= 1     # 买侧补成交（次日卖出缺口另计）
    assert report["t1_locked"] >= 1
    assert eff[1, 0] == 0.5
    assert eff[2, 0] == 0.0


def test_t390_31_rule_versioning():
    assert rule_pct("main", True, "2026-07-03") == pytest.approx(0.05)
    assert rule_pct("main", True, "2026-07-05") == pytest.approx(0.05)
    assert rule_pct("main", True, "2026-07-06") == pytest.approx(0.10)
    assert rule_pct("gem", True, "2020-08-23") == pytest.approx(0.05)
    assert rule_pct("gem", True, "2020-08-24") == pytest.approx(0.20)
    assert rule_pct("star", False, "2022-01-04") == pytest.approx(0.20)
    assert rule_pct("bse", False, "2022-01-04") == pytest.approx(0.30)


def test_t390_32_limit_price_rounding():
    assert limit_price(10.00, 0.10, "up") == pytest.approx(11.00)
    assert limit_price(10.00, 0.10, "down") == pytest.approx(9.00)
    assert limit_price(3.33, 0.10, "up") == pytest.approx(3.66)
    assert limit_price(3.33, 0.10, "down") == pytest.approx(3.00)
    with pytest.raises(ValueError):
        limit_price(10.0, 0.10, "sideways")


def test_t390_33_cost_separation():
    model = CostModel()
    buy_only = model.cost(1e6, 0.0)
    sell_only = model.cost(0.0, 1e6)
    assert buy_only["stamp_tax"] == 0.0
    assert sell_only["stamp_tax"] == pytest.approx(500.0)   # 5bp × 1e6
    assert buy_only["transfer_fee"] == pytest.approx(10.0)  # 0.1bp × 1e6
    assert sell_only["total"] - buy_only["total"] == pytest.approx(500.0)
    assert buy_only["commission"] == pytest.approx(250.0)   # 2.5bp
    with pytest.raises(ValueError):
        model.cost(-1.0, 0.0)
    with pytest.raises(ValueError):
        model.cost(float("nan"), 0.0)


def test_t390_34_deferred_fill_after_two_limits():
    case = _case(T=3)
    case["target_w"][:, 0] = 0.5
    case["high"][0, 0] = 11.0
    case["high"][1, 0] = 11.0
    eff, report = _run(case)
    assert report["blocked_buy"] == 2
    assert report["deferred"] == 1
    assert eff[1, 0] == 0.0
    assert eff[2, 0] == 0.5


def test_t390_35_rule_miss_and_overlap():
    with pytest.raises(ValueError):
        rule_pct("main", False, "1990-01-01")
    with pytest.raises(ValueError):
        rule_pct("gem", False, "2001-01-01")
    overlap = (
        LimitRule("main", False, 0.10, "2020-01-01", "2021-12-31"),
        LimitRule("main", False, 0.20, "2021-06-01"),
    )
    with pytest.raises(ValueError):
        _validate_rules(overlap)


# =============================================================================
# P-006 Step 9：TP6 系列（限价取整 / 板块映射 / 除权参考价 / 桶优先级）
# =============================================================================

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def _report_keys():
    return {"blocked_buy", "blocked_sell", "blocked_suspend", "t1_locked",
            "deferred", "carried", "limit_unknown", "one_word_up",
            "one_word_down"}


def test_tp6_1_tie_directed():
    """TP6-1: tie 定向（10.25 down 对 np.round 有区分度）。"""
    assert limit_price(10.25, 0.10, "up") == pytest.approx(11.28)
    assert limit_price(10.25, 0.10, "down") == pytest.approx(9.23)
    assert limit_price(3.33, 0.10, "up") == pytest.approx(3.66)
    assert limit_price(3.33, 0.10, "down") == pytest.approx(3.00)


def test_tp6_2_decimal_half_up_property():
    """TP6-2: 整数分生成价 × 4 档，与 Decimal(ROUND_HALF_UP) 逐值相等。"""
    prices = np.arange(100, 2601) / 100.0        # 1.00 ~ 26.00，2501 个
    total = 0
    for pct in (0.05, 0.10, 0.20, 0.30):
        for side, sign in (("up", 1), ("down", -1)):
            got = limit_price(prices, pct, side)
            pct_d = Decimal(str(pct))
            for prev, value in zip(prices, got):
                expected = float(
                    (Decimal(str(prev)) * (Decimal(1) + sign * pct_d))
                    .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                assert value == expected, (prev, pct, side, value, expected)
                total += 1
    assert total >= 10000

    # NaN 掩码：NaN 入 → NaN 出（无整型下溢）
    arr = limit_price(np.array([10.0, np.nan, 3.33]), 0.10, "up")
    assert arr[0] == pytest.approx(11.0)
    assert np.isnan(arr[1])
    assert arr[2] == pytest.approx(3.66)

    # 返回形态
    assert isinstance(limit_price(10.0, 0.10), float)
    assert isinstance(limit_price(np.array([10.0]), 0.10), np.ndarray)

    # pct 越界
    with pytest.raises(ValueError):
        limit_price(10.0, 1.5)
    with pytest.raises(ValueError):
        limit_price(10.0, -0.1)

    # 静态禁用 np.round / np.rint
    src = (Path(__file__).resolve().parents[1]
           / "backtest" / "tradability.py").read_text(encoding="utf-8")
    assert "np.round(" not in src
    assert "np.rint(" not in src


def test_tp6_3_three_branches():
    """TP6-3: 差额 <1 分 → ±1 分；限价 <1 分 → 1 分。"""
    assert limit_price(0.01, 0.10, "up") == pytest.approx(0.02)
    assert limit_price(0.01, 0.10, "down") == pytest.approx(0.01)
    assert limit_price(0.09, 0.10, "up") == pytest.approx(0.10)
    assert limit_price(0.09, 0.10, "down") == pytest.approx(0.08)
    assert limit_price(0.10, 0.10, "up") == pytest.approx(0.11)
    assert limit_price(0.10, 0.10, "down") == pytest.approx(0.09)
    with pytest.raises(ValueError):
        limit_price(10.0, 0.10, side="flat")


def test_tp6_5_board_of_prefixes():
    """TP6-5: 板块区间映射，未映射 → unknown（无默认 main）。"""
    for code in ("600000", "601398", "603000", "605001",
                 "000001", "001001", "002499", "003816", "004000"):
        assert board_of(code) == "main", code
    for code in ("300001", "301001", "302132", "309999"):
        assert board_of(code) == "gem", code
    for code in ("688009", "689009"):
        assert board_of(code) == "star", code
    for code in ("430047", "830799", "870001", "920001"):
        assert board_of(code) == "bse", code
    for code in ("900001", "200001", "abc", "", "60000"):
        assert board_of(code) == "unknown", code
    assert board_of(600000) == "main"
    assert board_of("600000.SH") == "main"
    assert board_of("302132.SZ") == "gem"


def test_tp6_6_ex_dividend_ref():
    """TP6-6: 除权参考价 ref = prev × adj[t-1]/adj[t]（TP6-7 构造性覆盖 apply 侧）。"""
    up, down, unk = compute_limits(10.0, 0.10, ref=5.0)
    assert not unk
    assert up == pytest.approx(5.50)
    assert down == pytest.approx(4.50)

    # 非除权日 ref==prev：与不传 ref 逐值一致
    up0, down0, unk0 = compute_limits(10.0, 0.10)
    up1, down1, _ = compute_limits(10.0, 0.10, ref=10.0)
    assert up0 == up1 and down0 == down1 and not unk0

    # apply 侧：prev=10, adj_prev/adj_t = 0.5 → ref=5 → high=5.5 封板
    case = _case(T=3)
    case["prev_close"] = np.array([[np.nan], [10.0], [10.0]])
    case["high"][1, 0] = 5.50
    case["low"][1, 0] = 4.50
    case["adj"] = np.array([[2.0], [4.0], [4.0]])
    case["target_w"][1, 0] = 0.5
    eff, report = apply_tradability(
        case["target_w"], case["prev_close"], case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["board"], case["is_st"], case["dates"],
        adj=case["adj"])
    assert report["blocked_buy"] == 1
    assert eff[1, 0] == 0.0
    assert eff[2, 0] == 0.5          # 非除权日 ref=prev=10，high=5.5 不封板


def test_tp6_7_apply_adj_single_side_missing():
    """TP6-7（apply 侧）：adj 单侧缺失 → limit_unknown，blocked 不增加。"""
    case = _case(T=3)
    case["prev_close"] = np.array([[np.nan], [10.0], [10.0]])
    case["high"][2, 0] = 11.0
    case["adj"] = np.array([[2.0], [2.0], [np.nan]])   # t=1 有限、t=2 NaN
    case["target_w"][2, 0] = 0.5
    eff, report = apply_tradability(
        case["target_w"], case["prev_close"], case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["board"], case["is_st"], case["dates"], adj=case["adj"])
    assert report["limit_unknown"] == 1
    assert report["blocked_buy"] == 0
    assert eff[2, 0] == 0.5           # 不可判定 → 不阻塞（未知即放行并计数）
    assert set(report) == _report_keys()
    assert all(type(v) is int for v in report.values())


def test_tp6_8_apply_st_vs_delisting_and_no_limit():
    """TP6-8（apply 侧）：退市不走 ST 5%；无限制日不判封板。"""
    base = _case(T=2)
    base["prev_close"] = np.array([[np.nan], [10.0]])
    base["high"][1, 0] = 10.50        # ST 5% 涨停价
    base["target_w"][1, 0] = 0.5

    eff_st, rep_st = apply_tradability(
        base["target_w"], base["prev_close"], base["high"], base["low"],
        base["close"], base["open_"], base["volume"], base["suspended"],
        base["board"], np.array([True]), base["dates"])
    assert rep_st["blocked_buy"] == 1 and eff_st[1, 0] == 0.0

    eff_del, rep_del = apply_tradability(
        base["target_w"], base["prev_close"], base["high"], base["low"],
        base["close"], base["open_"], base["volume"], base["suspended"],
        base["board"], np.array([True]), base["dates"],
        is_delisting=np.array([True]))
    assert rep_del["blocked_buy"] == 0 and eff_del[1, 0] == 0.5

    no_limit = np.zeros((2, 1), dtype=bool)
    no_limit[1, 0] = True
    eff_nl, rep_nl = apply_tradability(
        base["target_w"], base["prev_close"], base["high"], base["low"],
        base["close"], base["open_"], base["volume"], base["suspended"],
        base["board"], np.array([True]), base["dates"],
        no_limit=no_limit)
    assert rep_nl["blocked_buy"] == 0 and eff_nl[1, 0] == 0.5


def test_tp6_12_low_price_st_equivalence():
    """TP6-12: 低价 ST 显式分支 == 通用三分支（逐值）。"""
    for cents in range(1, 10):
        prev = cents / 100.0
        up_st, down_st, unk_st = compute_limits(prev, 0.05, is_st=True)
        up_gen, down_gen, unk_gen = compute_limits(prev, 0.05, is_st=False)
        assert not unk_st and not unk_gen
        assert up_st == up_gen and down_st == down_gen, cents


def test_report_bucket_priority():
    """INV-5：16 组合（suspended × no_limit × unknown × blocked）单桶互斥。"""
    combos = [(susp, nolim, unk, block)
              for susp in (False, True)
              for nolim in (False, True)
              for unk in (False, True)
              for block in (False, True)]
    T, N = 1, len(combos)
    target = np.full((T, N), 0.5)
    prev = np.full((T, N), 10.0)
    high = np.full((T, N), 10.0)
    low = np.full((T, N), 9.0)
    susp = np.zeros((T, N), dtype=bool)
    no_limit = np.zeros((T, N), dtype=bool)
    board = np.array(["main"] * N, dtype=object)
    expect = {"blocked_suspend": 0, "limit_unknown": 0, "blocked_buy": 0}
    free = np.zeros(N, dtype=bool)
    for j, (is_susp, is_nolim, is_unk, is_block) in enumerate(combos):
        susp[0, j] = is_susp
        no_limit[0, j] = is_nolim
        board[j] = "unknown" if is_unk else "main"
        high[0, j] = 11.0 if is_block else 10.0
        if is_susp:
            expect["blocked_suspend"] += 1
        elif is_nolim:
            free[j] = True
        elif is_unk:
            expect["limit_unknown"] += 1
            free[j] = True            # 不可判定 → 不阻塞（仅计数）
        elif is_block:
            expect["blocked_buy"] += 1
        else:
            free[j] = True
    eff, report = apply_tradability(
        target, prev, high, low, prev, prev, np.full((T, N), 1e6), susp,
        board, np.zeros((T, N), dtype=bool), np.array(["2026-01-05"]),
        no_limit=no_limit)
    assert len(combos) == 16
    for key, value in expect.items():
        assert report[key] == value, (key, report[key], value)
    assert set(report) == _report_keys()
    assert np.array_equal(eff[0] == 0.5, free)
    # 单桶互斥：每格至多入一桶 = 4 类计数之和 <= 16
    assert sum(report[k] for k in expect) <= 16


def test_is_st_2d_supported():
    """is_st (T,N) 逐日形态。"""
    T, N = 2, 1
    target = np.array([[0.0], [0.5]])
    prev = np.array([[np.nan], [10.0]])
    high = np.array([[10.0], [10.5]])
    low = np.array([[9.8], [9.8]])
    eff, report = apply_tradability(
        target, prev, high, low, np.full((T, N), 10.0), np.full((T, N), 10.0),
        np.full((T, N), 1e6), np.zeros((T, N), dtype=bool),
        np.array(["main"]), np.array([[False], [True]]),
        np.array(["2026-01-05", "2026-01-06"]))
    assert report["blocked_buy"] == 1
    assert eff[1, 0] == 0.0


def test_eps_two_readings_u6():
    """U-6 残余：eps=0 与 eps=1 tick 两档封板读数并列。"""
    T, N = 1, 1
    target = np.array([[0.5]])
    prev = np.array([[10.0]])
    high = np.array([[10.999]])
    low = np.array([[9.8]])
    args = (target, prev, high, low, prev, prev, np.full((T, N), 1e6),
            np.zeros((T, N), dtype=bool), np.array(["main"]),
            np.zeros((T, N), dtype=bool), np.array(["2026-01-05"]))
    _, rep0 = apply_tradability(*args, policy=TradabilityPolicy(eps=0.0))
    _, rep1 = apply_tradability(*args, policy=TradabilityPolicy(eps=0.01))
    assert (rep0["blocked_buy"], rep1["blocked_buy"]) == (0, 1)


def test_empty_panel_report_zero():
    """INV-9：空面板 9 键全 0（int）。"""
    _, report = apply_tradability(
        np.zeros((0, 0)), np.zeros((0, 0)), np.zeros((0, 0)),
        np.zeros((0, 0)), np.zeros((0, 0)), np.zeros((0, 0)),
        np.zeros((0, 0)), np.zeros((0, 0), dtype=bool), np.array([]),
        np.zeros((0, 0), dtype=bool), np.array([]))
    assert set(report) == _report_keys()
    assert all(v == 0 and type(v) is int for v in report.values())


def test_error_table_contracts():
    """CHECKLIST §5 错误表逐行契约。"""
    empty = np.zeros((2, 1))

    def kwargs(**over):
        base = dict(target_w=empty, prev_close=np.array([[np.nan], [10.0]]),
                    high=empty + 10.0, low=empty + 9.8, close=empty + 10.0,
                    open_=empty + 10.0, volume=empty + 1e6,
                    suspended=np.zeros((2, 1), dtype=bool),
                    board=np.array(["main"]), is_st=np.zeros(1, dtype=bool),
                    dates=np.array(["2026-01-05", "2026-01-06"]))
        base.update(over)
        return base

    with pytest.raises(ValueError):
        apply_tradability(**kwargs(dates=np.array(["2026-01-05"])))
    with pytest.raises(ValueError):
        apply_tradability(**kwargs(board=np.array(["mainx"])))
    with pytest.raises(ValueError):
        compute_limits(10.0, 1.5)

    # high/low NaN：无封板证据，不抛错、不 block
    nan_high = np.array([[np.nan], [np.nan]])
    eff, report = apply_tradability(
        **kwargs(target_w=np.array([[0.0], [0.5]]), high=nan_high,
                 low=nan_high))
    assert report["blocked_buy"] == 0 and eff[1, 0] == 0.5

    # prev NaN + 停牌 → blocked_suspend（而非 limit_unknown）
    _, report = apply_tradability(
        **kwargs(target_w=np.array([[0.5], [0.0]]),
                 suspended=np.array([[True], [False]])))
    assert report["blocked_suspend"] == 1
    assert report["limit_unknown"] == 0

    # BSE 2020-07-27 前：规则 gap → 不抛错（P-021 D3 / O-9 解阻断）
    pct, gap = _pct_matrix(np.array(["bse"]),
                           np.zeros((2, 1), dtype=bool), None,
                           np.array(["2020-01-06", "2020-01-07"]),
                           return_gaps=True)
    assert gap.all() and np.isnan(pct).all()
    _, report = apply_tradability(
        **kwargs(target_w=np.array([[0.0], [0.5]]), board=np.array(["bse"]),
                 dates=np.array(["2020-01-06", "2020-01-07"])))
    assert report["limit_unknown"] >= 1


# ---------------------------------------------------------------------------
# P-020（T020-1a/1b/2）
# ---------------------------------------------------------------------------

def test_t020_1a_one_word_up_count():
    """T020-1a：一字涨停正向计数（单向，down 必须为 0）。"""
    case = _case(T=2)
    case["high"][1, 0] = 11.0          # main 非 ST 涨停价
    case["low"][1, 0] = 11.0
    _, report = _run(case)
    assert report["one_word_up"] == 1
    assert report["one_word_down"] == 0


def test_t020_1b_one_word_down_count():
    """T020-1b：一字跌停正向计数（单向，up 必须为 0）。"""
    case = _case(T=2)
    case["high"][1, 0] = 9.0           # main 非 ST 跌停价
    case["low"][1, 0] = 9.0
    _, report = _run(case)
    assert report["one_word_down"] == 1
    assert report["one_word_up"] == 0


def test_t020_2_ref_direct_path():
    """T020-2：`ref=` 直传分支（无 adj），与 TP6-6 经 adj 派生同结果。"""
    case = _case(T=2)
    case["prev_close"] = np.array([[np.nan], [10.0]])
    case["high"][1, 0] = 5.50
    case["low"][1, 0] = 4.50
    case["target_w"][1, 0] = 0.5
    ref = np.array([[np.nan], [5.0]])
    eff, report = apply_tradability(
        case["target_w"], case["prev_close"], case["high"], case["low"],
        case["close"], case["open_"], case["volume"], case["suspended"],
        case["board"], case["is_st"], case["dates"], ref=ref)
    assert report["blocked_buy"] == 1
    assert report["limit_unknown"] == 0
    assert eff[1, 0] == 0.0
