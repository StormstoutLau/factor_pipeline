# RESEARCH — Layer 3 HAC 真实数据验证 (LAYER3_HAC_REAL_DATA)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 1-2
> **上游**: [PROJECT_STATUS §2 P1 #1](../PROJECT_STATUS.md) (冻结模型实证, 先做小样本验证)
> **范围**: 用真实 A 股日频数据验证 `PremiumEstimator.estimate_with_errors` (v3.4.12)
> 的数值合理性与 CI 行为; **不修改生产代码**, 不升版本。

## §1 调研问题

- **Q1**: 现有数据能否支撑月度 Fama-MacBeth 溢价估计 (期数 T、横截面 N、价格口径)?
- **Q2**: 复权价如何构造, 是否存在前视?
- **Q3**: 哪些量价因子可直接构造且无前视?
- **Q4**: 股票池如何清洗 (新股/停牌/极值)?
- **Q5**: 验证口径如何判定 HAC SE "合理"?
- **Q6**: 本次验证的已知偏差有哪些?

## §2 数据事实 (F1-F9, 2026-11-16 实测)

| # | 事实 | 证据 |
|---|------|------|
| F1 | 日频行情根目录 `E:\Ashare_data\market_data`; `stock_close` 1475×5688, 2020-01-02 → 2026-01-30 | `pd.read_pickle` 实测 shape/index |
| F2 | `stock_adj` 1394×5691 为累计复权因子 (000001 = 109.1694 且随时间递增); 复权价 = `close × adj` | 000001 序列核对 |
| F3 | `stock_amount` 1475×5688 为日成交额 (000001 median 1.32e6), 仅用于横截面排序 | 实测 |
| F4 | `market_value.csv` 1470×5684, 2020-01-02 → 2026-01-23 | 实测 |
| F5 | `price_volume_factors/UTR_turnover.pkl` 与 `construction_factors/*.pkl` 在当前 pandas 下**无法反序列化** (`StringDtype.__init__` 不兼容) → 本次不依赖 | 实测抛错 |
| F6 | `stock_ind.pkl` 仅到 2023-06-13, 无法覆盖全样本 → 不做行业中性化 | 实测 index 末端 |
| F7 | 面板**含退市股**: 179 只最后有效日 < 2025-01-01; 2020 年首有效 4364 只 | `last_valid_index` 年度分布 |
| F8 | 新股: 2021-2026 首有效 1315 只 → 需「上市满 250 交易日」过滤 | `first_valid_index` 年度分布 |
| F9 | v3.4.12 接口: `estimate_with_errors(factor, forward_returns, alpha=0.05, max_lag=None)` → 14 键; `premium_mean_se = sqrt(Ω_β/n_valid)` | [factor_health L65-L155](../../modules/factor_health/__init__.py#L65-L155) |

## §3 方法

### 3.1 采样与口径

- **频率**: 月度 (每月最后一个交易日), T ≈ 72 (2020-01 → 2026-01)
- **因子值**: 月末 t 使用 ≤ t 的行情; **前瞻收益**: 复权价 t → t+1 月
- **复权**: `price_adj = close × adj`; 收益率 `r_{t+1} = price_adj(t+1)/price_adj(t) − 1`
- **带宽**: `bandwidth=12` (1 年月度); v3.4.12 默认 24 (2 年) 在 T=72 下窗口占比过大
- **最小横截面**: 有效股票 ≥ 300 (远高于 `min_stocks=30`)

### 3.2 因子 (4 个, 全部可复现, 无前视)

| 因子 | 定义 | 方向预期 |
|------|------|---------|
| `momentum_1m` | 过去 21 日复权对数收益之和 | 正 |
| `reversal_1w` | 过去 5 日复权对数收益之和, 取负 | 正 (A 股短反转) |
| `volatility_1m` | 过去 21 日日对数收益 std, 取负 | 正 (低波溢价) |
| `amihud_1m` | 过去 21 日 `mean(|r_d| / amount_d)`, 取负 (×1e8) | 正 (流动性溢价) |

### 3.3 清洗

1. 剔除上市不足 250 交易日的股票 (按 `list_date_df` 与面板首有效日取较大者);
2. 停牌/缺失: 因子计算窗口要求 ≥ 15 个有效日 (`min_periods`), 不填充;
3. 横截面 winsorize 1%/99% 后做 z-score, 避免极值主导 OLS 斜率;
4. 前瞻收益 |r| > 100% 视为异常置 NaN。

## §4 验证口径 (V1-V6)

| # | 断言 | 依据 |
|---|------|------|
| V1 | 输出含 14 键, 数组长度 = T, `n_periods` = T | G2-G4 |
| V2 | `premium_mean == nanmean(beta_t)` (rel 1e-12) | 定义恒等式 |
| V3 | 有限 `premium_mean_se` > 0, 且 CI 包含点估计 | 正态 CI 构造 |
| V4 | `|premium_mean|/premium_mean_se` 与朴素 FM t (`mean/std×√T`) 同量级 (比值 0.3–3.0) | HAC 与 iid 应同阶 |
| V5 | 与 `diagnose()['premium_mean']` 同号 (允许 0 附近) | 平滑不改变总体水平方向 |
| V6 | 4 个因子全部完成, 无异常退出; 每个因子 `n_valid ≥ 60` | 数据充分性 |

## §5 已知偏差声明

| 偏差 | 说明 |
|------|------|
| 样本期短 | 2020-2026 (T≈72), 带宽 12 下有效窗口约 6 个; CI 可能偏宽 |
| 幸存者偏差 | 面板含 179 只退市股, 但 2020 年股票池仍是「现在可得」的并集, 偏差有限 |
| 复权口径 | `adj` 为事后累计复权因子, 用于收益率连续性 (标准做法), 因子侧无前视 |
| 无中性化 | 未做行业/市值中性化; Layer 3 为单因子 FM, 不要求 |
| 财务因子缺失 | 财务因子 pickle 不兼容 (F5), 本次仅量价 |

## §6 步骤 2 review 记录

| # | 检查项 | 结论 |
|---|--------|------|
| R1 | F1-F9 均为实测, 非推断 | ✅ 逐条来自 read_pickle/inspect |
| R2 | 复权价 = close×adj 有序列证据 | ✅ 000001 adj=109.17 且递增 |
| R3 | 因子定义无前视 (t 时点只用 ≤t) | ✅ 滚动窗口右对齐 |
| R4 | 前瞻收益与因子不重叠 (t → t+1) | ✅ |
| R5 | V4 同量级阈值 (0.3–3.0) 不苛刻 | ✅ HAC 与 iid 同阶, 5σ 差异才算异常 |
| R6 | 未把不可读因子 (F5) 写入设计 | ✅ |

**review 结论**: PASS。
