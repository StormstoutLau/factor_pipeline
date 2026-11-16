# EXECUTION — 组合层 IC/Sharpe 回测

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 中任务 (步骤 1-2-3-4-5-6-9-10)
> **上游**: [RESEARCH](../research/RESEARCH_PORTFOLIO_BACKTEST.md) (F1-F14/Q1-Q5) /
> [DESIGN](private/DESIGN_PORTFOLIO_BACKTEST.md) (G1-G13)
> **性质**: 新增离线实证脚本 + 分析报告; **生产代码零改动**; 版本仍 **3.4.13**;
> 缓存代际 `v2.3.0-cache` 不变

---

## §1 实施范围

| 项 | 内容 |
|----|------|
| 新增 | `scripts/verify_portfolio_backtest.py` (~430 行) |
| 新增 | `docs/analysis/PORTFOLIO_BACKTEST_VERIFICATION.md` (运行结果) |
| 新增 | `docs/audit/PORTFOLIO_BACKTEST_AUDIT.md` (步骤 10) |
| 修改 | `docs/PROJECT_STATUS.md` (P1 #1 状态) / `CHANGELOG.md` (分析记录) |
| 不动 | `modules/` / `backtest/` / 版本锚点 / 测试套件 |

---

## §2 代码结构

```python
# ── 常量 ────────────────────────────────────────────────
FACTORS = ['turnover_1m', 'reversal_1w', 'volatility_1m', 'max_ret_1m']
Q = 5
FEE_BPS = (0, 10, 20, 30)
POOLS = {'all': None, 'hs300': '000300'}
SEGMENTS = {'full': None, 'S1': (2020-02, 2022-12), 'S2': (2023-01, 2025-12)}
MIN_POOL_STOCKS = 250
NW_LAG = 3

# ── 数据层 ──────────────────────────────────────────────
load_index_members(root, code)   -> Series[date -> frozenset]
align_pool(members, month_idx, columns) -> DataFrame[bool]   # ≤月末最后交易日

# ── 组合层 ──────────────────────────────────────────────
build_quantile_weights(f, r, q)  -> {Qk: DataFrame[T,N]}
    valid = f.notna() & r.notna()
    ranks = f.where(valid).rank(axis=1, pct=True)
    labels = np.ceil(ranks * q)
    Qk = (labels == k) / count_k      # 空分位 → 全 0

portfolio_return(w, r)           -> Series[T]   # (w * r.fillna(0)).sum(axis=1)
build_turnover(w)                -> ndarray[T]  # [0.5*Σ|w0|] + compute_turnover(w)

# ── 指标层 ──────────────────────────────────────────────
nw_t(x, lag)                     # Bartlett 核, 自建
max_drawdown(x)                  # 复利净值, 自建
perf(x, turnover, fee_bps)       # 复用 compute_spread(x)*√12
    -> {ann_ret, ann_vol, sharpe, nw_t, maxdd, hit_rate, turnover_ann, n_months}

# ── 流程 ────────────────────────────────────────────────
run_combo(name, f_z, r, pool, fee_list) -> rows
    w = build_quantile_weights(f_pool, r, Q)
    ls_ret = portfolio_return(w['Q5'] - w['Q1'], r)
    lo_ret = portfolio_return(w['Q5'], r)
    bench  = r.where(pool).mean(axis=1)
    ...
main() -> 表 + V1-V10 断言 + JSON
```

### 2.1 关键实现要点

| # | 要点 |
|---|------|
| I1 | 因子 z-score 走 `cross_section_prep(panel, ret_m, mask_m)[0]` — **全市场一次** (G13) |
| I2 | 池 B 仅 `f_z.where(pool_B)` 后再分位, 不重跑 thin mask |
| I3 | `r` 全程用 C 脚本的 `ret_m` (同行对齐 + \|r\|>1 剔除), 不重算 |
| I4 | 权重只在 `f.notna() & r.notna()` 上分配; `r.fillna(0)` 仅在求和时使用 |
| I5 | 首期建仓换手显式插入 (`0.5*Σ|w_0|`), 使净值第 1 期即含成本 |
| I6 | 复合因子 = 4 个 z 面板 `np.nanmean(stack, axis=0)` |
| I7 | 子区间 slice 后**重跑**整条组合指标链 (G10) |
| I8 | `PremiumEstimator(bandwidth=12).estimate_with_errors` 只用于 V5 符号校验 |

---

## §3 断言实现

| # | 代码位置 | 实现 |
|---|---------|------|
| V1 | `main` 入口 | `f.index.equals(r.index)`; `r.iloc[-1].isna().all()` |
| V2 | `build_quantile_weights` | 多头 `row_sum ∈ {0,1}`; 多空 `abs(row_sum) < 1e-12` |
| V3 | 同上 | `(w >= 0).all()`; 多空正侧/负侧符号 |
| V4 | `perf` | `nav[0] ≈ 1 + net[0]`; `len(nav) == len(x)` |
| V5 | `main` | 4 因子 `sign(mean IC) == sign(premium_mean)` |
| V6 | `main` | 同组合 fee 升序 → 净年化 `diff <= 1e-12` |
| V7 | `main` | `ann(Q1) <= ann(Q3) <= ann(Q5)` — WARN |
| V8 | `main` | `sharpe(composite) >= min(sharpe_i)` — WARN |
| V9 | `build_turnover` | 多头 `0 <= t <= 1`; 多空 `0 <= t <= 2` |
| V10 | `align_pool` | 池 B 每月 `(pool & r.notna()).sum() >= 250` |

---

## §4 验收命令

```powershell
python scripts/verify_portfolio_backtest.py --json out/portfolio_backtest.json
```

**预期**: 5 因子 × 2 池 × 4 费率 × 3 区间 表格输出; V1-V10 全绿 (V7/V8 允许 WARN);
JSON 含 `factor × pool × fee × segment` 全量指标; 运行 < 120s。

---

## §5 兼容与影响

| 维度 | 结论 |
|------|------|
| 生产代码 / 公开 API | 零改动 |
| 版本号 / 缓存代际 | 3.4.13 / `v2.3.0-cache` (均不变) |
| 依赖 | 无新增 |
| 测试套件 | 不新增 pytest 用例 (脚本内断言即验收); 全量回归不受影响 |
| 数据产物 | 仅 `out/*.json` (gitignore 之外的可选输出) |

---

## §6 步骤 6 review 记录 (实施后回填)

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | G1-G13 与代码一致 | ✅ 逐项见 [审计 Phase 2](audit/PORTFOLIO_BACKTEST_AUDIT.md) |
| A2 | V1-V10 断言均已实现 | ✅ 首次运行即 V1-V6/V9/V10 全绿; V7/V8 WARN 8 条 (真实分位结构) |
| A3 | 无 `.shift(-1)` 误用 (同行对齐) | ✅ 脚本内无 `shift`; 收益面板直接复用 C 的 `ret_m` |
| A4 | 首期建仓成本计入 | ✅ `build_turnover` 首期 `0.5*Σ\|w0\|` |
| A5 | 池 B 未被 thin mask 误杀 (G13) | ✅ z-score 全市场一次; 池 B 最小有效成分 294 ≥ 250 |
| A6 | 子区间 slice 后指标重算 | ✅ `SEGMENTS` 循环内独立 `run_block` |
| A7 | 盈亏平衡解析解与四档费率一致 | ✅ 如 `turnover_1m`: 13.82% / (2×0.6133×12/1e4) = 93.9bp ≈ 报告 94bp |
| A8 | JSON 可复现 (固定输入 → 指标逐位相同) | ✅ 两次运行 (IC 修正前后) 的 LS/多头指标逐位一致 |

**review 结论**: PASS。

---

## §7 实施记录

| 项 | 结果 |
|----|------|
| 脚本行数 | 420 行 |
| 首次运行 | 退出码 0; V1-V6/V9/V10 全绿; 发现 D1 (两池 IC 相同, 口径错) |
| 修正后运行 | 退出码 0; 全断言通过; hs300 IC 0.0841 → 0.0565 (`turnover_1m`) |
| 实施期缺陷 | D1 IC 口径 (运行后) / D2 V10 边界·D3 死表达式·D4 dict 合并 (静态自查) / D5 thin mask (设计 review) |
| 运行时长 | 约 40s (数据加载为主) |
| 关键数值 (池 all / full / fee=0) | LS 年化 11.2%-16.1%, SR 0.77-1.05, NW t 2.41-3.04; 多头超额 -0.6%~+1.3% (t ≤0.48) |
| 中间产物 | `out/*.json` 已删除, 不入库 |

---

## §8 异构复审记录 (5 视角 × 8 探针, 2026-11-16)

> 方法: 异构复审 — 计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性 5 视角攻击式探针;
> 探针脚本为临时文件, 用后删除, 证据并入本节、
> [审计 Phase 8](audit/PORTFOLIO_BACKTEST_AUDIT.md) 与 [报告 §3.2/§3.3/§8/§9](analysis/PORTFOLIO_BACKTEST_VERIFICATION.md)。

### 8.1 探针结果 (P1-P8)

| # | 探针 (攻击面) | 结果 | 视角 |
|---|--------------|------|------|
| P1 | Q1 断崖是否为小市值马甲 | Q1 偏小市值 (Δlog(mv) 至 -0.88), Q1 月收益与小盘组 ρ=0.85-0.89 — **时序共动** | 计量推断 |
| P2 | 涨跌停可成交性 | 空头端 23.5-26.8% 权重为月跌 ≥9.5% 股票; 多头端 13.7-21.0% 涨停股 | 结论效度 |
| P3 | 停牌 stale price (r≈0) | Q1 内占比仅 0.3-0.4% — 无实质影响 | 数据质量 |
| P4 | NW t 自实现对拍 statsmodels HAC | **逐位一致** (diff=0) | 可复现性 |
| P5 | 前视反向验证 | IC(过去收益) 为负且强 1.7-8.9 倍 (reversal -0.41 vs 未来 +0.046) — 无前视 | 计量推断 |
| P6 | 多头超额基准敏感性 | vs 剔 Q1 池等权: 超额全部转负 (-0.7% ~ -1.6%) | 结论效度 |
| P7 | \|r\|>1 截断影响 | 首轮计数 0 为**探针自身顺序 bug** (先 mask 后计数); 修正后 565 个股票-月, LS 敏感 ~2.7pp | 数据质量 |
| P8 | 双重排序 (剔小市值 30%) | Q1 断崖**更深** (+2~4.6% → -0.7~-2.2%), LS 全部上升 (13.0-15.1%) — 效应独立于 size | 稳健性 |

### 8.2 发现与处置 (H1-H8)

| # | 发现 | 严重度 | 处置 |
|---|------|--------|------|
| H1 | NW t 自实现与 statsmodels 逐位一致 | 确认 | 无需处置 |
| H2 | 无前视 (反向验证通过) | 确认 | 无需处置 |
| H3 | **断崖非小市值马甲** — 剔小盘后断崖更深、LS 上升; 但 Q1 时序与小盘共动 (ρ≈0.87) | 结论加固 | 报告新增 §3.2 双重排序证据; §3.1 的 2024-25 解释保留 (小盘反弹抬高 Q1 时序) |
| H4 | \|r\|>1 截断敏感: 565 个股票-月, LS 相差 ~2.7pp (空头端妖股敞口) | 偏差 (中) | 报告新增 §3.3 + §9 偏差行; 截断属保守方向 |
| H5 | **可实施性折扣**: 卖空限制 + 涨跌停不可成交 → 多空收益为理论上限 | 偏差 (高, 需显式披露) | 报告 §8 结论 #4 改写 + §9 首位偏差行 |
| H6 | 多头超额对基准敏感 (剔 Q1 基准转负) | 结论加固 | 报告 §2.1 补注 + §9 偏差行 |
| H7 | stale price 轻微 (0.3-0.4%) | 确认 | 无需处置 |
| H8 | 探针脚本 P7 顺序 bug (先 mask 后计数) | 复审自纠 | 修正重跑 (P7c); 原始结论不依赖该数字 |

**复审结论**: 核心结论全部存活且部分**加强** (H3 断崖独立于 size, H6 多头超额稳健偏乐观);
新增 2 项必须披露的偏差 (H4 截断敏感, H5 可实施性上限)。PASS 维持, 报告已同步修订。
