# CHECKLIST v3.4.12 — 面板 HAC / Premium 标准误

> **版本**: v1.0 (2026-11-16)
> **对照工件**: [EXECUTION v1.0](../EXECUTION_V3.4.12_PREMIUM_HAC_SE.md)
> **使用方式**: 步骤 10 审计时逐项勾选, 任一项未勾选即不得发版。

## A. 代码落地 (`modules/factor_health/__init__.py`)

- [x] A1 抽出 `_smooth_betas`, `estimate` 改调用; 循环与原 L64-L76 逐行一致
- [x] A2 `_cross_sectional_betas` 改为 `_cross_sectional_betas_and_se(F, R)[0]` 薄包装
- [x] A3 `_cross_sectional_betas_and_se` 追加残差与 `beta_se = sqrt(σ̂²_ε/Σ(f−f̄)²)`
- [x] A4 `_hac_long_run_variance` 使用 Bartlett 核, 分母 n, n<3 → NaN
- [x] A5 `estimate_with_errors` 签名为 `(factor, forward_returns, alpha=0.05, max_lag=None)`
- [x] A6 返回 14 键, 与 G2-G4 一一对应
- [x] A7 局部 SE = `sqrt(max(Ω_t·Σw², ·))`, Ω<0 → NaN; 窗口 <3 → NaN
- [x] A8 全局 `premium_mean_se = sqrt(Ω_β/n_valid)`; `max_lag` 覆盖全局与局部
- [x] A9 `diagnose()` / `BreakpointDetector` 无 diff
- [x] A10 (复审 F1) SE 循环 `weights = weights / weights.sum()` — 与 `np.average` 归一化一致 (完整面板零影响)
- [x] A11 (复审 F2) `sigma2` 分母 `max(n_valid - 2, 1)` 守卫
- [x] A12 `_hac_long_run_variance` docstring 注明无 Stata 式 df 修正 (NW 1987 渐近形式)

## B. 测试 (`tests/unit/test_layer3_factor_health.py`)

- [x] B1 E1 六数组长度 T; `lambda_hat` 与 `estimate()` 全等; CI = λ̂ ± z·SE
- [x] B2 E2 `premium_mean == nanmean(beta_t)`; `se>0`; CI 包含均值
- [x] B3 E3 `n_periods/n_valid/hac_lag/alpha` 正确
- [x] B4 E4 `beta_se` 有限正数且 NaN 位置与 `beta_t` 一致; 单期手算一致
- [x] B5 E5 缺失注入 → 该期 `beta_t/beta_se` 为 NaN (λ̂ 仍有限); 仅 2 期有效 → λ̂/SE 全 NaN; 全缺失 → 标量 NaN; 无共同列 → T 行全 NaN; 无共同日期 → `n_periods=0`
- [x] B6 E6 `estimate()` 返回 ndarray 且与 `lambda_hat` 全等; `_beta_raw` 一致
- [x] B7 E7 CI 宽度比 = `z_0.10/z_0.05`
- [x] B8 Red **7 failed** → Green **7 passed** (E1-E7)
- [x] B9 (复审 F1) E8 缺失窗口 SE = 设计口径 (sum=1 权重), 且 > 未归一化值
- [x] B10 (复审 F2) E9 `min_stocks=2` 精确拟合 → `beta_se < 1e-12` 而非 NaN

## C. 回归

- [x] C1 `tests/unit/test_layer3_factor_health.py` 全绿 (**18 passed**)
- [x] C2 `tests/test_backtest` 全绿 (**599 passed / 8 skipped**, 基线不变)
- [x] C3 全量回归 **1755 passed / 15 skipped / 0 failed** (基线 1746 → +9)
- [x] C4 版本测试 7 passed + 手工 6/6

## D. 文档

- [x] D1 CHANGELOG 新增 v3.4.12 段
- [x] D2 PROJECT_STATUS P2 面板 HAC 行标 ✅ (含版本)
- [x] D3 DEV_PROGRESS 路标追加 v3.4.12
- [x] D4 CODE_WIKI `PremiumEstimator` 接口补 `estimate_with_errors`
- [x] D5 RESEARCH / EXECUTION / 审计报告互相链接, 数字与实测一致

## E. 一致性与发版

- [x] E1 六锚点均为 3.4.12
- [x] E2 文档数字与实测一致 (新增 9 例 E1-E9; Red 7 → Green 9)
- [x] E3 CONSISTENCY_REVIEW 判定 PASS

## F. 独立复审与外部验证 (2026-11-16 追加)

- [x] F1 独立复审完成: F1 (P2, 已修复+测试) / F2 (P3, 已修复+测试) / F3 (信息, 不改)
- [x] F2 Stata 18 对拍 L1-L3: 均值/beta_se/Ω_t 一致 (唯一系统差 = Stata df 修正 n/(n−k), 已声明)
- [x] F3 L4 Monte Carlo: premium SE/sd=0.94; lambda SE/sd=0.83 (≈90% 覆盖 @95% 名义, 已声明限制)
- [x] F4 复审与验证记录: [2026-11-16-premium-hac-se-audit.md Phase 7](2026-11-16-premium-hac-se-audit.md) / [EXECUTION §9](../EXECUTION_V3.4.12_PREMIUM_HAC_SE.md) / [scripts/verify_hac_stata.py](../../scripts/verify_hac_stata.py)
