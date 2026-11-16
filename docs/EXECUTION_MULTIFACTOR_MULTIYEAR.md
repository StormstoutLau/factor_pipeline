# EXECUTION — 多因子 × 多年实证扩展 (MULTIFACTOR_MULTIYEAR)

> **版本**: v1.0 (2026-11-16)
> **流程**: `docs/WORKFLOW_METHODOLOGY.md` §13.8 步骤 5-6
> **上游**: [RESEARCH v1.0](research/RESEARCH_MULTIFACTOR_MULTIYEAR.md) / DESIGN v1.0 (private)
> **目标**: 12 因子 (8 量价 + 4 财务) × 全样本/三分段 + Barra 中性化子样本; 生产代码零改动。

## §1 目标映射

| 目标 | 实施 | 验收 |
|------|------|------|
| G1 | `scripts/convert_legacy_pickles.py`: shim Unpickler → parquet + manifest + 冒烟回读 | H1 |
| G2 | `scripts/verify_multifactor_multiyear.py`: 单命令 C + I, `--json` 落盘 | V12 |
| G3 | 12 因子全样本 FM + HAC SE + BH-FDR (正态/t 双口径) | V1-V6 |
| G4/G5 | 3 分段 (S1/S2/S3) 各自 BH + 方向稳定数 | V8 |
| G6 | Barra 行业(28) + SIZE/BETA/RESVOL 中性化, 10 因子, 2020-02→2023-05 | V9-V11 |
| G7 | 带宽 {6,12,24} → 标签 + λ̂ 相关 | Q6 |
| G8 | HAC lag {1,2,3,4,6} → t | Q6 |
| G9 | 硬断言 AssertionError → exit 1; 软判定 WARN | — |
| G10 | 复用 B 任务 `build_eligible` / `cross_section_prep` / `month_end` | 代码审 |

## §2 工程事实复核

| # | 事实 | 复核 |
|---|------|------|
| F1 | 行情 1475 日 × 5688 股, 2020-01-02 → 2026-01-30 | ✅ |
| F2 | 复权价 `close × adj` | ✅ |
| F5 | legacy pickle 报错 = `StringDtype` 3 参数构造 (pandas 版本不兼容) | ✅ 复现 traceback |
| F6 | 6 个 legacy pickle → parquet, 冒烟 6/6 | ✅ manifest |
| F7 | 财务 4 因子与 close 交集 5586/5570/5685 列; 月频有效 ≥ 4073 | ✅ 实测 |
| F10 | Barra 173 月 (2009-01→2023-05), 28 行业 + 12 风格 | ✅ |
| F11 | 中性化区间 40 月 (2020-02→2023-05) | ✅ |
| F14 | `estimate_with_errors` 14 键; `premium_mean_se` 与 bandwidth 无关 | ✅ [L65-L155](../modules/factor_health/__init__.py#L65-L155) |
| F15 | `diagnose` 标签 = 结构健康 (ES/TD/stable), **不是显著性** | ✅ [L527-L556](../modules/factor_health/__init__.py#L527-L556) |

## §3 代码结构

```
scripts/convert_legacy_pickles.py        # H: shim Unpickler + parquet
scripts/verify_multifactor_multiyear.py  # C + I
  load_market / load_financials / load_barra
  build_price_factors (8) / build_monthly_panels
  bh_fdr / verify_factor / run_sample / stability
  neutralize_panel / compare_arms
  lag_sensitivity / bandwidth_sensitivity / main
```

复用: `from verify_layer3_hac_real import build_eligible, cross_section_prep, month_end`。

### 3.1 量价因子

```python
log_ret = np.log(adj_price).diff()
mkt = log_ret.mean(axis=1)                      # 等权市场
beta = log_ret.rolling(60, min_periods=40).cov(mkt)
beta = beta.div(mkt.rolling(60, min_periods=40).var(), axis=0)
turnover = amount.div(mv.where(mv > 0))
```

| 因子 | 定义 (方向已取正) |
|------|------------------|
| momentum_1m | +21 日 log 收益和 |
| reversal_1w | −5 日 log 收益和 |
| volatility_1m | −21 日 std |
| amihud_1m | −mean(\|r\|/amount)·1e8 |
| turnover_1m | −mean(amount/mv) |
| size_mv | −log(mv) |
| beta_60d | −β |
| max_ret_1m | −max(日收益) |

### 3.2 财务因子 (parquet → close 索引)

```python
df = pd.read_parquet(...).reindex(index=close.index, columns=close.columns).ffill(limit=5)
```
月末取值 (`resample('ME').last()`), 方向: current_ratio +; debt_ratio / LT_debt_ratio −; ocf_yoy +。

### 3.3 BH-FDR (双 p 口径)

```python
p_norm = 2 * (1 - stats.norm.cdf(abs(t)))
p_t    = 2 * (1 - stats.t.cdf(abs(t), df=n_valid - 1))
qv = p_sorted * m / rank; qv = np.minimum.accumulate(qv[::-1])[::-1]
```

### 3.4 中性化

```python
frame = y + SIZE + BETA + RESVOL + INDNAME   # 同月对齐, dropna
X = [1, industry_dummies(drop_first), SIZE, BETA, RESVOL]
resid = y - X @ lstsq(X, y)
out = (resid - mean) / std                   # 再 z-score
```
- `size_mv` / `beta_60d` 与 SIZE/BETA 同源 → 排除 (`SELF_REFERENTIAL`);
- BH 在臂内独立 (m=10)。

### 3.5 断言

```python
assert not missing_keys                    # V1 14 键
assert abs(pm - nanmean(beta)) <= 1e-12 * max(1, |ref|)   # V2
assert isfinite(se) and se > 0 and ci_low <= pm <= ci_high  # V3
assert sign(pm) == sign(diagnose_premium_mean) if |pm|>2se  # V5
assert min_month_count >= 300              # V7 (财务)
```
V4/V6 落 `warnings`, 不中断。

## §4 退化与边界

| 场景 | 行为 |
|------|------|
| 财务因子无数据月份 | 该月 NaN; 月度覆盖只统计有标签月份 |
| n_valid < 30 | 跳过 `diagnose` (见 §7 D2), 标签 `na` |
| Barra 月缺失 | 该月中性化残差 NaN |
| 设计矩阵奇异 | `lstsq` 伪逆 |
| 标签缺失 (末月) | 自动少 1 期 |
| 分段 T ≈ 24 | 出 t 但标注 V6 WARN; BH 仍按段内 m=12 计算 (仅方向参考) |

## §5 兼容性

| 维度 | 结论 |
|------|------|
| 生产代码 | 零改动 (`git status` 仅新增脚本/文档) |
| 依赖 | numpy / pandas / scipy (项目已有), pyarrow (parquet) |
| 数据写入 | 仅 `E:\Ashare_data\_converted\` (新目录, 不动原文件) |
| 版本 | 不升版本 |

## §6 验收映射

| # | 结果 |
|---|------|
| V1-V3, V5, V7, V9 | 12 因子 × 4 样本全部通过 (无 AssertionError) |
| V4 | 12 因子 SEratio ∈ [0.679, 1.083], 无 WARN |
| V6 | 全样本 n_valid 67-72 ✅; 分段 22-24 → WARN (设计内) |
| V8 | 6 因子 3/3, 6 因子 2/3 |
| V10 | 中性化后 \|ρ\| ≈ 0 (OLS 正交, 构造使然); 前置 \|ρ\|: SIZE 0.101 / BETA 0.120 / RESVOL 0.216, mean R²=0.206 |
| V11 | 10 因子 raw/neut 对比表已输出, 1 例翻转 (max_ret_1m) |
| V12 | `--json` 落盘成功 |
| 附 | β_t 两两相关 mean 0.357 / max 0.974 (19 对 > 0.5) → 附 Bonferroni 保守边界 (3/12) |

## §7 实施阶段修正 (幻觉消除 #3)

| # | 问题 | 处置 |
|---|------|------|
| D1 | 首版财务覆盖断言 `min_count` 把末月 (无前瞻收益) 计入 0 → V7 误报 | 只统计有标签月份 (`r.notna().any(axis=1)`) |
| D2 | `diagnose` 在 n_valid<30 时命中生产缺陷 `BreakpointDetector._no_breakpoint_result` 不存在 → AttributeError | 分段 (T≈24) 跳过 diagnose 并记标签 `na`; **不改生产代码**, 缺陷另案 (见审计 DEFECT-1) |
| D3 | 首版中性化正交性检查只记残差相关 (构造上恒 0), 缺有效性证据 | 补记前置 \|ρ\| 与回归 R² (mean 0.206), 使 V10 有信息量 |
| D4 | 首版 `load_financials` 误用 `columns.index` 重采样 | 改为按 `close.index` / `close.columns` reindex + `ffill(limit=5)` |

## §8 步骤 6 review 记录

| # | 检查项 | 结论 |
|---|--------|------|
| A1 | F1/F5/F7/F10/F11 与实测一致 | ✅ |
| A2 | 因子右对齐 (rolling 右界为 t, 无前视) | ✅ |
| A3 | 标签 `shift(-1)`, 与因子同月末对齐 | ✅ |
| A4 | `build_eligible` 语义与 B 任务一致 (list_date+365) | ✅ |
| A5 | `estimate_with_errors` 参数与 L65-L68 一致 | ✅ |
| A6 | BH 双口径实现与 `statsmodels` 定义一致 (q 单调化) | ✅ |
| A7 | 中性化列 (SIZE/BETA/RESVOL/INDNAME) 与 Barra 实测列名一致 | ✅ |
| A8 | `size_mv`/`beta_60d` 排除中性化的理由写入报告 | ✅ |

**review 结论**: PASS。
