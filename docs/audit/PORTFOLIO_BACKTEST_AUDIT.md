# 2026-11-16 代码质量审计 — 组合层 IC/Sharpe 回测

> **审计对象**: `scripts/verify_portfolio_backtest.py` (420 行) + 分析报告
> **代码版本**: 3.4.13 (不变; 本任务不改生产代码)
> **审计依据**: [RESEARCH](../research/RESEARCH_PORTFOLIO_BACKTEST.md) (F1-F14/Q1-Q5) /
> [DESIGN](private/DESIGN_PORTFOLIO_BACKTEST.md) (G1-G13) /
> [EXECUTION](../EXECUTION_PORTFOLIO_BACKTEST.md) (V1-V10)
> **审计方法**: audit-driven-development 4 阶段 + 运行两次的确定性对拍

## Phase 1 — Spec Inventory

| 工件 | 版本 | 状态 |
|------|------|------|
| RESEARCH_PORTFOLIO_BACKTEST.md | v1.0 | ✅ 数据事实 F1-F14 / 问题 Q1-Q5 / 口径 / 学术依据 |
| DESIGN_PORTFOLIO_BACKTEST.md (private) | v1.0 | ✅ G1-G13 + 模块结构 + 断言 + 边界 |
| EXECUTION_PORTFOLIO_BACKTEST.md | v1.0 | ✅ 代码结构 / V1-V10 / 验收命令 |
| PORTFOLIO_BACKTEST_VERIFICATION.md | v1.0 | ✅ Q1-Q5 结论 + 分位结构 + 成本 + 池对比 + 偏差 |
| 本审计 | v1.0 | ✅ |
| CHECKLIST / CONSISTENCY_REVIEW | — | 按 §13.8 中任务裁剪省略 |

## Phase 2 — Code vs Spec

| 规格 | 代码证据 | 结论 |
|------|---------|------|
| G1 复用 C 因子构造链 | `load_market`/`build_price_factors`/`load_financials`/`build_monthly_panels` 全部 import | ✅ |
| G2 不用 `compute_long_short_returns` | 全文无该调用; 自建行对齐 `build_quantile_weights` | ✅ |
| G3 复用指标函数 | `compute_rank_ic`/`compute_icir`/`compute_hit_rate`/`compute_turnover`/`compute_spread` 均 import 使用 | ✅ |
| G4 向量化分位 | `rank(axis=1, pct=True)` → `np.ceil(ranks*q)` | ✅ |
| G5 权重只在 f&r 有效处 | `valid = f.notna() & r.notna()`; `ranks = f.where(valid).rank(...)` | ✅ |
| G6 成本 2×turnover×fee + 首期建仓 | `build_turnover` 首期 `0.5*Σ\|w0\|`; `perf` 中 `2.0*tv*fee/1e4` | ✅ |
| G7 Sharpe 复用 / MaxDD·NW 自建 | `compute_spread(rv)*√12`; `max_drawdown`/`nw_t` 自建 | ✅ |
| G8 复合 = nanmean | `composite_panel` 用 `divide(..., where=cnt>0)` | ✅ |
| G9 池 B ≤月末最后交易日 | `align_pool` 用 `searchsorted(ts, 'right')-1` | ✅ |
| G10 子区间重跑 | `SEGMENTS` 循环内重新 `run_block` | ✅ |
| G13 z-score 全市场一次 | `z[name] = cross_section_prep(panels[name], ret, mask)` 无池参数 | ✅ |
| V1-V10 | 见 Phase 3/4; 首次运行即 V1-V6/V9/V10 全绿 | ✅ |
| 盈亏平衡解析解 | `gross_ann / (2*mean_t*12/1e4)` | ✅ |

## Phase 3 — Defect Scan

| # | 候选/实际 | 判定 | 处置 |
|---|----------|------|------|
| **D1** | **IC 口径错**: 初版在 `main` 用全市场 `z[name]` 算 IC → 池 all 与 hs300 的 IC 逐位相同 | **实际缺陷** (运行后发现) | 移入 `run_block`, 用 `f.where(pool_mask)` 计算池内 IC; 修正后 hs300 IC 从 0.0841→0.0565 (`turnover_1m`) |
| D2 | V10 检查全年份 → 首月 (因子全 NaN) / 末月 (无前瞻收益) `n_eff=0` 会误判 | 静态自查 | 加 `active = z.notna().any & ret.notna().any` 掩码 |
| D3 | V2 断言残留 `~rs.isin([...]) if False else ...` 死表达式 | 静态自查 | 清理为 `~np.isclose(rs,0) & ~np.isclose(rs,1)` |
| D4 | `perf` 用 `dict \| dict` (需 Py≥3.9, 项目最低版本未确认) | 静态自查 | 改为显式赋值, 零兼容风险 |
| D5 | 池 B 若重跑 `cross_section_prep` 会被 `count<300` thin mask 整月打空 | 设计 review | G13: z-score 全市场一次, 池 B 只过滤分位输入 |
| D6 | Q1 断崖 (2.0% vs Q2 16.2%) 是否为极端值伪影? | 非缺陷 | 临时诊断: Q1 月度 mean +0.17% / 中位年化 2.26% / \|r\|>15% 仅 3 月; 分年稳定 → 真实结构 |
| D7 | 沪深300 多空 MDD 42-50% 是否为计算错误? | 非缺陷 | 每分位 ~60 只, 多空 120 只分散度低 → 波动 ~25% 年化, 数学一致 |
| D8 | `r.fillna(0)` 是否掩盖真实缺失? | 非缺陷 | 权重已在 `valid` 上归零, `fillna(0)` 仅保证求和数值稳定; V2/V3 断言行和 |
| D9 | `bench` 用池内等权 (非真实指数) | 口径限制 | 已在报告 §9 披露 |

## Phase 4 — 回归与验证

| 项 | 结果 |
|----|------|
| 首次运行 (未修 IC) | 退出码 0; V1-V6/V9/V10 全通过; WARN 8 (V7) |
| 修正 IC 后运行 | 退出码 0; 全断言通过; WARN 8 (V7) |
| 确定性 (两次运行对拍) | LS/多头指标逐位一致 (IC 修正不影响组合): `turnover_1m` LS 0.138 / SR 0.830 / t 2.91 两次相同 |
| V5 IC vs FM | 4/4 同向 (premium_mean 3.6e-3~6.6e-3) |
| V6 费率单调 | 5 因子 × 2 池 × 3 区间 全部满足 |
| V10 池容量 | hs300 最小 294 只 ≥ 250 |
| 生产代码 | `git status` 仅 `scripts/` + `docs/` 新增; `modules/` `backtest/` 零改动 |
| 测试套件 | 未新增 pytest 用例 (脚本内断言即验收), 全量回归不受影响 |
| 中间产物 | `out/*.json` (257KB) 已删除, 仓库不跟踪 |

## Phase 5 — 风险与兼容

| 维度 | 结论 |
|------|------|
| 生产代码 / 公开 API | 零改动 |
| 版本号 / 缓存代际 | 3.4.13 / `v2.3.0-cache` 不变 |
| 依赖 | 无新增 (pandas/numpy/scipy 既有) |
| 运行时长 | 约 40s (数据加载为主) |
| 可复现性 | 无随机数; 固定输入 → 逐位相同 |

## Phase 6 — 自审

| 质疑 | 回应 |
|------|------|
| 为什么复用 C 脚本而不调用 `FactorBacktestEngine`? | Engine 依赖 DataLoaderV3 (日频 pipeline 输出), 与月频自建因子不兼容; 强接会引入两套口径 |
| 为什么不用 `compute_long_short_returns`? | 其 `factor[:,t]` vs `returns[:,t+1]` 错位约定会让本面板整体偏移一期 (F12) |
| 分位非单调 (Q3>Q5) 是否说明因子无效? | 不。多空 (Q5-Q1) 仍显著 (t 2.4-2.9); 非单调说明信息集中在左尾, 已在报告 §3/§8 如实呈现 |
| 多头超额≈0 是否与 C 的显著性矛盾? | 不矛盾: FM 检验的是截面单调关系, 主要由 Q1 驱动; 多头端 β 暴露与基准重叠 → 超额被稀释 |
| 沪深300 失败是否说明实现错误? | V5 池内 IC 与 FM 同向、池容量 V10 通过、MDD 与 60 只分位样本的波动数学一致; 是真实结论 |
| 是否应把 out/*.json 提交? | 不。属中间产物 (用户规则: 中间产物不入库); 报告已含全部结论数字 |

## Phase 7 — 审计结论

**PASS**。3 个实现缺陷 (D1 IC 口径 / D2 V10 边界 / D3 死表达式) 与 1 个兼容性隐患 (D4)
均在交付前修复; 1 个设计缺陷 (D5) 在设计 review 阶段拦截。
断言 V1-V6/V9/V10 全绿, V7/V8 WARN 均为**真实分位结构**而非代码错误 (D6/D7 已诊断)。
生产代码零改动, 版本/缓存/依赖不变, 结果确定性可复现。

**核心结论的可信度**: 全市场多空显著 (NW t 2.4-3.0) 与多头超额≈0 (t ≤0.48) 同时成立,
二者互为印证 — 收益来自空头端而非选股端。该结论已由独立诊断 (§3.1 分年 + Q1 分布) 加固。

## Phase 8 — 异构复审 (5 视角 × 8 探针, 2026-11-16)

> 复审视角: 计量推断 / 数据质量 / 稳健性 / 结论效度 / 可复现性; 探针脚本为临时文件,
> 用后删除, 证据并入本 Phase 与 [EXECUTION §8](../EXECUTION_PORTFOLIO_BACKTEST.md)。

### 8.1 探针结果 (P1-P8)

| # | 探针 (攻击面) | 结果 | 视角 |
|---|--------------|------|------|
| P1 | Q1 断崖是否为小市值马甲 | 时序共动 (ρ=0.85-0.89) 但横截面独立 (P8) | 计量推断 |
| P2 | 涨跌停可成交性 | 空头端 23.5-26.8% 跌停 / 多头端 13.7-21.0% 涨停 | 结论效度 |
| P3 | 停牌 stale price | Q1 内 0.3-0.4% — 轻微 | 数据质量 |
| P4 | NW t vs statsmodels HAC | 逐位一致 (diff=0) | 可复现性 |
| P5 | 前视反向验证 | IC(过去) 负且强 1.7-8.9 倍 — 无前视 | 计量推断 |
| P6 | 超额基准敏感性 (剔 Q1) | 全部转负 (-0.7% ~ -1.6%) | 结论效度 |
| P7 | \|r\|>1 截断 | 565 个股票-月; LS 敏感 ~2.7pp (首轮探针自身 bug 已修) | 数据质量 |
| P8 | 双重排序剔小盘 30% | 断崖更深 (+2~4.6% → -0.7~-2.2%), LS 13.0-15.1% | 稳健性 |

### 8.2 发现与处置 (H1-H8)

| # | 发现 | 处置 |
|---|------|------|
| H1 | NW t 实现正确 | 无需处置 |
| H2 | 无前视 | 无需处置 |
| H3 | 断崖独立于小市值 (加固); Q1 时序与小盘共动 | 报告 §3.2 新增双重排序证据 |
| H4 | \|r\|>1 截断敏感 ~2.7pp (空头端妖股敞口) | 报告 §3.3 + §9 偏差行 |
| H5 | 多空收益为理论上限 (卖空限制 + 涨跌停) | 报告 §8 #4 改写 + §9 显式披露 |
| H6 | 多头超额基准敏感 (剔 Q1 转负, 原口径偏乐观) | 报告 §2.1 补注 + §9 |
| H7 | stale 轻微 | 无需处置 |
| H8 | 探针 P7 顺序 bug (自纠) | 修正重跑; 原结论不依赖 |

**复审结论**: PASS 维持 — 0 个推翻性发现; 核心结论 2 项加固 (H3/H6), 2 项新披露偏差
(H4/H5); 报告 §3.2/§3.3/§8/§9 已同步修订。
