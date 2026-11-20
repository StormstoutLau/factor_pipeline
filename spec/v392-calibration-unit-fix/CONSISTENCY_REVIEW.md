# CONSISTENCY REVIEW v3.9.2 — 跨文档一致性

---
id: v392-calibration-unit-fix-CONSISTENCY-REVIEW
type: design
version: 1.1
status: verified
date: 2026-11-20
depends: [v392-calibration-unit-fix-RESEARCH, v392-calibration-unit-fix-DESIGN, v392-calibration-unit-fix-IMPLEMENTATION, v392-calibration-unit-fix-CHECKLIST]
upstream: null
---

> **版本**: v1.1 (2026-11-20；v1.0 = 2026-11-20)
> **范围**: RESEARCH v1.1 / DESIGN v1.1 / IMPLEMENTATION v1.1 / CHECKLIST v1.1
> **方法**: 逐项抽取受约束口径，两两对照；不一致项当场修正或登记
> **v1.1 变更**: 命名对齐（`EXECUTION` → `IMPLEMENTATION`，CHECKLIST v1.0 → v1.1），判定结论不变

---

## §1 一致性矩阵

| # | 口径 | RESEARCH | DESIGN | IMPLEMENTATION | CHECKLIST | 判定 |
|---|------|----------|--------|-----------|-----------|------|
| 1 | 批次/包版本 | v3.9.2 | 3.9.1→3.9.2 | 3.9.1→3.9.2 | 3.9.2 | ✅ |
| 2 | 默认基线 | 2047/15 | — | ≥2047/15 | 2047/15 | ✅ |
| 3 | 默认 SHA | `82728CE1…` | 逐位不变 | 全串 | `82728CE1…` | ✅ |
| 4 | c 读数 | 15.0677 | — | — | — | ✅ |
| 5 | c 门槛 | 建议 R²/区间 | `R²≥0.05`、`c∈[0.1,2.0]`、回退 0.5 | 同左 + 常量共享 | 同左 | ✅ |
| 6 | rho 读数/频率 | -0.147、月频错配 | 改日频 + `rho<=0→1.0` | 同左 | 同左 | ✅ |
| 7 | temporary | 代理、非 T+1 | `portfolio_ar1_proxy` | 同左 | 同左 | ✅ |
| 8 | 白名单 | 5 类 | 同 | 8 文件 + 版本 7 落点 | I10 引用 IMPLEMENTATION §0 | ✅ |
| 9 | 测试编号 | — | T1-T8 | T1-T8 | T1-T8 | ✅ |
| 10 | 遗留 | B9/B11 | 非目标 | 非目标 | D7 | ✅ |

---

## §2 发现与处置

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| M1 | 说明 | v3.8.1 `CONSISTENCY_REVIEW` 记录「2048 passed」，最终审计为 **2047** | 本批统一以最终审计 **2047** 为基线；旧文档不回改（历史时点读数） |
| M2 | 文档 | 调研 §4.4 年化区间曾与单月混写 | 步骤 2 已改为 1.6%–2.5%/年 |
| M3 | 文档 | DESIGN D5「6 处锚点」歧义 | 步骤 4 已改为「6 代码 + CHANGELOG」 |
| M4 | 设计 | 门槛阈值 `0.05` / `[0.1,2.0]` 为**自定守卫**，非文献结论 | 设计 D2 已显式声明；报告必须同注 |
| M5 | 实施 | 旧测试可能断言月频 rho / bar σ | IMPLEMENTATION R4 + CHECKLIST G7 要求逐条说明 |
| M6 | 范围 | 股票×日 vs 股票×月、截面 T+1 未修 | B9/B11 明确登记为后续批次，不在本批声称已修 |

---

## §3 版本链校正

- v3.8.1 调研 §6 U3 建议「组合月超额 AR(1)」与 DESIGN §7「日频」冲突，v3.8.1 未裁决；
- 本批 DESIGN §2 D3 明确**废止 U3**，以 DESIGN §7 为准，并在 §19 留痕；
- 该裁决只影响 `--calibrate` 路径，不构成对 v3.8.1 审计结论的否定（当时未覆盖此口径）。

---

## §4 结论

**PASS**。四份文档在批次/版本/SHA/门槛/频率/标注/白名单/测试编号上一致；
6 项差异均为说明或已闭环修正；无未登记的实质冲突。进入步骤 9 实施。
