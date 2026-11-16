# CHECKLIST — 多因子 × 多年实证扩展 (MULTIFACTOR_MULTIYEAR)

> **版本**: v1.0 (2026-11-16)
> **对照**: [RESEARCH](../research/RESEARCH_MULTIFACTOR_MULTIYEAR.md) / DESIGN (private) / [EXECUTION](../EXECUTION_MULTIFACTOR_MULTIYEAR.md)

## A. 规格一致性

- [x] A1 因子集 = 8 量价 + 4 财务, 与 RESEARCH §3.1 逐项一致
- [x] A2 方向统一为「大 = 预期收益高」, 财务方向 (current_ratio +, 杠杆 −) 与 RESEARCH 一致
- [x] A3 标签口径: 月末 → 下月末复权收益, `|r|>1` 置 NaN
- [x] A4 eligible: `list_date + 365 天` (复用 B 任务 `build_eligible`)
- [x] A5 横截面: winsorize 1/99 + z-score + 有效 < 300 整月剔除
- [x] A6 分段区间 S1/S2/S3 与 RESEARCH §3.3 一致
- [x] A7 中性化区间 2020-02→2023-05, 控制变量 = 行业 + SIZE/BETA/RESVOL
- [x] A8 `size_mv` / `beta_60d` 排除中性化, 理由写入 RESEARCH §3.4 / EXECUTION §3.4
- [x] A9 验收 V1-V12 全部映射到脚本断言或输出

## B. 实现

- [x] B1 `convert_legacy_pickles.py`: shim `Unpickler.find_class` 拦截 `StringDtype`
- [x] B2 转换目标 = parquet + manifest, 原 pickle 不改动
- [x] B3 冒烟回读 (shape + NaN 比例) 6/6
- [x] B4 `verify_multifactor_multiyear.py`: 单命令 C + I + 敏感性
- [x] B5 复用 `build_eligible` / `cross_section_prep` / `month_end` (无重复实现)
- [x] B6 BH-FDR 双口径 (`p_norm` / `p_t`), q 单调化正确
- [x] B7 硬断言 (V1/V2/V3/V5/V7/V9), 软判定 WARN (V4/V6)
- [x] B8 `--json` 输出含 full / segments / stability / neutralization / sensitivity / warnings

## C. 数据

- [x] C1 行情 1475×5688, 2020-01-02 → 2026-01-30
- [x] C2 财务 4 因子与 close 交集 5585-5685 列; 月频有效 ≥ 4073
- [x] C3 Barra 173 月 (→2023-05-31), 28 行业 + 12 风格
- [x] C4 中性化区间 40 月, 每月覆盖 ≥ 300
- [x] C5 无 list_date 的股票静默剔除 (1 只, 与 B 任务一致)

## D. 文档

- [x] D1 RESEARCH F1-F16 全部有实测出处
- [x] D2 EXECUTION §7 实施阶段修正 D1-D4 记录
- [x] D3 验证报告 §6.1 更正 B 报告 amihud 措辞
- [x] D4 验证报告 §8 记录 DEFECT-1 (未改生产代码)
- [x] D5 标签语义 (`stable` ≠ 显著) 在报告 §5.3 澄清

## E. 交付

- [x] E1 `scripts/convert_legacy_pickles.py`
- [x] E2 `scripts/verify_multifactor_multiyear.py`
- [x] E3 `docs/analysis/MULTIFACTOR_MULTIYEAR_VERIFICATION.md`
- [x] E4 生产代码零改动 (`git status` 仅脚本 + 文档)
- [x] E5 版本不升 (3.4.12), 缓存代际不变

## F. 未覆盖 (显式排除)

- [ ] F1 组合层 IC / Sharpe 回测 (P1 #1 下一层)
- [ ] F2 Romano-Wolf stepdown / White RC
- [ ] F3 2023-06 之后的行业数据 (源缺失)
- [ ] F4 财报公告日对齐 (源未提供)
