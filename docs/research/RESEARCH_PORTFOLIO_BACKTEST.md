# RESEARCH — 组合层 IC/Sharpe 回测 (P1 #1 收尾)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 — 中任务 (步骤 1-2-3-4-5-6-9-10;
> 省略步骤 7-8 checklist/一致性 review, 验收并入审计)
> **目标**: 把 C 任务「因子层统计显著性」推进到「组合层可投资结论」——
> 回答「月频分位组合能否赚钱、成本吃掉多少、多因子合成是否优于单因子」。

---

## §1 目标与问题

| # | 问题 | 判定标准 |
|---|------|---------|
| Q1 | 4 个 BH 通过因子 (turnover_1m / reversal_1w / volatility_1m / max_ret_1m) 的月频多空组合 Sharpe 与 NW t 是多少? | 年化 Sharpe + Newey-West t (lag=3) |
| Q2 | Rank IC 序列是否与因子层 FM 结论同向? | IC 均值符号 = premium_mean 符号; ICIR / t |
| Q3 | 多因子 z-score 等权合成的 Sharpe 是否高于任一单因子? | 复合 vs 4 单因子的 Sharpe/ICIR 对比 |
| Q4 | 成本 (单边 10/20/30bp) 后是否仍有正收益? | 净 Sharpe + 净年化; 盈亏平衡费率 |
| Q5 | 沪深300 成分池内选股与全市场选股差异多大? | 两池 Sharpe / IC 对比; 池内 300 只的可实施性 |

**非目标**: 不做实盘撮合、不做涨跌停/停牌逐笔可成交性建模、不做行业中性组合 (Barra 仅覆盖
≤2023-05, 会截断样本)、不新增生产模块、不入库任何中间产物。

---

## §2 数据事实 (已实测, 2026-11-16)

| # | 事实 | 证据 |
|---|------|------|
| F1 | 日频行情 (close/adj/amount/mv/return/suspend/volume) 覆盖 **2020-01-02 → 2026-01-30** | `E:\Ashare_data\market_data\` 文件时间戳 + C 任务实测 |
| F2 | `index_dict.pkl` = DataFrame 4150 行, 列 `_id` (日期) + `indexComponentsWeight` (嵌套 dict) | 本次探查 |
| F3 | 嵌套结构为 `{index_code: {stock_code: weight_pct}}`; 早期行只含 `000300`, 后期含 `000300/000905/000852/000016/000906/...` | 本次探查首/末行 |
| F4 | **000300 (沪深300) 日频成分 2020+ 全覆盖 1475 个交易日, 每月末恰好 300 只** | 本次探查计数 |
| F5 | 000905 (中证500) 同样 1475 天 / 500 只; 000852 (中证1000) 亦可用 | 本次探查计数 |
| F6 | 成分权重为单位数百分比 (如 `000001: 1.0902`), 同日各成分和 ≈ 100 | 本次探查 |
| F7 | 因子面板与收益面板**同行对齐**: `ret_m = price_m.shift(-1)/price_m - 1`, 行 t = t 月末 → t+1 月末; 末月 NaN | [verify_multifactor_multiyear.py L418-L420](../../scripts/verify_multifactor_multiyear.py#L418-L420) |
| F8 | 因子方向已统一为「数值大 = 预期收益高」(如 `reversal_1w = -log_ret.rolling(5).sum()`) | L117-L126 |
| F9 | `ret_m` 已剔除 \|r\|>1.0 的异常 (重组/借壳) | L420 |
| F10 | 可投资域掩码 `eligible` = 上市满 365 自然日, 且月度有效股票 <300 的月份整行置 NaN | [verify_layer3_hac_real.py L68-L92](../../scripts/verify_layer3_hac_real.py#L68-L92) |
| F11 | `backtest/factor_metrics.py` 提供单期纯函数 `compute_rank_ic` / `compute_icir` / `compute_hit_rate` / `compute_turnover` | 该文件 |
| F12 | `compute_long_short_returns` 采用 `factor[:,t]` vs `returns[:,t+1]` 的**错位约定**, 与 F7 的同行对齐面板不兼容 | [factor_metrics.py L298-L363](../../backtest/factor_metrics.py#L298-L363) |
| F13 | 项目内无现成 Sharpe / MaxDD / Newey-West t 单函数 (grep 无命中) | 本次 grep |
| F14 | C 任务结论: BH 通过 4 个非自指因子; 核心三项 (turnover/reversal/volatility) 在任何多重检验口径下通过; `max_ret_1m` 最弱 (最差月 |t|=1.79) | [MULTIFACTOR_MULTIYEAR_VERIFICATION.md §6](../analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md) |

**关键推论**: F4/F5 使「指数内选股」完全可行且无前视 (用月末当日已公布成分); F7/F12 决定
**不能**直接复用 `compute_long_short_returns`, 必须自建行对齐的分位组合层; F13 决定
Sharpe/MaxDD/NW t 需新写 (约 30 行, 纯计算)。

---

## §3 口径定义 (设计前置)

### 3.1 组合构造

| 项 | 口径 |
|----|------|
| 调仓频率 | 月频, 月末收盘价计算因子, 月末调仓, 持有下月 |
| 分位 | 5 分位 (Q1 最低因子值 … Q5 最高); 方向已统一, 预期 Q5 > Q1 |
| 权重 | Q5 内**等权** (MVP); 不做市值加权 (与 C 任务 `market_value` 口径偏差隔离) |
| 多空 | Q5 等权 − Q1 等权 (Dollar-neutral, 各 100% 名义) |
| 多头 | Q5 等权, 与同池等权基准比较超额 |
| 复合因子 | 4 因子各自截面 winsorize(1/99) + z-score 后**等权平均**, 再按同一分位流程 |
| 股票池 | 池 A = 全市场 (eligible + 月度 ≥300); 池 B = 沪深300 成分 (月末最近交易日 300 只 ∩ eligible) |

### 3.2 成本

```
turnover_t = 0.5 * Σ_i |w_{i,t} - w_{i,t-1}|        # 单边换手比例
cost_t     = 2 * turnover_t * fee_bps / 1e4          # 买卖双边各一次
nav_t      = nav_{t-1} * (1 + r_t - cost_t)
```

费率档: 0 / 10 / 20 / 30 bp (单边)。**盈亏平衡费率** = 使净年化 = 0 的费率。

### 3.3 指标

| 指标 | 公式 | 备注 |
|------|------|------|
| Rank IC | `spearman(f_t, r_t)` 逐月 | 复用 `compute_rank_ic` |
| ICIR | `mean(IC)/std(IC, ddof=1)` | 复用 `compute_icir` |
| IC t | `mean(IC)/(std/√n)` | 报告为参考 (IC 自相关 → 略高估) |
| 年化收益 | `mean(r)*12` | 月频算术年化 |
| 年化波动 | `std(r, ddof=1)*√12` | |
| Sharpe | `mean(r)/std(r)*√12` | rf=0 |
| NW t | mean / NW-SE, lag = 3 | Newey & West (1987) |
| MaxDD | `max(1 - nav/cummax(nav))` | 基于复利净值 |
| 月胜率 | `count(r>0)/n` | |
| 年化换手 | `mean(turnover)*12` | |

### 3.4 样本与窗口

- 全样本: **2020-02 → 2025-12** (与 C 任务一致, 71 个月末)。
- 子区间: 2020-02 → 2022-12 / 2023-01 → 2025-12 (各约 35 月, 仅作方向参考)。
- 复合因子权重: 全样本内固定等权 (不做样本内优化, 避免数据窥探)。

---

## §4 学术依据

| 主题 | 文献 | 用于 |
|------|------|------|
| 分位组合 / 因子检验 | Fama & MacBeth (1973, JPE) | 与 C 任务因子层口径衔接 |
| 动量与短期反转 | Jegadeesh (1990, JF); Jegadeesh & Titman (1993, JF) | reversal_1w 方向 |
| 特质波动率 | Ang, Hodrick, Xing & Zhang (2006, JF) | volatility_1m |
| MAX 效应 | Bali, Cakici & Whitelaw (2011, JFE) | max_ret_1m |
| 流动性 / 换手 | Amihud (2002, JFM); 换手作为流动性代理 | turnover_1m / amihud |
| 交易成本与策略容量 | Novy-Marx & Velikov (2016, RFS); Frazzini, Israel & Moskowitz (2018, JFE) | 成本敏感性 / 换手 |
| HAC 标准误 | Newey & West (1987, Econometrica) | 多空收益 t 值 |
| Sharpe 比率 | Sharpe (1966, JoB); Lo (2002, FAJ) | 年化与统计解释 |
| 多因子合成 | 等权 z-score 合成 (naive diversification) | 复合因子对照 |

> 不引入样本内权重优化 (Green, Hand & Zhang 2017 的「多数因子样本外衰减」警示), 复合因子只用等权。

---

## §5 待验证假设与风险

| # | 假设/风险 | 验证方式 |
|---|----------|---------|
| H1 | 因子层 t 值与组合层 IC 同向 | 逐因子比对符号; 断言 V5 |
| H2 | 成本是核心威胁 (月频高换手) | 0/10/20/30bp 四档 + 盈亏平衡费率 |
| H3 | 复合因子 Sharpe > 单因子 (分散化) | 直接对比; 若否, 如实报告 |
| H4 | 沪深300 池内样本仅 60 只/分位, 噪音更大 | 两池并列 + 披露分位样本数 |
| H5 | 幸存者偏差 (面板含 179 只退市股, 已含在面板内) | 沿用 C 任务口径, 文档披露 |
| H6 | 等权 vs 市值加权差异 | MVP 只做等权, 列入 §7 偏差 |
| H7 | 月末调仓的可成交性 (涨跌停/停牌) | 未建模, 文档披露; `stock_suspend` 留作后续 |
| H8 | 复合因子权重为全样本固定等权 → 轻微数据窥探 | 只等权不优化, 且报告子区间稳健性 |

---

## §6 交付物

| # | 文件 | 内容 |
|---|------|------|
| 1 | `scripts/verify_portfolio_backtest.py` (新) | 组合层回测脚本: 因子复用 C 脚本构造, 分位组合 + 成本 + 指标 + V1-V10 断言 |
| 2 | `docs/analysis/PORTFOLIO_BACKTEST_VERIFICATION.md` (新) | Q1-Q5 结论表 + 分位单调性 + 成本曲线 + 子区间 + 偏差 |
| 3 | `docs/private/DESIGN_PORTFOLIO_BACKTEST.md` (新) | G1-Gn 设计决策 + 模块结构 + 不复用项理由 |
| 4 | `docs/EXECUTION_PORTFOLIO_BACKTEST.md` (新) | 实施步骤 + 代码结构 + 断言清单 + 回归记录 |
| 5 | `docs/audit/PORTFOLIO_BACKTEST_AUDIT.md` (新) | 步骤 10 审计 (audit-driven-development 4 阶段) |
| 6 | `PROJECT_STATUS.md` / `CHANGELOG.md` | P1 #1 状态更新 + 分析任务记录 |

**不新增版本号** (不改生产代码, 版本仍 3.4.13; 缓存代际 `v2.3.0-cache` 不变)。

---

## §7 复现命令

```powershell
python scripts/verify_portfolio_backtest.py --json out/portfolio_backtest.json
# 可选: --data-root <path> --converted-root <path> --fee-bps 0 10 20 30 --quantiles 5
```
