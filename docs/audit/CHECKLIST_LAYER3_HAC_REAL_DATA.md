# CHECKLIST — Layer 3 HAC 真实数据验证 (LAYER3_HAC_REAL_DATA)

> **版本**: v1.0 (2026-11-16)
> **对照工件**: [EXECUTION v1.0](../EXECUTION_LAYER3_HAC_REAL_DATA.md)
> **使用方式**: 步骤 10 审计时逐项勾选。

## A. 数据与因子

- [x] A1 `load_market` 读取 close/adj/amount/list_date 并对齐 index/columns
- [x] A2 复权价 = `close × adj` (F2)
- [x] A3 4 因子定义与 RESEARCH §3.2 一致 (momentum/reversal/volatility/amihud)
- [x] A4 上市满 250 交易日掩码 (**基于 `list_date`**: 面板起点前上市直接 eligible; 面板内新股 +365 天)
- [x] A5 月末采样 `resample('ME').last()` + 下月收益 `shift(-1)/x−1`
- [x] A6 横截面 winsorize 1/99 + z-score; `|r|>1` 置 NaN; 月有效股票 <300 → NaN

## B. 估计与断言

- [x] B1 调 `PremiumEstimator.estimate_with_errors(f, r, alpha)` 且 `bandwidth` 可配
- [x] B2 V1 14 键 + 数组长度硬断言
- [x] B3 V2 `premium_mean == nanmean(beta_t)` 硬断言
- [x] B4 V3 `se` 有限正 + CI 含点 硬断言
- [x] B5 V4 `hac_over_iid ∈ [0.3,3.0]` 软判定 (越界 WARN)
- [x] B6 V5 与 `diagnose` 同号 (`|pm|>2se` 时) 硬断言
- [x] B7 V6 `n_valid ≥ 60` 软判定 (WARN)
- [x] B8 stdout 表 + 可选 `--json`

## C. 运行

- [x] C1 `python scripts/verify_layer3_hac_real.py` 成功 (exit 0)
- [x] C2 4 因子全部产出; WARN 如实打印 (修正后清零)
- [x] C3 断言未被 try/except 吞掉
- [x] C4 结果数字与报告一致

## D. 文档

- [x] D1 `docs/analysis/LAYER3_HAC_REAL_DATA_VERIFICATION.md` 报告完成
- [x] D2 RESEARCH / EXECUTION / CHECKLIST / audit 互链
- [x] D3 已知偏差 (幸存者/样本期/无中性化/财务缺失) 显式声明

## E. 一致性与版本

- [x] E1 生产代码零改动 (`git diff --name-only` 仅 scripts/docs)
- [x] E2 不升版本 (3.4.12 保持), 缓存代际不变
- [x] E3 CONSISTENCY_REVIEW 判定 PASS
