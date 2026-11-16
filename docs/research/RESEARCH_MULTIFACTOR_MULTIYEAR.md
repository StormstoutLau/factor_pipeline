# RESEARCH — 多因子 × 多年实证扩展 (MULTIFACTOR_MULTIYEAR)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 1-3
> **上游**: [LAYER3_HAC_REAL_DATA_VERIFICATION.md](../analysis/LAYER3_HAC_REAL_DATA_VERIFICATION.md) (v3.4.12 4 因子验证)
> **目标**: 把 Layer 3 溢价估计的真实数据验证从 4 因子 / 全样本, 扩到 **12 因子 × 全样本 + 3 分段**, 并在 Barra 可得区间内做**行业/风格中性化**复核, 关闭 P1 #1「多年多因子全量对比待扩」。

## §1 问题定义 (Q1-Q6)

| # | 问题 | 本任务答案形式 |
|---|------|--------------|
| Q1 | 4 个量价因子的结论能否在 8 个量价 + 4 个财务因子上复现? | 12 因子全样本 BH-FDR 表 |
| Q2 | 因子溢价是否在 2020-21 / 2022-23 / 2024-25 三段稳定? | 分段方向一致数 (0-3) + 分段 t |
| Q3 | 此前被判定「不可用」的预构造因子 pickle 能否解锁? | H: 兼容转换 + 冒烟回读 |
| Q4 | 溢价是否由行业/风格暴露驱动? | I: Barra 中性化前后对比 (2020-02→2023-05) |
| Q5 | 多重检验下哪些因子仍显著? | BH-FDR (m=12, 两个 p 值口径) |
| Q6 | 结论对带宽 / lag 是否稳健? | 带宽 6/12/24 + q 扫描 (抽样因子) |

## §2 工程事实 (全部实测)

| # | 事实 | 证据 |
|---|------|------|
| F1 | 日频行情 1475×5688, 2020-01-02 → 2026-01-30 (73 个月) | `stock_close.pkl` |
| F2 | 复权价 = `stock_close × stock_adj`; `stock_adj` 为累计后复权因子 (B 任务 P6 已确认单调不减比例中位数 0.999) | 序列核对 |
| F3 | `stock_amount` 为日成交额; `market_value.csv` 1470×5684, 2020-01-02 → 2026-01-23, 月频覆盖 3765 → 5474 | 实测 |
| F4 | `list_date_df.pkl` 5797 行, 列 `list_date`; 1 只缺日期 (B 任务 P1) | 实测 |
| F5 | **legacy pickle 根因**: `StringDtype.__init__() takes from 1 to 2 positional arguments but 3 were given` — 由更高版本 pandas 写出 (3 位置参数 `('pyarrow', nan)`), 本机 pandas 2.2.3 反序列化失败; **文件未损坏** | 复现 traceback |
| F6 | 6 个 legacy pickle 已转 parquet 至 `E:\Ashare_data\_converted\` (manifest.json), 冒烟回读 6/6 OK | `scripts/convert_legacy_pickles.py` |
| F7 | `current_ratio / debt_ratio` 1464×6231 (2020-01-02→2026-01-15), 财务股 (银行) 无 current_ratio; 与 close 交集 5684; 月频有效股票 min 4073 | 实测 |
| F8 | `LT_debt_ratio` 月频有效 min 3911; `ocf_yoy_processed` 1190×6507, 月频有效 min 4192 | 实测 |
| F9 | 财务因子按季度跳变后 ffilled (000001 在 1464 日中仅 13 次取值变化) | 实测 |
| F10 | `barra_df_tl.pkl`: 173 个月 2009-01-23 → **2023-05-31**, 每期 dict 含 `INDNAME` (28 行业) + 12 风格 (BETA/SIZE/RESVOL/MOMENTUM/…), 末月覆盖 4995 只 | 实测 |
| F11 | Barra 与行情同界点: Barra 止于 2023-05-31, `stock_ind.pkl` 止于 2023-06-13 → 行业口径一致可用区间 = 2020-02 → 2023-05 (**40 个月**) | 实测 |
| F12 | `index_dict.pkl` 为 `{'index': DataFrame[4150×2]}` (000300/000905/000906 日频权重, 2009→2026); 本任务不用 (市场收益用等权代理) | 实测 |
| F13 | `stock_suspend.pkl` 1475×5681 object, 非空=停牌原因; 本任务不额外使用 (停牌日价格为 NaN, 已天然剔除) | 实测 |
| F14 | `estimate_with_errors` 返回 14 键, `premium_mean_se` 为 β_t 序列的全局 HAC SE (bandwidth 无关, B 任务 P4) | [factor_health L65-L155](../../modules/factor_health/__init__.py#L65-L155) |
| F15 | `diagnose` 返回 `premium_mean` (平滑 λ̂ 均值) 与五态标签 | [L343-L391](../../modules/factor_health/__init__.py#L343-L391) |
| F16 | 预构造 `UTR_turnover.pkl` 72×5659 月频, 但构造口径未知 (取值量级 -878~2484) → **不使用**, 换手率改用 `amount / market_value` 自建 | 实测 |

## §3 方法

### 3.1 因子集 (12)

**量价 8** (日频滚动, 右对齐, 只用 ≤t 数据):

| 因子 | 定义 | 经济方向 |
|------|------|---------|
| `momentum_1m` | 21 日 log 收益和 | + |
| `reversal_1w` | −5 日 log 收益和 | + |
| `volatility_1m` | −21 日收益 std | + |
| `amihud_1m` | −mean(\|r\|/amount)·1e8 (21 日) | + |
| `turnover_1m` | −mean(amount/market_value) (21 日) | + |
| `size_mv` | −log(market_value) (月末) | + |
| `beta_60d` | −β (60 日市场模型, 市场=等权全样本收益) | + |
| `max_ret_1m` | −max(日收益) (21 日) | + |

**财务 4** (parquet, 月末取值; 方向已按经济含义取正):

| 因子 | 定义 | 方向 |
|------|------|------|
| `current_ratio` | 流动比率 | + |
| `debt_ratio` | −资产负债率 | + |
| `LT_debt_ratio` | −长期负债率 | + |
| `ocf_yoy` | 经营现金流同比 | + |

> 方向统一为「数值越大预期收益越高」, 便于横向比较 t 值符号。

### 3.2 标签与样本

- 月末 FM: 因子取月末最后交易日, 标签 = 下月末复权价收益 (`shift(-1)`)。
  > 口径注: `resample('ME')` 的索引标签为日历月末, 取值为当月最后交易日; 该标签只用于
  > 内部对齐与 `Period('M')` 连接 Barra, 不参与任何日频左连接。
- 上市满 250 交易日: `date >= list_date + 365 天` (沿用 B 任务 `build_eligible`, 面板起点前上市的老股直接 eligible)。
- 横截面: 1%/99% winsorize → z-score; 有效股票 < 300 的月份整行置 NaN。
- 标签离群: `|r| > 1.0` 置 NaN (沿用 B 任务)。

### 3.3 分段

| 段 | 区间 | 预期 T |
|----|------|--------|
| 全样本 | 2020-02 → 2025-12 | 71 |
| S1 | 2020-02 → 2021-12 | 23 |
| S2 | 2022-01 → 2023-12 | 24 |
| S3 | 2024-01 → 2025-12 | 24 |

> 分段用于**方向稳定性**, 不用于独立显著性主张 (T≈24 检验力低)。

### 3.4 中性化 (I)

区间 2020-02 → 2023-05 (40 月), 对 10 个非自指因子 (`size_mv` / `beta_60d` 与 Barra SIZE/BETA 同源, 不做中性化):

1. 因子横截面 z-score (同 3.2);
2. 回归 `f ~ 截距 + 行业哑变量(28, drop_first) + SIZE + BETA + RESVOL` (Barra 月度);
3. 取残差再 z-score;
4. 与原始口径分别跑 FM + HAC SE + BH-FDR (m=10), 对比显著性翻转。

### 3.5 稳健性

- 带宽 h ∈ {6, 12, 24}: `diagnose` 标签变化 + `λ̂` 与 h=12 路径的相关系数
  (溢价均值 `mean(β_t)` 与 HAC SE 均与 h 无关 — B 任务 P4 已确认, 故不复测溢价对 h 的敏感性);
- HAC lag q ∈ {1,2,3,4,6}: 12 因子 t 变化 (B 任务已做 4 因子, 此处扩展)。

## §4 验收口径

| # | 项 | 判定 |
|---|----|------|
| V1 | 14 键齐全 + 数组长度 = T | 硬 |
| V2 | `premium_mean == nanmean(beta_t)` (rel 1e-12) | 硬 |
| V3 | `premium_mean_se` 有限正 + CI 含点 | 硬 |
| V4 | `hac_over_iid ∈ [0.3, 3.0]` | 软 (WARN) |
| V5 | 与 `diagnose` 同号 (`|pm| > 2se` 时) | 硬 |
| V6 | `n_valid ≥ 60` (全样本) | 软 (WARN) |
| V7 | 财务因子每月有效股票 ≥ 300 | 硬 (失败即中断) |
| V8 | 分段方向一致数 ≥ 2/3 记为 `stable` | 报告标签 |
| V9 | 中性化: 每月 Barra 覆盖 ≥ 300 | 硬 |
| V10 | 中性化后 \|corr(factor, SIZE/BETA)\| 均值 < 0.10 | 软 (WARN) |
| V11 | 显著性翻转表 (raw → neutralized) 全量列出 | 硬 (输出) |
| V12 | 复现脚本单命令跑通, JSON 落盘 | 硬 |

## §5 已知偏差

| 偏差 | 影响 |
|------|------|
| 无中证监会行业全期数据 | 中性化仅 2020-02→2023-05 (40/71 月) |
| Barra SIZE/BETA 为模型暴露 | 与自建 size/beta 不完全同源, 仅作控制变量 |
| 财务因子季度跳变 + 财报滞后 | `current_ratio` 等按发布后 ffilled 口径, 未额外做发布日对齐 (数据源未提供公告日) |
| 等权市场收益 | beta 基准非市值加权, 低 beta 因子定义有偏差 |
| 幸存者偏差 | 面板为「现可得」并集; 含 179 只退市股, 偏差有限 |
| 多重检验 | BH-FDR 假设弱相关; 实测 β_t 相关需报告 → 附 Bonferroni 保守边界 (α/m) |
| 分段检验力 | S1-S3 各 T≈24, 仅作方向稳定性 |

## §6 交付物

| 文件 | 内容 |
|------|------|
| `scripts/convert_legacy_pickles.py` | H: legacy pickle → parquet + manifest |
| `scripts/verify_multifactor_multiyear.py` | C + I 一键复现 (JSON 落盘) |
| `docs/EXECUTION_MULTIFACTOR_MULTIYEAR.md` | 代码与口径 |
| `docs/analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md` | 结果与结论 |
| `docs/audit/*` | CHECKLIST / CONSISTENCY_REVIEW / 审计 |
